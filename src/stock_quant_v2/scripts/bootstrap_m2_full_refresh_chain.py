from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

from stock_quant_v2.config.settings import settings


@dataclass(frozen=True)
class SymbolRangeTopic:
    name: str
    bootstrap_module: str
    full_start_date: date


@dataclass(frozen=True)
class DateChainTopic:
    name: str
    bootstrap_module: str
    full_start_date: date


SYMBOL_RANGE_TOPICS: list[SymbolRangeTopic] = [
    SymbolRangeTopic(
        name="daily_bar",
        bootstrap_module="stock_quant_v2.scripts.backfill_daily_bar_by_symbol_range",
        full_start_date=settings.bootstrap_daily_bar_start_date,
    ),
    SymbolRangeTopic(
        name="adjust_factor",
        bootstrap_module="stock_quant_v2.scripts.backfill_adjust_factor_by_symbol_range",
        full_start_date=settings.bootstrap_daily_bar_start_date,
    ),
]

DATE_CHAIN_TOPICS: list[DateChainTopic] = [
    DateChainTopic(
        name="instrument_status_daily",
        bootstrap_module="stock_quant_v2.scripts.bootstrap_instrument_status_daily_first_chain",
        full_start_date=settings.bootstrap_daily_bar_start_date,
    ),
    DateChainTopic(
        name="price_limit_daily",
        bootstrap_module="stock_quant_v2.scripts.bootstrap_price_limit_daily_first_chain",
        full_start_date=settings.bootstrap_daily_bar_start_date,
    ),
    DateChainTopic(
        name="market_index_bar",
        bootstrap_module="stock_quant_v2.scripts.bootstrap_market_index_first_chain",
        full_start_date=settings.bootstrap_daily_bar_start_date,
    ),
]

OPTIONAL_DATE_CHAIN_TOPICS: list[DateChainTopic] = [
    DateChainTopic(
        name="fundamental_snapshot",
        bootstrap_module="stock_quant_v2.scripts.bootstrap_fundamental_snapshot_first_chain",
        full_start_date=settings.bootstrap_daily_bar_start_date,
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


def _run_symbol_range_full(topic: SymbolRangeTopic, latest_trading_day: date) -> int:
    print(
        f"[M2-FULL][{topic.name}] symbol-range full refresh: "
        f"{topic.full_start_date.isoformat()} -> {latest_trading_day.isoformat()} "
        f"| module={topic.bootstrap_module}"
    )
    return _run_module(
        topic.bootstrap_module,
        extra_env={
            "BOOTSTRAP_DAILY_BAR_START_DATE": topic.full_start_date.isoformat(),
            "BOOTSTRAP_DAILY_BAR_END_DATE": latest_trading_day.isoformat(),
            "DAILY_BAR_RESUME_ENABLED": "false",
            "ADJUST_FACTOR_RESUME_ENABLED": "false",
            "ADJUST_FACTOR_FORCE_RERUN": "true",
        },
    )


def _run_date_chain_full(topic: DateChainTopic, latest_trading_day: date) -> int:
    print(
        f"[M2-FULL][{topic.name}] date-range full refresh: "
        f"{topic.full_start_date.isoformat()} -> {latest_trading_day.isoformat()} "
        f"| module={topic.bootstrap_module}"
    )
    return _run_module(
        topic.bootstrap_module,
        extra_env={
            "BOOTSTRAP_DAILY_BAR_START_DATE": topic.full_start_date.isoformat(),
            "BOOTSTRAP_DAILY_BAR_END_DATE": latest_trading_day.isoformat(),
        },
    )


def run_m2_full_refresh_chain(include_optional: bool = False) -> int:
    inspector = DatabaseInspector(str(settings.postgres_v2_url))
    try:
        print("[M2-FULL] Full refresh chain started.")
        print(f"[M2-FULL] Using database URL: {settings.postgres_v2_url}")

        print(f"\n[M2-FULL] Pre-step starting: {CALENDAR_BOOTSTRAP_MODULE}")
        rc = _run_module(CALENDAR_BOOTSTRAP_MODULE)
        if rc != 0:
            print(f"[M2-FULL] Pre-step failed: {CALENDAR_BOOTSTRAP_MODULE} (exit_code={rc})")
            return rc
        print(f"[M2-FULL] Pre-step succeeded: {CALENDAR_BOOTSTRAP_MODULE}")

        latest_trading_day = inspector.latest_trading_day()
        if latest_trading_day is None:
            print("[M2-FULL] Failed to resolve latest_trading_day after calendar bootstrap.")
            return 2

        print(f"[M2-FULL] latest_trading_day = {latest_trading_day.isoformat()}")

        for topic in SYMBOL_RANGE_TOPICS:
            rc = _run_symbol_range_full(topic, latest_trading_day=latest_trading_day)
            if rc != 0:
                print(f"[M2-FULL][{topic.name}] full refresh failed (exit_code={rc})")
                return rc
            print(f"[M2-FULL][{topic.name}] full refresh succeeded.")

        date_topics = list(DATE_CHAIN_TOPICS)
        if include_optional:
            date_topics.extend(OPTIONAL_DATE_CHAIN_TOPICS)

        for topic in date_topics:
            rc = _run_date_chain_full(topic, latest_trading_day=latest_trading_day)
            if rc != 0:
                print(f"[M2-FULL][{topic.name}] full refresh failed (exit_code={rc})")
                return rc
            print(f"[M2-FULL][{topic.name}] full refresh succeeded.")

        print("\n[M2-FULL] Full refresh chain completed successfully.")
        print("[M2-FULL] Next action: run sql/m2_2_acceptance.sql before moving to M3.")
        return 0
    finally:
        inspector.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the M2 full refresh chain. "
            "daily_bar / adjust_factor use symbol-range full refresh from configured start_date to latest_trading_day; "
            "other topics refresh by date-range."
        )
    )
    parser.add_argument(
        "--include-optional",
        action="store_true",
        help="Also run optional topics like fundamental snapshot.",
    )
    args = parser.parse_args(argv)
    return run_m2_full_refresh_chain(include_optional=args.include_optional)


if __name__ == "__main__":
    raise SystemExit(main())