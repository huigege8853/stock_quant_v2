from __future__ import annotations

import argparse
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from stock_quant_v2.platform_overview_domain.tasks.run_platform_overview_daily_flow import (
    run_platform_overview_daily_flow,
)


def _resolve_report_date(cli_report_date: str | None = None) -> str:
    if cli_report_date:
        return cli_report_date

    for env_name in ("M9_REPORT_DATE", "M8_REPORT_DATE", "REPORT_DATE"):
        value = os.getenv(env_name)
        if value:
            return value

    tz_name = os.getenv("APP_TIMEZONE", os.getenv("TZ", "Asia/Shanghai"))
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Asia/Shanghai")
    return datetime.now(tz).date().isoformat()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Stable M9 DailyRun entrypoint. It runs the M9.1.1 platform overview "
            "daily flow without exposing bootstrap/p-stage script names to scheduler code."
        )
    )
    parser.add_argument("--report-date", type=str, default=None, help="Report date in YYYY-MM-DD. Default: M9_REPORT_DATE, M8_REPORT_DATE, REPORT_DATE, or local date.")
    parser.add_argument("--min-complete-days", type=int, default=int(os.getenv("M9_MIN_COMPLETE_DAYS", "2")), help="Minimum complete overview days for history check. Default: 2.")
    parser.add_argument("--db-url", type=str, default=os.getenv("M9_DATABASE_URL"), help="Optional explicit database URL for upstream bridge summaries.")
    parser.add_argument("--skip-upstream-summaries", action="store_true", default=os.getenv("M9_SKIP_UPSTREAM_SUMMARIES", "").lower() in {"1", "true", "yes", "y"}, help="Skip M3/M4/M5 upstream bridge summaries and use existing artifacts only.")
    parser.add_argument("--fail-on-upstream-error", action="store_true", default=os.getenv("M9_FAIL_ON_UPSTREAM_ERROR", "").lower() in {"1", "true", "yes", "y"}, help="Fail if upstream summary generation fails. Default is best-effort/non-blocking.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    report_date = _resolve_report_date(args.report_date)

    outputs = run_platform_overview_daily_flow(
        report_date=report_date,
        minimum_required_complete_days=args.min_complete_days,
        build_upstream_summaries=not args.skip_upstream_summaries,
        db_url=args.db_url,
        continue_on_upstream_error=not args.fail_on_upstream_error,
    )

    print("[M9] Daily ops chain completed:")
    print(f"  - report_date: {report_date}")
    print(f"  - min_complete_days: {args.min_complete_days}")
    print(f"  - skip_upstream_summaries: {args.skip_upstream_summaries}")
    print(f"  - fail_on_upstream_error: {args.fail_on_upstream_error}")
    for group_name, group_outputs in outputs.items():
        print(f"  - {group_name}:")
        for output_name, output_value in group_outputs.items():
            print(f"      - {output_name}: {output_value}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
