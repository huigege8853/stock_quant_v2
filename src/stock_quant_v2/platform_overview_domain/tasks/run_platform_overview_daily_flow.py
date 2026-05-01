from __future__ import annotations

import argparse
from pathlib import Path

from stock_quant_v2.platform_overview_domain.tasks.build_platform_overview_report import (
    build_platform_overview_report,
)
from stock_quant_v2.platform_overview_domain.tasks.build_upstream_readiness_summaries import (
    build_upstream_readiness_summaries,
)
from stock_quant_v2.platform_overview_domain.tasks.check_platform_overview_history import (
    check_platform_overview_history,
)


def run_platform_overview_daily_flow(
    report_date: str,
    minimum_required_complete_days: int = 2,
    build_upstream_summaries: bool = True,
    db_url: str | None = None,
    continue_on_upstream_error: bool = True,
) -> dict[str, dict[str, Path] | dict[str, str]]:
    """Run the M9.1.1 daily platform overview flow.

    Current daily flow order:
    1. Build M3/M4/M5 lightweight upstream bridge summaries when enabled.
    2. Build the 15-section platform overview report from artifacts.
    3. Check platform overview history retention for section 13.

    Upstream summaries are best-effort by default because M9.1.1 is an
    explanation layer and must not block the daily runtime chain when a DB fact
    source is temporarily unavailable. Use ``--fail-on-upstream-error`` when a
    strict acceptance run should fail fast instead.
    """

    outputs: dict[str, dict[str, Path] | dict[str, str]] = {}

    if build_upstream_summaries:
        try:
            outputs["upstream_summaries"] = build_upstream_readiness_summaries(
                report_date=report_date,
                db_url=db_url,
            )
        except Exception as exc:
            error_payload = {
                "status": "WARN",
                "message": (
                    "upstream summaries failed; continued with existing artifacts "
                    "because continue_on_upstream_error=true"
                ),
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            outputs["upstream_summaries"] = error_payload
            if not continue_on_upstream_error:
                raise
            print("[M9.1.1][WARN] Upstream summaries failed; continuing with existing artifacts.")
            print(f"[M9.1.1][WARN] {type(exc).__name__}: {exc}")
    else:
        outputs["upstream_summaries"] = {
            "status": "SKIPPED",
            "message": "upstream summaries skipped by CLI flag",
        }

    overview_outputs = build_platform_overview_report(report_date=report_date)
    history_outputs = check_platform_overview_history(
        report_date=report_date,
        minimum_required_complete_days=minimum_required_complete_days,
    )

    outputs["platform_overview"] = overview_outputs
    outputs["history_check"] = history_outputs

    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the M9.1.1 daily flow: build upstream bridge summaries, "
            "build platform overview, then check platform overview history."
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
    parser.add_argument(
        "--db-url",
        type=str,
        default=None,
        help="Explicit database URL for upstream bridge summaries.",
    )
    parser.add_argument(
        "--skip-upstream-summaries",
        action="store_true",
        help="Skip M3/M4/M5 upstream bridge summaries and use existing artifacts only.",
    )
    parser.add_argument(
        "--fail-on-upstream-error",
        action="store_true",
        help="Fail the daily flow if upstream bridge summary generation fails.",
    )
    args = parser.parse_args(argv)

    outputs = run_platform_overview_daily_flow(
        report_date=args.report_date,
        minimum_required_complete_days=args.min_complete_days,
        build_upstream_summaries=not args.skip_upstream_summaries,
        db_url=args.db_url,
        continue_on_upstream_error=not args.fail_on_upstream_error,
    )

    print("[M9.1.1] Daily flow completed:")
    print(f"  - report_date: {args.report_date}")
    print("  - steps:")
    if args.skip_upstream_summaries:
        print("    1) skip upstream bridge summaries")
    else:
        print("    1) build upstream bridge summaries")
    print("    2) build platform overview")
    print("    3) check platform overview history")

    for group_name, group_outputs in outputs.items():
        print(f"  - {group_name}:")
        for output_name, output_path in group_outputs.items():
            print(f"      - {output_name}: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
