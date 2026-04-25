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
class M5Step:
    name: str
    module_name: str


M5_STEPS: list[M5Step] = [
    M5Step(
        name="research_definitions",
        module_name="stock_quant_v2.scripts.bootstrap_m5_research_definitions",
    ),
    M5Step(
        name="screen_chain",
        module_name="stock_quant_v2.scripts.bootstrap_m5_screen_chain",
    ),
    M5Step(
        name="backtest_chain",
        module_name="stock_quant_v2.scripts.bootstrap_m5_backtest_chain",
    ),
    M5Step(
        name="backtest_result_skeleton",
        module_name="stock_quant_v2.scripts.bootstrap_m5_backtest_result_skeleton",
    ),
    M5Step(
        name="backtest_quality",
        module_name="stock_quant_v2.scripts.check_m5_backtest_quality",
    ),
]


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

    def latest_signal_as_of_date(self) -> date | None:
        value = self._safe_scalar("SELECT MAX(as_of_date) FROM strategy_signal")
        return self._coerce_to_date(value)

    def latest_signal_effective_date(self) -> date | None:
        value = self._safe_scalar("SELECT MAX(effective_date) FROM strategy_signal")
        return self._coerce_to_date(value)

    def latest_backtest_request_id(self) -> int | None:
        return self._safe_int("SELECT MAX(id) FROM research_backtest_request")

    def latest_backtest_request_run_id(self) -> int | None:
        return self._safe_int(
            """
            SELECT run_id
            FROM research_backtest_request
            ORDER BY id DESC
            LIMIT 1
            """
        )

    def latest_backtest_result_id(self) -> int | None:
        return self._safe_int("SELECT MAX(id) FROM research_backtest_result")

    def latest_backtest_result_run_id(self) -> int | None:
        return self._safe_int(
            """
            SELECT run_id
            FROM research_backtest_result
            ORDER BY id DESC
            LIMIT 1
            """
        )

    def latest_screen_result_id(self) -> int | None:
        return self._safe_int("SELECT MAX(id) FROM research_screen_result")

    def _safe_scalar(self, sql: str) -> Any | None:
        try:
            with self.engine.connect() as conn:
                return conn.execute(text(sql)).scalar()
        except Exception:
            return None

    def _safe_int(self, sql: str) -> int | None:
        value = self._safe_scalar(sql)
        return int(value) if value is not None else None

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


def _build_m5_env(
    *,
    latest_trading_day: date,
    backtest_start_date: date,
    signal_as_of_date: date,
    signal_effective_date: date,
) -> dict[str, str]:
    backtest_end_date = min(latest_trading_day, signal_effective_date)

    return {
        "M5_AS_OF_DATE": latest_trading_day.isoformat(),
        "M5_TRADE_DATE": latest_trading_day.isoformat(),
        "M5_SIGNAL_AS_OF_DATE": signal_as_of_date.isoformat(),
        "M5_SCREEN_AS_OF_DATE": signal_as_of_date.isoformat(),
        "M5_SCREEN_TRADE_DATE": signal_as_of_date.isoformat(),
        "M5_SCREEN_EFFECTIVE_DATE": signal_effective_date.isoformat(),
        "M5_BACKTEST_START_DATE": backtest_start_date.isoformat(),
        "M5_BACKTEST_END_DATE": backtest_end_date.isoformat(),
    }


def run_m5_research_refresh_chain(
    target_date: date | None = None,
    start_date: date | None = None,
    skip_definitions: bool = False,
    skip_screen: bool = False,
    skip_quality: bool = False,
) -> int:
    inspector = DatabaseInspector(str(settings.postgres_v2_url))
    try:
        print("[M5] Research refresh chain started.")
        print(f"[M5] Using database URL: {settings.postgres_v2_url}")

        latest_trading_day = target_date or inspector.latest_trading_day()
        if latest_trading_day is None:
            print("[M5] Failed to resolve latest_trading_day. Please make sure M2 / M3 / M4 are ready.")
            return 2

        backtest_start_date = start_date
        if backtest_start_date is None:
            raw = os.getenv("M5_BACKTEST_START_DATE", "2024-04-01")
            backtest_start_date = datetime.strptime(raw, "%Y-%m-%d").date()

        signal_as_of_date = inspector.latest_signal_as_of_date()
        signal_effective_date = inspector.latest_signal_effective_date()

        if signal_as_of_date is None:
            print("[M5] Failed to resolve latest signal as_of_date from strategy_signal.")
            return 3
        if signal_effective_date is None:
            print("[M5] Failed to resolve latest signal effective_date from strategy_signal.")
            return 4

        print(f"[M5] latest_trading_day = {latest_trading_day.isoformat()}")
        print(f"[M5] backtest_start_date = {backtest_start_date.isoformat()}")
        print(f"[M5] signal_as_of_date = {signal_as_of_date.isoformat()}")
        print(f"[M5] signal_effective_date = {signal_effective_date.isoformat()}")

        base_env = _build_m5_env(
            latest_trading_day=latest_trading_day,
            backtest_start_date=backtest_start_date,
            signal_as_of_date=signal_as_of_date,
            signal_effective_date=signal_effective_date,
        )

        print("[M5] Effective env overrides:")
        for k, v in base_env.items():
            print(f"  - {k}={v}")

        steps = list(M5_STEPS)

        if skip_definitions:
            steps = [s for s in steps if s.name != "research_definitions"]
        if skip_screen:
            steps = [s for s in steps if s.name != "screen_chain"]
        if skip_quality:
            steps = [s for s in steps if s.name != "backtest_quality"]

        current_backtest_run_id: int | None = None

        for step in steps:
            step_env = dict(base_env)

            if step.name in {"backtest_result_skeleton", "backtest_quality"}:
                current_backtest_run_id = inspector.latest_backtest_request_run_id()
                if current_backtest_run_id is not None:
                    step_env["M5_BACKTEST_RUN_ID"] = str(current_backtest_run_id)

            print(f"\n[M5][{step.name}] starting: {step.module_name}")
            if "M5_BACKTEST_RUN_ID" in step_env:
                print(f"[M5][{step.name}] using M5_BACKTEST_RUN_ID={step_env['M5_BACKTEST_RUN_ID']}")

            rc = _run_module(step.module_name, extra_env=step_env)
            if rc != 0:
                print(f"[M5][{step.name}] failed (exit_code={rc})")
                print("[M5] Chain stopped. Fix this step before moving to M6.")
                return rc
            print(f"[M5][{step.name}] succeeded.")

        latest_screen_result_id = inspector.latest_screen_result_id()
        latest_backtest_request_id = inspector.latest_backtest_request_id()
        latest_backtest_request_run_id = inspector.latest_backtest_request_run_id()
        latest_backtest_result_id = inspector.latest_backtest_result_id()
        latest_backtest_result_run_id = inspector.latest_backtest_result_run_id()

        print("\n[M5] Lightweight post-run observations:")
        print(f"  - latest_screen_result_id: {latest_screen_result_id if latest_screen_result_id is not None else '-'}")
        print(f"  - latest_backtest_request_id: {latest_backtest_request_id if latest_backtest_request_id is not None else '-'}")
        print(f"  - latest_backtest_request_run_id: {latest_backtest_request_run_id if latest_backtest_request_run_id is not None else '-'}")
        print(f"  - latest_backtest_result_id: {latest_backtest_result_id if latest_backtest_result_id is not None else '-'}")
        print(f"  - latest_backtest_result_run_id: {latest_backtest_result_run_id if latest_backtest_result_run_id is not None else '-'}")

        print("\n[M5] Research refresh chain completed successfully.")
        print("[M5] Next action: run sql/m5_1_acceptance.sql before moving to M6.")
        return 0
    finally:
        inspector.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the M5 research refresh chain. "
            "Screen dates use latest strategy_signal as_of/effective dates; "
            "backtest window uses M5_BACKTEST_START_DATE -> latest_trading_day."
        )
    )
    parser.add_argument(
        "--target-date",
        required=False,
        help="Optional manual override target date in YYYY-MM-DD. Default: latest_trading_day from DB.",
    )
    parser.add_argument(
        "--start-date",
        required=False,
        help="Optional manual override backtest start date in YYYY-MM-DD. Default: env M5_BACKTEST_START_DATE or 2024-04-01.",
    )
    parser.add_argument(
        "--skip-definitions",
        action="store_true",
        help="Skip bootstrap_m5_research_definitions.",
    )
    parser.add_argument(
        "--skip-screen",
        action="store_true",
        help="Skip bootstrap_m5_screen_chain.",
    )
    parser.add_argument(
        "--skip-quality",
        action="store_true",
        help="Skip check_m5_backtest_quality.",
    )

    args = parser.parse_args(argv)

    target_date = datetime.strptime(args.target_date, "%Y-%m-%d").date() if args.target_date else None
    start_date = datetime.strptime(args.start_date, "%Y-%m-%d").date() if args.start_date else None

    return run_m5_research_refresh_chain(
        target_date=target_date,
        start_date=start_date,
        skip_definitions=args.skip_definitions,
        skip_screen=args.skip_screen,
        skip_quality=args.skip_quality,
    )


if __name__ == "__main__":
    raise SystemExit(main())