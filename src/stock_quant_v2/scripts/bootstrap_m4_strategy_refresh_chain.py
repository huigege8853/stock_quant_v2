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
class M4Chain:
    name: str
    module_name: str


M4_MAIN_CHAIN = M4Chain(
    name="rule_strategy_chain",
    module_name="stock_quant_v2.scripts.bootstrap_m4_rule_strategy_chain",
)


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

    def signal_total_rows(self) -> int | None:
        value = self._safe_scalar("SELECT COUNT(*) FROM strategy_signal")
        return int(value) if value is not None else None

    def signal_latest_as_of_date(self) -> date | None:
        value = self._safe_scalar("SELECT MAX(as_of_date) FROM strategy_signal")
        return self._coerce_to_date(value)

    def signal_latest_effective_date(self) -> date | None:
        value = self._safe_scalar("SELECT MAX(effective_date) FROM strategy_signal")
        return self._coerce_to_date(value)

    def strategy_definition_count(self) -> int | None:
        value = self._safe_scalar("SELECT COUNT(*) FROM strategy_definition")
        return int(value) if value is not None else None

    def strategy_version_count(self) -> int | None:
        value = self._safe_scalar("SELECT COUNT(*) FROM strategy_version")
        return int(value) if value is not None else None

    def parameter_schema_count(self) -> int | None:
        value = self._safe_scalar("SELECT COUNT(*) FROM strategy_parameter_schema")
        return int(value) if value is not None else None

    def current_true_rows(self) -> list[dict[str, Any]]:
        sql = """
        SELECT
            sd.strategy_code,
            COUNT(*) AS current_true_count
        FROM strategy_version sv
        JOIN strategy_definition sd
          ON sd.id = sv.strategy_definition_id
        WHERE sv.is_current = TRUE
        GROUP BY sd.strategy_code
        ORDER BY sd.strategy_code
        """
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(text(sql)).mappings().all()
                return [dict(r) for r in rows]
        except Exception:
            return []

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


def _build_m4_env(target_date: date) -> dict[str, str]:
    target = target_date.isoformat()
    # 这里统一导出一组不冲突的日期变量。
    # 如果下游 M4 脚本当前只消费其中一个，也能直接生效；
    # 若当前下游完全不读这些变量，则下一步只需补 child script，不用重写编排层。
    return {
        "M4_AS_OF_DATE": target,
        "M4_SIGNAL_AS_OF_DATE": target,
        "M4_TRADE_DATE": target,
        "M4_EFFECTIVE_DATE": target,
    }


def run_m4_strategy_refresh_chain(target_date: date | None = None) -> int:
    inspector = DatabaseInspector(str(settings.postgres_v2_url))
    try:
        print("[M4] Strategy refresh chain started.")
        print(f"[M4] Using database URL: {settings.postgres_v2_url}")

        latest_trading_day = target_date or inspector.latest_trading_day()
        if latest_trading_day is None:
            print("[M4] Failed to resolve latest_trading_day. Please make sure M2 is ready.")
            return 2

        print(f"[M4] latest_trading_day = {latest_trading_day.isoformat()}")

        env_overrides = _build_m4_env(latest_trading_day)
        print("[M4] Effective env overrides:")
        for k, v in env_overrides.items():
            print(f"  - {k}={v}")

        print(f"\n[M4][{M4_MAIN_CHAIN.name}] starting: {M4_MAIN_CHAIN.module_name}")
        rc = _run_module(M4_MAIN_CHAIN.module_name, extra_env=env_overrides)
        if rc != 0:
            print(f"[M4][{M4_MAIN_CHAIN.name}] failed (exit_code={rc})")
            print("[M4] Chain stopped. Fix M4 before moving to M5.")
            return rc
        print(f"[M4][{M4_MAIN_CHAIN.name}] succeeded.")

        strategy_definition_count = inspector.strategy_definition_count()
        strategy_version_count = inspector.strategy_version_count()
        parameter_schema_count = inspector.parameter_schema_count()
        signal_total_rows = inspector.signal_total_rows()
        signal_latest_as_of_date = inspector.signal_latest_as_of_date()
        signal_latest_effective_date = inspector.signal_latest_effective_date()
        current_true_rows = inspector.current_true_rows()

        print("\n[M4] Lightweight post-run observations:")
        print(f"  - strategy_definition_count: {strategy_definition_count if strategy_definition_count is not None else '-'}")
        print(f"  - strategy_version_count: {strategy_version_count if strategy_version_count is not None else '-'}")
        print(f"  - parameter_schema_count: {parameter_schema_count if parameter_schema_count is not None else '-'}")
        print(f"  - signal_total_rows: {signal_total_rows if signal_total_rows is not None else '-'}")
        print(f"  - signal_latest_as_of_date: {signal_latest_as_of_date.isoformat() if signal_latest_as_of_date else '-'}")
        print(f"  - signal_latest_effective_date: {signal_latest_effective_date.isoformat() if signal_latest_effective_date else '-'}")

        if current_true_rows:
            print("  - current_true_rows:")
            for row in current_true_rows:
                print(f"      * {row['strategy_code']}: {row['current_true_count']}")
        else:
            print("  - current_true_rows: -")

        print("\n[M4] Strategy refresh chain completed successfully.")
        print("[M4] Next action: run sql/m4_1_acceptance.sql before moving to M5.")
        return 0
    finally:
        inspector.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the M4 strategy refresh chain. "
            "By default, resolve latest_trading_day at runtime and export M4 date env overrides."
        )
    )
    parser.add_argument(
        "--target-date",
        required=False,
        help="Optional manual override target date in YYYY-MM-DD. Default: latest_trading_day from DB.",
    )
    args = parser.parse_args(argv)

    target_date = datetime.strptime(args.target_date, "%Y-%m-%d").date() if args.target_date else None
    return run_m4_strategy_refresh_chain(target_date=target_date)


if __name__ == "__main__":
    raise SystemExit(main())