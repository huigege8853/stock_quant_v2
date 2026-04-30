from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

from stock_quant_v2.config.settings import settings


DAILY_BAR_TAIL_SCAN_TRADING_DAYS = 10
DAILY_BAR_PARTIAL_COVERAGE_RATIO = 0.95
CN_A_APP_TIMEZONE = "Asia/Shanghai"
# Same-day CN A-share daily bars are expected to be available after the
# evening EOD publication window. Before this cutoff, DailyRun should keep
# using the latest completed core_daily_bar date to avoid ingesting partial
# intraday data. After this cutoff, the chain should actively try today's
# daily_bar instead of skipping it merely because raw/core rows are not
# present yet.
DAILY_BAR_SAME_DAY_READY_HOUR = 18
DAILY_BAR_SAME_DAY_READY_MINUTE = 0


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


@dataclass(frozen=True)
class DailyBarPartialRepairPlan:
    repair_start_date: date
    scan_start_date: date
    scan_end_date: date
    expected_rows: int
    threshold_rows: int
    coverage_by_date: list[tuple[date, int]]
    anomalous_days: list[tuple[date, int]]


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


def _local_now() -> datetime:
    timezone_name = os.environ.get("APP_TIMEZONE") or os.environ.get("TZ") or CN_A_APP_TIMEZONE
    try:
        return datetime.now(ZoneInfo(timezone_name))
    except Exception:
        return datetime.now(ZoneInfo(CN_A_APP_TIMEZONE))


def _local_today() -> date:
    return _local_now().date()


def _same_day_daily_bar_ready(local_now: datetime) -> bool:
    return (local_now.hour, local_now.minute) >= (
        DAILY_BAR_SAME_DAY_READY_HOUR,
        DAILY_BAR_SAME_DAY_READY_MINUTE,
    )


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

    def latest_core_daily_bar_date(self) -> date | None:
        value = self._safe_scalar("""
            SELECT MAX(trade_date)
            FROM core_daily_bar
            WHERE price_adjust_type = 'RAW'
        """)
        return self._coerce_to_date(value)

    def effective_daily_bar_end_date(self, calendar_latest_trading_day: date) -> tuple[date, date | None, str | None]:
        """Return the safest end date for daily_bar/adjust_factor refresh.

        The trading calendar may contain today's trading day before the EOD bars
        are ready. Before the evening EOD cutoff, same-day targets with no core
        rows are kept on the latest completed core_daily_bar date. After the
        cutoff, the chain actively tries today's daily_bar instead of skipping it
        just because raw/core rows are not present yet. On the next calendar day,
        the previous trading day remains eligible for normal catch-up.
        """
        latest_core_date = self.latest_core_daily_bar_date()
        local_now = _local_now()
        local_today = local_now.date()

        if latest_core_date is None:
            return calendar_latest_trading_day, None, None

        if calendar_latest_trading_day > local_today and latest_core_date < calendar_latest_trading_day:
            reason = (
                "calendar latest trading day is ahead of local app date; "
                "defer to latest completed core_daily_bar date"
            )
            return latest_core_date, latest_core_date, reason

        if calendar_latest_trading_day == local_today and latest_core_date < calendar_latest_trading_day:
            if _same_day_daily_bar_ready(local_now):
                reason = (
                    "calendar latest trading day is today and local time is after EOD ready cutoff; "
                    "attempt same-day daily_bar refresh"
                )
                return calendar_latest_trading_day, latest_core_date, reason

            reason = (
                "calendar latest trading day is today/current session before EOD ready cutoff and "
                "daily_bar has no completed RAW rows yet; defer to latest completed core_daily_bar date"
            )
            return latest_core_date, latest_core_date, reason

        return calendar_latest_trading_day, latest_core_date, None

    def max_date(self, table_name: str, date_column: str) -> date | None:
        value = self._safe_scalar(f"SELECT MAX({date_column}) FROM {table_name}")
        return self._coerce_to_date(value)

    def row_count(self, table_name: str) -> int | None:
        value = self._safe_scalar(f"SELECT COUNT(*) FROM {table_name}")
        return int(value) if value is not None else None

    def recent_trading_days(self, end_date: date, limit: int) -> list[date]:
        candidates = [
            ("meta_trading_calendar", "trade_date", "is_open"),
            ("meta_trading_calendar", "calendar_date", "is_open"),
            ("meta_trading_calendar", "trade_date", "is_trading_day"),
            ("meta_trading_calendar", "calendar_date", "is_trading_day"),
        ]

        for table_name, date_col, open_col in candidates:
            sql = f"""
            SELECT DISTINCT {date_col} AS trade_date
            FROM {table_name}
            WHERE {open_col} = TRUE
              AND {date_col} <= :end_date
            ORDER BY {date_col} DESC
            LIMIT :limit
            """
            rows = self._safe_rows(sql, {"end_date": end_date, "limit": limit})
            dates = [self._coerce_to_date(row.get("trade_date")) for row in rows]
            resolved = sorted(d for d in dates if d is not None)
            if resolved:
                return resolved

        fallback_sql = """
        SELECT DISTINCT trade_date
        FROM core_daily_bar
        WHERE price_adjust_type = 'RAW'
          AND trade_date <= :end_date
        ORDER BY trade_date DESC
        LIMIT :limit
        """
        rows = self._safe_rows(fallback_sql, {"end_date": end_date, "limit": limit})
        dates = [self._coerce_to_date(row.get("trade_date")) for row in rows]
        return sorted(d for d in dates if d is not None)

    def daily_bar_raw_coverage(self, start_date: date, end_date: date) -> dict[date, int]:
        sql = """
        SELECT
            trade_date,
            COUNT(DISTINCT instrument_id) AS instrument_count
        FROM core_daily_bar
        WHERE price_adjust_type = 'RAW'
          AND trade_date BETWEEN :start_date AND :end_date
        GROUP BY trade_date
        """
        rows = self._safe_rows(sql, {"start_date": start_date, "end_date": end_date})
        coverage: dict[date, int] = {}
        for row in rows:
            trade_date = self._coerce_to_date(row.get("trade_date"))
            if trade_date is None:
                continue
            coverage[trade_date] = int(row.get("instrument_count") or 0)
        return coverage

    def detect_daily_bar_partial_repair_plan(self, latest_trading_day: date) -> DailyBarPartialRepairPlan | None:
        trading_days = self.recent_trading_days(
            end_date=latest_trading_day,
            limit=DAILY_BAR_TAIL_SCAN_TRADING_DAYS,
        )
        if len(trading_days) < 2:
            return None

        scan_start_date = trading_days[0]
        scan_end_date = trading_days[-1]
        coverage_map = self.daily_bar_raw_coverage(scan_start_date, scan_end_date)
        coverage_by_date = [(trade_date, coverage_map.get(trade_date, 0)) for trade_date in trading_days]

        non_zero_counts = [row_count for _, row_count in coverage_by_date if row_count > 0]
        if not non_zero_counts:
            return None

        expected_rows = max(non_zero_counts)
        threshold_rows = int(expected_rows * DAILY_BAR_PARTIAL_COVERAGE_RATIO)
        anomalous_days = [
            (trade_date, row_count)
            for trade_date, row_count in coverage_by_date
            if row_count < threshold_rows
        ]

        if not anomalous_days:
            return None

        repair_start_date = min(trade_date for trade_date, _ in anomalous_days)
        return DailyBarPartialRepairPlan(
            repair_start_date=repair_start_date,
            scan_start_date=scan_start_date,
            scan_end_date=scan_end_date,
            expected_rows=expected_rows,
            threshold_rows=threshold_rows,
            coverage_by_date=coverage_by_date,
            anomalous_days=anomalous_days,
        )

    def _safe_scalar(self, sql: str) -> Any | None:
        try:
            with self.engine.connect() as conn:
                return conn.execute(text(sql)).scalar()
        except Exception:
            return None

    def _safe_rows(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(sql), params or {})
                return [dict(row._mapping) for row in result]
        except Exception:
            return []

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


def _format_coverage_pairs(pairs: list[tuple[date, int]]) -> str:
    return ", ".join(f"{trade_date.isoformat()}={row_count}" for trade_date, row_count in pairs)


def _run_symbol_range_topic(
    topic: SymbolRangeTopic,
    start_date: date,
    end_date: date,
    extra_env: dict[str, str] | None = None,
) -> int:
    print(
        f"[M2][{topic.name}] symbol-range incremental update: "
        f"{start_date.isoformat()} -> {end_date.isoformat()} | module={topic.bootstrap_module}"
    )
    env = {
        "BOOTSTRAP_DAILY_BAR_START_DATE": start_date.isoformat(),
        "BOOTSTRAP_DAILY_BAR_END_DATE": end_date.isoformat(),
    }
    if extra_env:
        env.update(extra_env)
    return _run_module(topic.bootstrap_module, extra_env=env)


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

        daily_bar_end_date, latest_core_daily_bar_date, daily_bar_end_reason = inspector.effective_daily_bar_end_date(
            latest_trading_day
        )
        if latest_core_daily_bar_date is not None:
            print(f"[M2][daily_bar] latest_core_daily_bar_date = {latest_core_daily_bar_date.isoformat()}")
        print(f"[M2][daily_bar] effective_end_date = {daily_bar_end_date.isoformat()}")
        if daily_bar_end_reason:
            print(f"[M2][daily_bar] effective_end_reason = {daily_bar_end_reason}")

        # 1) symbol 方式：daily_bar / adjust_factor
        for topic in SYMBOL_RANGE_TOPICS:
            row_count = inspector.row_count(topic.table_name)
            last_date = inspector.max_date(topic.table_name, topic.date_column)

            print(f"\n[M2][{topic.name}] current_row_count = {row_count}")
            print(f"[M2][{topic.name}] current_max_date = {last_date.isoformat() if last_date else '-'}")

            topic_end_date = daily_bar_end_date if topic.name in {"daily_bar", "adjust_factor"} else latest_trading_day
            if topic_end_date != latest_trading_day:
                print(
                    f"[M2][{topic.name}] target_end_date adjusted: "
                    f"{latest_trading_day.isoformat()} -> {topic_end_date.isoformat()}"
                )

            start_date = _resolve_incremental_start_date(topic.init_start_date, last_date, row_count)
            child_extra_env: dict[str, str] = {}
            repair_plan: DailyBarPartialRepairPlan | None = None

            if topic.name == "daily_bar":
                repair_plan = inspector.detect_daily_bar_partial_repair_plan(topic_end_date)
                if repair_plan is not None:
                    print(
                        f"[M2][daily_bar] tail coverage scan: "
                        f"{repair_plan.scan_start_date.isoformat()} -> {repair_plan.scan_end_date.isoformat()} | "
                        f"expected_rows={repair_plan.expected_rows}, threshold_rows={repair_plan.threshold_rows}"
                    )
                    print(
                        f"[M2][daily_bar] tail coverage detail: "
                        f"{_format_coverage_pairs(repair_plan.coverage_by_date)}"
                    )
                    print(
                        f"[M2][daily_bar] partial days detected: "
                        f"{_format_coverage_pairs(repair_plan.anomalous_days)}"
                    )
                    print(
                        f"[M2][daily_bar] repair range adjusted to: "
                        f"{repair_plan.repair_start_date.isoformat()} -> {topic_end_date.isoformat()}"
                    )
                    start_date = min(start_date, repair_plan.repair_start_date)
                    child_extra_env.update(
                        {
                            # Existing daily-bar controls; no new env vars are introduced here.
                            "DAILY_BAR_RESUME_ENABLED": "false",
                            "DAILY_BAR_FORCE_RERUN": "true",
                        }
                    )

            if last_date is not None and last_date >= topic_end_date and repair_plan is None:
                print(f"[M2][{topic.name}] already up to date, skipped.")
                continue

            if start_date > topic_end_date:
                print(f"[M2][{topic.name}] computed empty range, skipped.")
                continue

            rc = _run_symbol_range_topic(
                topic,
                start_date=start_date,
                end_date=topic_end_date,
                extra_env=child_extra_env or None,
            )
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

            topic_end_date = daily_bar_end_date if topic.name in {"daily_bar", "adjust_factor"} else latest_trading_day
            if topic_end_date != latest_trading_day:
                print(
                    f"[M2][{topic.name}] target_end_date adjusted: "
                    f"{latest_trading_day.isoformat()} -> {topic_end_date.isoformat()}"
                )

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
