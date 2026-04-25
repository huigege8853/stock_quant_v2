from __future__ import annotations

import argparse
from pathlib import Path

from stock_quant_v2.platform_overview_domain.services.platform_overview_history_check_service import (
    PlatformOverviewHistoryCheckService,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def check_platform_overview_history(
    report_date: str,
    minimum_required_complete_days: int = 2,
) -> dict[str, Path]:
    repo_root = _repo_root()
    service = PlatformOverviewHistoryCheckService(repo_root=repo_root)
    result = service.run(
        report_date=report_date,
        minimum_required_complete_days=minimum_required_complete_days,
    )
    outputs = service.export(result)

    print("[M9.1.1] Platform overview history check completed:")
    print(f"  - requested_report_date: {result.requested_report_date}")
    print(f"  - status: {result.status}")
    print(f"  - latest_available_date: {result.latest_available_date or '-'}")
    print(f"  - previous_complete_date: {result.previous_complete_date or '-'}")
    print(f"  - complete_dates: {', '.join(result.complete_dates) if result.complete_dates else '-'}")

    for name, path in outputs.items():
        print(f"  - {name}: {path}")

    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check whether platform overview artifacts retain enough complete report dates for section 13 comparison."
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

    check_platform_overview_history(
        report_date=args.report_date,
        minimum_required_complete_days=args.min_complete_days,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())