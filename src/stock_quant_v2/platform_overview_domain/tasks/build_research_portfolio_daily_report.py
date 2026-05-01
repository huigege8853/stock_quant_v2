from __future__ import annotations

import argparse
from pathlib import Path

from stock_quant_v2.platform_overview_domain.services.research_portfolio_daily_report_builder import (
    ResearchPortfolioDailyReportBuilder,
    ResearchPortfolioDailyReportExporter,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def build_research_portfolio_daily_report(report_date: str) -> dict[str, Path]:
    repo_root = _repo_root()
    builder = ResearchPortfolioDailyReportBuilder(repo_root=repo_root)
    report = builder.build_report(report_date=report_date)
    exporter = ResearchPortfolioDailyReportExporter(
        output_dir=repo_root / "artifacts" / "m9" / "research_portfolio_daily"
    )
    return exporter.export(report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build M9.1.1-B research / portfolio daily report from M3/M4/M5/M8 artifacts."
        )
    )
    parser.add_argument(
        "--report-date",
        type=str,
        required=True,
        help="Report date in YYYY-MM-DD.",
    )
    args = parser.parse_args(argv)

    outputs = build_research_portfolio_daily_report(report_date=args.report_date)

    print("[M9.1.1-B] Research / portfolio daily report generated:")
    print(f"  - report_date: {args.report_date}")
    for name, path in outputs.items():
        print(f"  - {name}: {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
