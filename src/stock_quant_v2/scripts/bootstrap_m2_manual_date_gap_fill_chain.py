from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from stock_quant_v2.config.settings import settings


@dataclass(frozen=True)
class DateGapTopic:
    name: str
    module_name: str
    enabled_by_default: bool = True


CALENDAR_BOOTSTRAP_MODULE = "stock_quant_v2.scripts.bootstrap_instrument_calendar"

CORE_TOPICS: list[DateGapTopic] = [
    DateGapTopic(
        name="daily_bar",
        module_name="stock_quant_v2.scripts.bootstrap_daily_bar_first_chain",
        enabled_by_default=True,
    ),
    DateGapTopic(
        name="adjust_factor",
        module_name="stock_quant_v2.scripts.backfill_adjust_factor_history",
        enabled_by_default=True,
    ),
]

OPTIONAL_TOPICS: list[DateGapTopic] = [
    DateGapTopic(
        name="instrument_status_daily",
        module_name="stock_quant_v2.scripts.bootstrap_instrument_status_daily_first_chain",
        enabled_by_default=False,
    ),
    DateGapTopic(
        name="price_limit_daily",
        module_name="stock_quant_v2.scripts.bootstrap_price_limit_daily_first_chain",
        enabled_by_default=False,
    ),
    DateGapTopic(
        name="market_index_bar",
        module_name="stock_quant_v2.scripts.bootstrap_market_index_first_chain",
        enabled_by_default=False,
    ),
    DateGapTopic(
        name="fundamental_snapshot",
        module_name="stock_quant_v2.scripts.bootstrap_fundamental_snapshot_first_chain",
        enabled_by_default=False,
    ),
]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _run_module(module_name: str, extra_env: dict[str, str] | None = None) -> int:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)

    cmd = [sys.executable, "-m", module_name]
    completed = subprocess.run(cmd, cwd=_project_root(), env=env)
    return int(completed.returncode)


def _resolve_topics(
    include_status: bool,
    include_price_limit: bool,
    include_market_index: bool,
    include_fundamental: bool,
) -> list[DateGapTopic]:
    topics = list(CORE_TOPICS)

    if include_status:
        topics.append(
            next(topic for topic in OPTIONAL_TOPICS if topic.name == "instrument_status_daily")
        )
    if include_price_limit:
        topics.append(
            next(topic for topic in OPTIONAL_TOPICS if topic.name == "price_limit_daily")
        )
    if include_market_index:
        topics.append(
            next(topic for topic in OPTIONAL_TOPICS if topic.name == "market_index_bar")
        )
    if include_fundamental:
        topics.append(
            next(topic for topic in OPTIONAL_TOPICS if topic.name == "fundamental_snapshot")
        )

    return topics


def run_m2_manual_date_gap_fill_chain(
    start_date: date,
    end_date: date,
    include_status: bool = False,
    include_price_limit: bool = False,
    include_market_index: bool = False,
    include_fundamental: bool = False,
    skip_calendar: bool = False,
) -> int:
    if start_date > end_date:
        print("[M2-REPAIR] Invalid range: start_date > end_date")
        return 2

    print("[M2-REPAIR] Manual date gap fill chain started.")
    print(f"[M2-REPAIR] Using database URL: {settings.postgres_v2_url}")
    print(f"[M2-REPAIR] Manual date range: {start_date.isoformat()} -> {end_date.isoformat()}")

    topics = _resolve_topics(
        include_status=include_status,
        include_price_limit=include_price_limit,
        include_market_index=include_market_index,
        include_fundamental=include_fundamental,
    )

    if not skip_calendar:
        print(f"\n[M2-REPAIR] Pre-step starting: {CALENDAR_BOOTSTRAP_MODULE}")
        rc = _run_module(CALENDAR_BOOTSTRAP_MODULE)
        if rc != 0:
            print(f"[M2-REPAIR] Pre-step failed: {CALENDAR_BOOTSTRAP_MODULE} (exit_code={rc})")
            return rc
        print(f"[M2-REPAIR] Pre-step succeeded: {CALENDAR_BOOTSTRAP_MODULE}")
    else:
        print("\n[M2-REPAIR] skip_calendar=true, bootstrap_instrument_calendar skipped.")

    for topic in topics:
        print(
            f"\n[M2-REPAIR][{topic.name}] date-gap fill: "
            f"{start_date.isoformat()} -> {end_date.isoformat()} | module={topic.module_name}"
        )
        rc = _run_module(
            topic.module_name,
            extra_env={
                "BOOTSTRAP_DAILY_BAR_START_DATE": start_date.isoformat(),
                "BOOTSTRAP_DAILY_BAR_END_DATE": end_date.isoformat(),
            },
        )
        if rc != 0:
            print(f"[M2-REPAIR][{topic.name}] failed (exit_code={rc})")
            print("[M2-REPAIR] Chain stopped. Fix this topic before rerunning downstream modules.")
            return rc

        print(f"[M2-REPAIR][{topic.name}] succeeded.")

    print("\n[M2-REPAIR] Manual date gap fill chain completed successfully.")
    print("[M2-REPAIR] Suggested next action: run sql/m2_2_acceptance.sql if this repair affects the current working window.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the M2 manual date-gap fill chain. "
            "Default range comes from settings.bootstrap_daily_bar_start_date / end_date. "
            "CLI dates are optional overrides."
        )
    )
    parser.add_argument(
        "--start-date",
        required=False,
        help="Optional override start date in YYYY-MM-DD. Default: settings.bootstrap_daily_bar_start_date",
    )
    parser.add_argument(
        "--end-date",
        required=False,
        help="Optional override end date in YYYY-MM-DD. Default: settings.bootstrap_daily_bar_end_date",
    )
    parser.add_argument(
        "--include-status",
        action="store_true",
        help="Also run instrument_status_daily date-gap fill.",
    )
    parser.add_argument(
        "--include-price-limit",
        action="store_true",
        help="Also run price_limit_daily date-gap fill.",
    )
    parser.add_argument(
        "--include-market-index",
        action="store_true",
        help="Also run market_index_bar date-gap fill.",
    )
    parser.add_argument(
        "--include-fundamental",
        action="store_true",
        help="Also run fundamental_snapshot date-gap fill.",
    )
    parser.add_argument(
        "--skip-calendar",
        action="store_true",
        help="Skip bootstrap_instrument_calendar pre-step.",
    )

    args = parser.parse_args(argv)

    start_date = _parse_date(args.start_date) if args.start_date else settings.bootstrap_daily_bar_start_date
    end_date = _parse_date(args.end_date) if args.end_date else settings.bootstrap_daily_bar_end_date

    return run_m2_manual_date_gap_fill_chain(
        start_date=start_date,
        end_date=end_date,
        include_status=args.include_status,
        include_price_limit=args.include_price_limit,
        include_market_index=args.include_market_index,
        include_fundamental=args.include_fundamental,
        skip_calendar=args.skip_calendar,
    )


if __name__ == "__main__":
    raise SystemExit(main())