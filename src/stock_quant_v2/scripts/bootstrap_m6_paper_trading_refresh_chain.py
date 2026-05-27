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
class M6Step:
    name: str
    module_name: str


M6_ACCOUNT_INIT = M6Step(
    name="paper_account",
    module_name="stock_quant_v2.scripts.bootstrap_m6_paper_account",
)

M6_MAIN_STEPS: list[M6Step] = [
    M6Step(
        name="paper_trading_first_chain",
        module_name="stock_quant_v2.scripts.bootstrap_m6_paper_trading_first_chain",
    ),
    M6Step(
        name="paper_trading_quality",
        module_name="stock_quant_v2.scripts.check_m6_paper_trading_quality",
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

    def latest_available_bar_date(self) -> date | None:
        value = self._safe_scalar("SELECT MAX(trade_date) FROM core_daily_bar")
        return self._coerce_to_date(value)

    def latest_executable_screen_source(
        self,
        effective_date_cap: date | None = None,
        strategy_version_id: int | None = None,
    ) -> tuple[int | None, int | None, date | None, date | None, date | None]:
        latest_bar_date = self.latest_available_bar_date()
        if latest_bar_date is None:
            return None, None, None, None, None

        effective_upper_bound = (
            min(latest_bar_date, effective_date_cap)
            if effective_date_cap is not None
            else latest_bar_date
        )

        if strategy_version_id is not None:
            sql = """
            SELECT
                rsr.signal_run_id,
                rsr.screen_request_id,
                rsr.as_of_date,
                rsr.effective_date
            FROM research_screen_result rsr
            JOIN strategy_signal ss ON ss.run_id = rsr.signal_run_id
            WHERE rsr.result_status = 'SUCCESS'
              AND rsr.effective_date <= :effective_upper_bound
              AND ss.strategy_version_id = :strategy_version_id
            GROUP BY rsr.id, rsr.signal_run_id, rsr.screen_request_id, rsr.as_of_date, rsr.effective_date
            ORDER BY rsr.effective_date DESC, rsr.id DESC
            LIMIT 1
            """
            params = {
                "effective_upper_bound": effective_upper_bound,
                "strategy_version_id": strategy_version_id,
            }
        else:
            # Legacy standalone route.  Campaign runners should provide
            # M6_STRATEGY_VERSION_ID to avoid global latest screen selection.
            sql = """
            SELECT signal_run_id, screen_request_id, as_of_date, effective_date
            FROM research_screen_result rsr
            WHERE result_status = 'SUCCESS'
              AND effective_date <= :effective_upper_bound
            ORDER BY rsr.effective_date DESC, rsr.id DESC
            LIMIT 1
            """
            params = {"effective_upper_bound": effective_upper_bound}

        try:
            with self.engine.connect() as conn:
                row = conn.execute(text(sql), params).first()
        except Exception:
            return None, None, None, None, latest_bar_date

        if not row:
            return None, None, None, None, latest_bar_date

        signal_run_id = int(row[0]) if row[0] is not None else None
        screen_request_id = int(row[1]) if row[1] is not None else None
        as_of_date = self._coerce_to_date(row[2])
        effective_date = self._coerce_to_date(row[3])
        return signal_run_id, screen_request_id, as_of_date, effective_date, latest_bar_date

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


def _env_int(name: str) -> int | None:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return None
    return int(str(raw).strip())


def _resolve_m6_source(
    inspector: DatabaseInspector,
    manual_target: date | None,
    strategy_version_id: int | None = None,
) -> tuple[int, int, date, date, date, str]:
    (
        latest_signal_run_id,
        latest_screen_request_id,
        latest_as_of_date,
        latest_effective_date,
        latest_bar_date,
    ) = inspector.latest_executable_screen_source(
        effective_date_cap=manual_target,
        strategy_version_id=strategy_version_id,
    )

    if latest_bar_date is None:
        raise RuntimeError("Failed to resolve latest available daily_bar date.")

    if (
        latest_signal_run_id is None
        or latest_screen_request_id is None
        or latest_as_of_date is None
        or latest_effective_date is None
    ):
        raise RuntimeError(
            "Failed to resolve latest executable screen source. "
            f"latest_available_bar_date={latest_bar_date}. "
            "Please make sure M5 screen SUCCESS results exist and "
            "their effective_date is <= latest available daily_bar date."
        )

    source = (
        "manual_target_cap_executable_screen"
        if manual_target is not None
        else "latest_executable_screen"
    )

    return (
        latest_signal_run_id,
        latest_screen_request_id,
        latest_as_of_date,
        latest_effective_date,
        latest_bar_date,
        source,
    )


def _build_m6_env(
    *,
    as_of_date: date,
    effective_date: date,
    source_signal_run_id: int,
    source_screen_request_id: int,
) -> dict[str, str]:
    return {
        "M6_AS_OF_DATE": as_of_date.isoformat(),
        "M6_TRADE_DATE": effective_date.isoformat(),
        "M6_TARGET_DATE": effective_date.isoformat(),
        "M6_EFFECTIVE_DATE": effective_date.isoformat(),
        "M6_SOURCE_SIGNAL_RUN_ID": str(source_signal_run_id),
        "M6_SOURCE_SCREEN_REQUEST_ID": str(source_screen_request_id),
    }


def run_m6_paper_trading_refresh_chain(
    target_date: date | None = None,
    with_account_init: bool = False,
    skip_quality: bool = False,
) -> int:
    inspector = DatabaseInspector(str(settings.postgres_v2_url))
    try:
        print("[M6] Paper trading refresh chain started.")
        print(f"[M6] Using database URL: {settings.postgres_v2_url}")

        try:
            (
                source_signal_run_id,
                source_screen_request_id,
                as_of_date,
                effective_date,
                latest_bar_date,
                target_source,
            ) = _resolve_m6_source(
                inspector,
                target_date,
                strategy_version_id=_env_int("M6_STRATEGY_VERSION_ID"),
            )
        except Exception as exc:
            print(f"[M6] Failed to resolve executable source: {exc}")
            print("[M6] Please make sure M4 / M5 outputs are ready.")
            return 2

        print(f"[M6] latest_available_bar_date = {latest_bar_date.isoformat()}")
        print(f"[M6] target_source = {target_source}")
        print(f"[M6] latest_screen_request_id = {source_screen_request_id}")
        print(f"[M6] latest_signal_run_id = {source_signal_run_id}")
        print(f"[M6] strategy_version_id_filter = {_env_int('M6_STRATEGY_VERSION_ID')}")
        print(f"[M6] as_of_date = {as_of_date.isoformat()}")
        print(f"[M6] effective_date = {effective_date.isoformat()}")

        env_overrides = _build_m6_env(
            as_of_date=as_of_date,
            effective_date=effective_date,
            source_signal_run_id=source_signal_run_id,
            source_screen_request_id=source_screen_request_id,
        )
        print("[M6] Effective env overrides:")
        for k, v in env_overrides.items():
            print(f"  - {k}={v}")

        if with_account_init:
            print(f"\n[M6][{M6_ACCOUNT_INIT.name}] starting: {M6_ACCOUNT_INIT.module_name}")
            rc = _run_module(M6_ACCOUNT_INIT.module_name, extra_env=env_overrides)
            if rc != 0:
                print(f"[M6][{M6_ACCOUNT_INIT.name}] failed (exit_code={rc})")
                print("[M6] Chain stopped. Fix account init before continuing.")
                return rc
            print(f"[M6][{M6_ACCOUNT_INIT.name}] succeeded.")

        steps = list(M6_MAIN_STEPS)
        if skip_quality:
            steps = [s for s in steps if s.name != "paper_trading_quality"]

        for step in steps:
            print(f"\n[M6][{step.name}] starting: {step.module_name}")
            rc = _run_module(step.module_name, extra_env=env_overrides)
            if rc != 0:
                print(f"[M6][{step.name}] failed (exit_code={rc})")
                print("[M6] Chain stopped. Fix this step before moving to M7.")
                return rc
            print(f"[M6][{step.name}] succeeded.")

        print("\n[M6] Paper trading refresh chain completed successfully.")
        print("[M6] Next action: run sql/m6_1_acceptance.sql before moving to M7.")
        return 0
    finally:
        inspector.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the M6 paper trading refresh chain. "
            "Default flow: optional account init -> paper_trading_first_chain -> quality. "
            "Source selection rule: latest SUCCESS screen result whose effective_date "
            "is <= latest available daily_bar date."
        )
    )
    parser.add_argument(
        "--target-date",
        required=False,
        help="Optional manual upper bound for executable screen effective_date in YYYY-MM-DD.",
    )
    parser.add_argument(
        "--with-account-init",
        action="store_true",
        help="Also run bootstrap_m6_paper_account before the main paper trading chain.",
    )
    parser.add_argument(
        "--skip-quality",
        action="store_true",
        help="Skip check_m6_paper_trading_quality.",
    )

    args = parser.parse_args(argv)

    target_date = datetime.strptime(args.target_date, "%Y-%m-%d").date() if args.target_date else None

    return run_m6_paper_trading_refresh_chain(
        target_date=target_date,
        with_account_init=args.with_account_init,
        skip_quality=args.skip_quality,
    )


if __name__ == "__main__":
    raise SystemExit(main())