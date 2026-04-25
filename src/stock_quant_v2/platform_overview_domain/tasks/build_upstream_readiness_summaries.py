from __future__ import annotations

import argparse
from pathlib import Path

from stock_quant_v2.platform_overview_domain.services.upstream_summary_builder import (
    UpstreamSummaryBuilder,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def build_upstream_readiness_summaries(
    report_date: str,
    db_url: str | None = None,
) -> dict[str, dict[str, Path]]:
    repo_root = _repo_root()
    builder = UpstreamSummaryBuilder(repo_root=repo_root, db_url=db_url)
    return builder.build_all(report_date=report_date)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build M3/M4 upstream summaries for M9.1.1 platform overview consumption."
    )
    parser.add_argument(
        "--report-date",
        type=str,
        required=True,
        help="Report date in YYYY-MM-DD.",
    )
    parser.add_argument(
        "--db-url",
        type=str,
        default=None,
        help="Explicit database URL.",
    )
    args = parser.parse_args(argv)

    outputs = build_upstream_readiness_summaries(
        report_date=args.report_date,
        db_url=args.db_url,
    )

    print("[M9.1.1] Upstream summaries generated:")
    for group_name, group_outputs in outputs.items():
        print(f"  - {group_name}:")
        for output_name, output_path in group_outputs.items():
            print(f"      - {output_name}: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())