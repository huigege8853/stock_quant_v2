from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

from stock_quant_v2.config.settings import settings


@dataclass(frozen=True)
class SymbolRangeTopic:
    name: str
    table_name: str
    date_column: str
    bootstrap_module: str
    init_start_date: date


@dataclass(frozen=True)
class DateChainTopic:
    name: str
    table_name: str
    date_column: str
    bootstrap_module: str
    init_start_date: date


SYMBOL_RANGE_TOPICS: list[SymbolRangeTopic] = [
    SymbolRangeTopic(
        name="daily_bar",
        table_name="core_daily_bar",
        date_column="trade_date",
        bootstrap_module="stock_quant_v2.scripts.backfill_daily_bar_by_symbol_range",
        init_start_date=settings.bootstrap_daily_bar_start_date,
    ),
    SymbolRangeTopic(
        name="adjust_factor",
        table_name="core_adjust_factor",
        date_column="trade_date",
        bootstrap_module="stock_quant_v2.scripts.backfill_adjust_factor_by_symbol_range",
        init_start_date=settings.bootstrap_daily_bar_start_date,
    ),
]

DATE_CHAIN_TOPICS: list[DateChainTopic] = [
    DateChainTopic(
        name="instrument_status_daily",
        table_name="core_instrument_status_daily",
        date_column="trade_date",
        bootstrap_module="stock_quant_v2.scripts.bootstrap_instrument_status_daily_first_chain",
        init_start_date=settings.bootstrap_daily_bar_start_date,
    ),
    DateChainTopic(
        name="price_limit_daily",
        table_name="core_price_limit_daily",
        date_column="trade_date",
        bootstrap_module="stock_quant_v2.scripts.bootstrap_price_limit_daily_first_chain",
        init_start_date=settings.bootstrap_daily_bar_start_date,
    ),
    DateChainTopic(
        name="market_index_bar",
        table_name="core_market_index_bar",
        date_column="trade_date",
        bootstrap_module="stock_quant_v2.scripts.bootstrap_market_index_first_chain",
        init_start_date=settings.bootstrap_daily_bar_start_date,
    ),
]

OPTIONAL_DATE_CHAIN_TOPICS: list[DateChainTopic] = [
    DateChainTopic(
        name="fundamental_snapshot",
        table_name="core_fundamental_snapshot",
        date_column="trade_date",
        bootstrap_module="stock_quant_v2.scripts.bootstrap_fundamental_snapshot_first_chain",
        init_start_date=settings.bootstrap_daily_bar_start_date,
    ),
]

CALENDAR_BOOTSTRAP_MODULE = "stock_quant_v2.scripts.bootstrap_instrument_calendar"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _run_module(module_name: str, extra_env: dict[str, str] | None = None) -> int:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)

    cmd = [sys.executable, "-m", module_name]
    completed = subprocess.run(cmd, cwd=_project_root(), env=env)
    return int(completed.returncode)


class DatabaseInspector:
    def __init__(self, db_url: str) -> None:
        self.engine = create_engine(db_url)

    def close(self) -> None:
        self.engine.dispose()

    def latest_trading_day(self) -> date | None:
        candidates = [
            ("meta_trading_calendar", "trade_date", "is_open"),
            ("meta_trading_calendar", "calendar_date", "is_open"),
            ("meta_trading_calendar", "trade_date", "is_trading_day"),
            ("meta_trading_calendar", "calendar_date", "is_trading_day"),
        ]

        for table_name, date_col, open_col in candidates:
            sql = f"""
            SELECT MAX({date_col})
            FROM {table_name}
            WHERE {open_col} = TRUE
              AND {date_col} <= CURRENT_DATE
            """
            value = self._safe_scalar(sql)
            coerced = self._coerce_to_date(value)
            if coerced is not None:
                return coerced

        fallback = self._safe_scalar("SELECT MAX(trade_date) FROM core_daily_bar")
        return self._coerce_to_date(fallback)

    def max_date(self, table_name: str, date_column: str) -> date | None:
        value = self._safe_scalar(f"SELECT MAX({date_column}) FROM {table_name}")
        return self._coerce_to_date(value)

    def row_count(self, table_name: str) -> int | None:
        value = self._safe_scalar(f"SELECT COUNT(*) FROM {table_name}")
        return int(value) if value is not None else None

    def _safe_scalar(self, sql: str) -> Any | None:
        try:
            with self.engine.connect() as conn:
                return conn.execute(text(sql)).scalar()
        except Exception:
            return None

    @staticmethod
    def _coerce_to_date(value: Any | None) -> date | None:
        if value is None:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            return datetime.strptime(value, "%Y-%m-%d").date()
        return None


def _resolve_incremental_start_date(init_start_date: date, last_date: date | None, row_count: int | None) -> date:
    if row_count is None or row_count == 0 or last_date is None:
        return init_start_date
    return last_date + timedelta(days=1)


def _run_symbol_range_topic(topic: SymbolRangeTopic, start_date: date, end_date: date) -> int:
    print(
        f"[M2][{topic.name}] symbol-range incremental update: "
        f"{start_date.isoformat()} -> {end_date.isoformat()} | module={topic.bootstrap_module}"
    )
    return _run_module(
        topic.bootstrap_module,
        extra_env={
            "BOOTSTRAP_DAILY_BAR_START_DATE": start_date.isoformat(),
            "BOOTSTRAP_DAILY_BAR_END_DATE": end_date.isoformat(),
        },
    )


def _run_date_chain_topic(topic: DateChainTopic, start_date: date, end_date: date) -> int:
    print(
        f"[M2][{topic.name}] date-range incremental update: "
        f"{start_date.isoformat()} -> {end_date.isoformat()} | module={topic.bootstrap_module}"
    )
    return _run_module(
        topic.bootstrap_module,
        extra_env={
            "BOOTSTRAP_DAILY_BAR_START_DATE": start_date.isoformat(),
            "BOOTSTRAP_DAILY_BAR_END_DATE": end_date.isoformat(),
        },
    )


def run_m2_data_refresh_chain(include_optional: bool = False) -> int:
    inspector = DatabaseInspector(str(settings.postgres_v2_url))
    try:
        print("[M2] Data refresh chain started.")
        print(f"[M2] Using database URL: {settings.postgres_v2_url}")

        print(f"\n[M2] Pre-step starting: {CALENDAR_BOOTSTRAP_MODULE}")
        rc = _run_module(CALENDAR_BOOTSTRAP_MODULE)
        if rc != 0:
            print(f"[M2] Pre-step failed: {CALENDAR_BOOTSTRAP_MODULE} (exit_code={rc})")
            return rc
        print(f"[M2] Pre-step succeeded: {CALENDAR_BOOTSTRAP_MODULE}")

        latest_trading_day = inspector.latest_trading_day()
        if latest_trading_day is None:
            print("[M2] Failed to resolve latest_trading_day after calendar bootstrap.")
            return 2

        print(f"[M2] latest_trading_day = {latest_trading_day.isoformat()}")

        # 1) symbol 方式：daily_bar / adjust_factor
        for topic in SYMBOL_RANGE_TOPICS:
            row_count = inspector.row_count(topic.table_name)
            last_date = inspector.max_date(topic.table_name, topic.date_column)

            print(f"\n[M2][{topic.name}] current_row_count = {row_count}")
            print(f"[M2][{topic.name}] current_max_date = {last_date.isoformat() if last_date else '-'}")

            start_date = _resolve_incremental_start_date(topic.init_start_date, last_date, row_count)

            if last_date is not None and last_date >= latest_trading_day:
                print(f"[M2][{topic.name}] already up to date, skipped.")
                continue

            if start_date > latest_trading_day:
                print(f"[M2][{topic.name}] computed empty range, skipped.")
                continue

            rc = _run_symbol_range_topic(topic, start_date=start_date, end_date=latest_trading_day)
            if rc != 0:
                print(f"[M2][{topic.name}] incremental update failed (exit_code={rc})")
                return rc

            print(f"[M2][{topic.name}] incremental update succeeded.")

        # 2) 其余仍按日期链更新，但语义是“追加到最新”
        date_topics = list(DATE_CHAIN_TOPICS)
        if include_optional:
            date_topics.extend(OPTIONAL_DATE_CHAIN_TOPICS)

        for topic in date_topics:
            row_count = inspector.row_count(topic.table_name)
            last_date = inspector.max_date(topic.table_name, topic.date_column)

            print(f"\n[M2][{topic.name}] current_row_count = {row_count}")
            print(f"[M2][{topic.name}] current_max_date = {last_date.isoformat() if last_date else '-'}")

            start_date = _resolve_incremental_start_date(topic.init_start_date, last_date, row_count)

            if last_date is not None and last_date >= latest_trading_day:
                print(f"[M2][{topic.name}] already up to date, skipped.")
                continue

            if start_date > latest_trading_day:
                print(f"[M2][{topic.name}] computed empty range, skipped.")
                continue

            rc = _run_date_chain_topic(topic, start_date=start_date, end_date=latest_trading_day)
            if rc != 0:
                print(f"[M2][{topic.name}] incremental update failed (exit_code={rc})")
                return rc

            print(f"[M2][{topic.name}] incremental update succeeded.")

        print("\n[M2] Data refresh chain completed successfully.")
        print("[M2] Next action: run sql/m2_2_acceptance.sql before moving to M3.")
        return 0
    finally:
        inspector.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the M2 incremental data refresh chain. "
            "daily_bar / adjust_factor use symbol-range append-to-latest; "
            "other topics append by date-range."
        )
    )
    parser.add_argument(
        "--include-optional",
        action="store_true",
        help="Also run optional topics like fundamental snapshot.",
    )
    args = parser.parse_args(argv)
    return run_m2_data_refresh_chain(include_optional=args.include_optional)


if __name__ == "__main__":
    raise SystemExit(main())