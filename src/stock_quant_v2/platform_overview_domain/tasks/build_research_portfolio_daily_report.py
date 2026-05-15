from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from sqlalchemy import text

from stock_quant_v2.platform_overview_domain.services.research_portfolio_daily_report_builder import (
    ProductionObservationReportExporter,
    ResearchPortfolioDailyReportBuilder,
    ResearchPortfolioDailyReportExporter,
    ResearchStrategySnapshotExporter,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]



def _resolve_report_date(repo_root: Path, report_date: str | None) -> str:
    if report_date:
        return report_date

    try:
        from stock_quant_v2.db.session import SessionLocal, dispose_engine

        with SessionLocal() as session:
            value = session.execute(
                text(
                    """
                    select max(trade_date)::text
                    from public.core_daily_bar
                    where price_adjust_type = 'RAW'
                    """
                )
            ).scalar_one_or_none()
        dispose_engine()
        if value:
            return str(value)
    except Exception:
        pass

    return date.today().isoformat()


def build_research_portfolio_daily_report(report_date: str | None = None) -> dict[str, Path]:
    repo_root = _repo_root()
    report_date = _resolve_report_date(repo_root, report_date)
    builder = ResearchPortfolioDailyReportBuilder(repo_root=repo_root)
    report = builder.build_report(report_date=report_date)
    exporter = ResearchPortfolioDailyReportExporter(
        output_dir=repo_root / "artifacts" / "m9" / "research_portfolio_daily"
    )
    outputs = exporter.export(report)

    snapshot_exporter = ResearchStrategySnapshotExporter(
        repo_root=repo_root,
        output_dir=repo_root / "artifacts" / "m9" / "research_strategy_snapshot",
        overview_output_dir=repo_root / "overview",
    )
    outputs.update(snapshot_exporter.export(report))

    production_exporter = ProductionObservationReportExporter(
        output_dir=repo_root / "artifacts" / "m9" / "production_observation"
    )
    outputs.update(production_exporter.export(report))
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build M9.1.1-B research / portfolio daily report from M3/M4/M5/M8 artifacts."
        )
    )
    parser.add_argument(
        "--report-date",
        type=str,
        default=None,
        help="Report date in YYYY-MM-DD. Default: latest RAW core_daily_bar trade_date, then today.",
    )
    args = parser.parse_args(argv)

    repo_root = _repo_root()
    resolved_report_date = _resolve_report_date(repo_root, args.report_date)
    outputs = build_research_portfolio_daily_report(report_date=resolved_report_date)

    print("[M9.1.1-B] Research / portfolio / production observation daily report generated:")
    print(f"  - report_date: {resolved_report_date}")
    for name, path in outputs.items():
        print(f"  - {name}: {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
