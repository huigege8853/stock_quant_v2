"""Bootstrap M4 S3 signal preview artifacts.

This script is artifact-only. It reads S2 rule-validation artifacts and writes
S3 signal preview files. It does not write strategy_signal and does not create
M5 backtest requests.
"""

from __future__ import annotations

import argparse
import os
from datetime import date
from pathlib import Path

from stock_quant_v2.strategy_domain.tasks.build_regime_sector_industry_signal_preview import (
    run_build_regime_sector_industry_signal_preview,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build M4 S3 signal preview artifacts from S2 rule-validation outputs.")
    parser.add_argument("--project-root", default=".", help="Project root. The script changes cwd to this path before resolving relative paths.")
    parser.add_argument("--report-date", required=True, help="Report suffix date, for example 2026-05-06.")
    parser.add_argument("--s2-artifact-dir", default="artifacts/m4/strategy_rule_validation", help="Directory containing S2 rule validation artifacts.")
    parser.add_argument("--output-dir", default="artifacts/m4/strategy_signal_preview", help="Output directory for S3 preview artifacts.")
    parser.add_argument("--effective-date", default=None, help="Optional effective date for preview rows. If omitted, actual_trade_date from S2 is used.")
    parser.add_argument("--max-preview-rows", type=int, default=None, help="Optional cap for preview row count.")
    parser.add_argument("--strategy-version-ref", default="regime_sector_industry_selection_v1/S3_PREVIEW", help="Human-readable preview strategy version reference; not a DB id.")
    parser.add_argument("--env-file", default=None, help="Optional dotenv file used to resolve DB URL for v1.1 concept/capital scoring preview.")
    parser.add_argument("--database-url", default=None, help="Optional explicit SQLAlchemy URL for read-only v1.1 enrichment.")
    parser.add_argument("--disable-v1-1-scoring-preview", action="store_true", help="Disable concept/capital read-only enrichment and emit original S3 preview only.")
    return parser.parse_args()


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def main() -> None:
    args = parse_args()
    project_root = Path(args.project_root).resolve()
    os.chdir(project_root)

    def progress(message: str) -> None:
        print(f"[M4_S3_SIGNAL_PREVIEW] {message}", flush=True)

    progress(
        "START "
        f"report_date={args.report_date} "
        f"s2_artifact_dir={Path(args.s2_artifact_dir).resolve()} "
        f"output_dir={Path(args.output_dir).resolve()} "
        f"effective_date={args.effective_date} "
        f"max_preview_rows={args.max_preview_rows} "
        f"v1_1_scoring_preview={not args.disable_v1_1_scoring_preview}"
    )
    task_result = run_build_regime_sector_industry_signal_preview(
        report_date=args.report_date,
        s2_artifact_dir=args.s2_artifact_dir,
        output_dir=args.output_dir,
        effective_date=_parse_date(args.effective_date),
        max_preview_rows=args.max_preview_rows,
        strategy_version_ref=args.strategy_version_ref,
        project_root=project_root,
        env_file=args.env_file,
        database_url=args.database_url,
        enable_v1_1_scoring_preview=not args.disable_v1_1_scoring_preview,
        progress_callback=progress,
    )
    result = task_result.result
    progress(
        "DONE "
        f"status={result.status} "
        f"rows={result.preview_summary.get('signal_preview_row_count')} "
        f"can_start_m4_signal_db_write_design={result.validation_decision.get('can_start_m4_signal_db_write_design')} "
        f"can_write_strategy_signal_now={result.validation_decision.get('can_write_strategy_signal_now')}"
    )
    if result.artifacts:
        progress(f"ARTIFACTS_WRITTEN json={result.artifacts.json_path}")


if __name__ == "__main__":
    main()
