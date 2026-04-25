from __future__ import annotations

import argparse
from pathlib import Path

from stock_quant_v2.platform_overview_domain.readers.platform_overview_artifact_reader import (
    PlatformOverviewArtifactReader,
)
from stock_quant_v2.platform_overview_domain.services.platform_overview_report_builder import (
    PlatformOverviewExporter,
    PlatformOverviewReportBuilder,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def build_platform_overview_report(report_date: str | None = None) -> dict[str, Path]:
    repo_root = _repo_root()

    reader = PlatformOverviewArtifactReader(repo_root=repo_root)
    builder = PlatformOverviewReportBuilder(repo_root=repo_root, reader=reader)
    report = builder.build_report(report_date=report_date)

    exporter = PlatformOverviewExporter(
        output_dir=repo_root / "artifacts" / "m9" / "platform_overview"
    )
    return exporter.export(report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build M9.1.1 platform overview report from M8/M5 artifacts."
    )
    parser.add_argument(
        "--report-date",
        type=str,
        default=None,
        help="Report date in YYYY-MM-DD. Default: auto-detect from sources.",
    )
    args = parser.parse_args(argv)

    outputs = build_platform_overview_report(report_date=args.report_date)

    print("[M9.1.1] Platform overview report generated:")
    for name, path in outputs.items():
        print(f"  - {name}: {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())