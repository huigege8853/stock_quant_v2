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
class M3Topic:
    name: str
    module_name: str


M3_TOPICS: list[M3Topic] = [
    M3Topic(
        name="indicator",
        module_name="stock_quant_v2.scripts.bootstrap_m3_indicator_chain",
    ),
    M3Topic(
        name="factor",
        module_name="stock_quant_v2.scripts.bootstrap_m3_factor_chain",
    ),
    M3Topic(
        name="feature",
        module_name="stock_quant_v2.scripts.bootstrap_m3_feature_chain",
    ),
    M3Topic(
        name="label",
        module_name="stock_quant_v2.scripts.bootstrap_m3_label_chain",
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

    def max_date(self, table_name: str, date_column: str) -> date | None:
        value = self._safe_scalar(f"SELECT MAX({date_column}) FROM {table_name}")
        return self._coerce_to_date(value)

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


def _build_m3_env(target_date: date) -> dict[str, str]:
    target = target_date.isoformat()
    return {
        "M3_INDICATOR_TRADE_DATE": target,
        "M3_FACTOR_TRADE_DATE": target,
        "M3_FEATURE_TRADE_DATE": target,
        "M3_LABEL_ANCHOR_DATE": target,
    }


def run_m3_analytics_refresh_chain(
    indicator_only: bool = False,
    factor_only: bool = False,
    feature_only: bool = False,
    label_only: bool = False,
    target_date: date | None = None,
) -> int:
    inspector = DatabaseInspector(str(settings.postgres_v2_url))
    try:
        print("[M3] Analytics refresh chain started.")
        print(f"[M3] Using database URL: {settings.postgres_v2_url}")

        latest_trading_day = target_date or inspector.latest_trading_day()
        if latest_trading_day is None:
            print("[M3] Failed to resolve latest_trading_day. Please make sure M2 calendar / daily_bar is ready.")
            return 2

        print(f"[M3] latest_trading_day = {latest_trading_day.isoformat()}")

        env_overrides = _build_m3_env(latest_trading_day)
        print("[M3] Effective env overrides:")
        for k, v in env_overrides.items():
            print(f"  - {k}={v}")

        selected_topics = list(M3_TOPICS)

        flags = [indicator_only, factor_only, feature_only, label_only]
        if any(flags):
            selected_topics = []
            if indicator_only:
                selected_topics.append(next(t for t in M3_TOPICS if t.name == "indicator"))
            if factor_only:
                selected_topics.append(next(t for t in M3_TOPICS if t.name == "factor"))
            if feature_only:
                selected_topics.append(next(t for t in M3_TOPICS if t.name == "feature"))
            if label_only:
                selected_topics.append(next(t for t in M3_TOPICS if t.name == "label"))

        for topic in selected_topics:
            print(f"\n[M3][{topic.name}] starting: {topic.module_name}")
            rc = _run_module(topic.module_name, extra_env=env_overrides)
            if rc != 0:
                print(f"[M3][{topic.name}] failed (exit_code={rc})")
                print("[M3] Chain stopped. Fix this topic before moving to M4.")
                return rc
            print(f"[M3][{topic.name}] succeeded.")

        # 只做轻量观察，不在这里阻塞
        indicator_max = inspector.max_date("analytics_instrument_indicator_snapshot", "trade_date")
        factor_max = inspector.max_date("analytics_factor_snapshot", "trade_date")
        feature_max = inspector.max_date("analytics_feature_snapshot", "trade_date")
        label_max = inspector.max_date("analytics_label_snapshot", "trade_date")

        print("\n[M3] Snapshot max dates after refresh:")
        print(f"  - indicator_snapshot: {indicator_max.isoformat() if indicator_max else '-'}")
        print(f"  - factor_snapshot: {factor_max.isoformat() if factor_max else '-'}")
        print(f"  - feature_snapshot: {feature_max.isoformat() if feature_max else '-'}")
        print(f"  - label_snapshot: {label_max.isoformat() if label_max else '-'}")

        print("\n[M3] Analytics refresh chain completed successfully.")
        print("[M3] Next action: run sql/m3_1_acceptance.sql before moving to M4.")
        return 0
    finally:
        inspector.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the M3 analytics refresh chain. "
            "By default, resolve latest trading day at runtime and use it to override "
            "M3_INDICATOR_TRADE_DATE / M3_FACTOR_TRADE_DATE / "
            "M3_FEATURE_TRADE_DATE / M3_LABEL_ANCHOR_DATE."
        )
    )
    parser.add_argument(
        "--target-date",
        required=False,
        help="Optional manual override target date in YYYY-MM-DD. Default: latest_trading_day from DB.",
    )
    parser.add_argument(
        "--indicator-only",
        action="store_true",
        help="Run only indicator chain.",
    )
    parser.add_argument(
        "--factor-only",
        action="store_true",
        help="Run only factor chain.",
    )
    parser.add_argument(
        "--feature-only",
        action="store_true",
        help="Run only feature chain.",
    )
    parser.add_argument(
        "--label-only",
        action="store_true",
        help="Run only label chain.",
    )

    args = parser.parse_args(argv)

    target_date = datetime.strptime(args.target_date, "%Y-%m-%d").date() if args.target_date else None

    return run_m3_analytics_refresh_chain(
        indicator_only=args.indicator_only,
        factor_only=args.factor_only,
        feature_only=args.feature_only,
        label_only=args.label_only,
        target_date=target_date,
    )


if __name__ == "__main__":
    raise SystemExit(main())