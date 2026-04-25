from __future__ import annotations

import argparse
from pathlib import Path

from stock_quant_v2.platform_overview_domain.tasks.build_platform_overview_report import (
    build_platform_overview_report,
)
from stock_quant_v2.platform_overview_domain.tasks.check_platform_overview_history import (
    check_platform_overview_history,
)


def run_platform_overview_daily_flow(
    report_date: str,
    minimum_required_complete_days: int = 2,
) -> dict[str, dict[str, Path]]:
    overview_outputs = build_platform_overview_report(report_date=report_date)
    history_outputs = check_platform_overview_history(
        report_date=report_date,
        minimum_required_complete_days=minimum_required_complete_days,
    )

    return {
        "platform_overview": overview_outputs,
        "history_check": history_outputs,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the M9.1.1 daily flow: build platform overview first, "
            "then run the platform overview history check."
        )
    )
    parser.add_argument(
        "--report-date",
        type=str,
        required=True,
        help="Report date in YYYY-MM-DD.",
    )
    parser.add_argument(
        "--min-complete-days",
        type=int,
        default=2,
        help="Minimum number of complete report dates required. Default: 2",
    )
    args = parser.parse_args(argv)

    outputs = run_platform_overview_daily_flow(
        report_date=args.report_date,
        minimum_required_complete_days=args.min_complete_days,
    )

    print("[M9.1.1] Daily flow completed:")
    print(f"  - report_date: {args.report_date}")
    print("  - steps:")
    print("    1) build platform overview")
    print("    2) check platform overview history")

    for group_name, group_outputs in outputs.items():
        print(f"  - {group_name}:")
        for output_name, output_path in group_outputs.items():
            print(f"      - {output_name}: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())