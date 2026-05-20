"""Bootstrap M4 historical signal generation design / preview dry-run.

This script is intentionally a single reusable entry point for the M4 historical
signal generation pipeline while the workflow is being validated:

- mode=design consumes M5 historical request/span design artifacts and produces
  M4 historical signal generation design artifacts.
- mode=preview_dry_run consumes the M4 design artifacts and produces historical
  signal preview rows as files only.
- mode=db_write_preview consumes historical preview rows and produces
  strategy_signal DB-write candidate artifacts only.
- mode=controlled_db_write consumes DB-write candidates and performs an explicit,
  guarded historical strategy_signal write. It skips existing same-version
  date pairs by default.

No mode in this entry point writes M5 request/result rows, executes a backtest,
nor paper-trading records. Only mode=controlled_db_write writes strategy_signal,
and only after db_write_preview has opened the controlled-write gate.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build M4 historical signal generation design or preview dry-run artifacts without DB writes.")
    parser.add_argument("--project-root", default=".", help="Project root. The script changes cwd before resolving relative paths.")
    parser.add_argument("--mode", choices=["design", "preview_dry_run", "db_write_preview", "controlled_db_write"], default="design", help="design keeps the original behavior; preview_dry_run generates historical signal preview rows; db_write_preview creates strategy_signal write candidates without DB writes; controlled_db_write performs an explicit guarded strategy_signal insert.")
    parser.add_argument("--report-date", required=True, help="Report suffix date, for example 2026-05-06.")
    parser.add_argument("--historical-request-artifact-dir", default="artifacts/m5/historical_backtest_request_design", help="Directory containing M5 historical request design artifacts for mode=design.")
    parser.add_argument("--design-artifact-dir", default="artifacts/m4/historical_signal_generation_design", help="Directory containing M4 historical signal generation design artifacts for mode=preview_dry_run.")
    parser.add_argument("--preview-artifact-dir", default="artifacts/m4/historical_signal_generation_preview", help="Directory containing M4 historical signal preview artifacts for mode=db_write_preview.")
    parser.add_argument("--db-write-preview-artifact-dir", default="artifacts/m4/historical_signal_db_write_preview", help="Directory containing M4 historical signal DB write preview artifacts for mode=controlled_db_write.")
    parser.add_argument("--output-dir", default=None, help="Output directory. Defaults depend on mode.")
    parser.add_argument("--strategy-code", default="regime_sector_industry_selection_v1", help="Strategy code for guardrail context.")
    parser.add_argument("--strategy-version-code", default="v1", help="Strategy version code for guardrail context.")
    parser.add_argument("--research-backtest-request-id", type=int, default=None, help="Optional explicit research_backtest_request.id. Defaults to artifact value.")
    parser.add_argument("--benchmark-index-code", default="000300.SH", help="Benchmark index code for dependency context.")
    parser.add_argument("--target-top-n", type=int, default=100, help="Target candidate signals per historical signal date.")
    parser.add_argument("--max-signal-batches", type=int, default=120, help="Maximum signal date batches to process or emit into CSV preview.")
    parser.add_argument("--min-signal-pairs", type=int, default=20, help="Minimum planned signal/effective pairs for PASS-level design readiness.")
    parser.add_argument("--min-preview-rows-per-batch", type=int, default=50, help="Minimum generated historical preview rows per signal date for preview_dry_run.")
    parser.add_argument("--min-candidate-rows", type=int, default=1000, help="Minimum DB-write candidate rows for mode=db_write_preview.")
    parser.add_argument("--max-rows", type=int, default=None, help="Optional cap on source rows for mode=db_write_preview diagnostics.")
    parser.add_argument("--allow-existing-same-version-date", action="store_true", help="Mark existing same-version as_of/effective rows as explicitly reviewed for mode=db_write_preview; this still does not write DB rows.")
    parser.add_argument("--existing-date-policy", choices=["skip", "fail", "append"], default="skip", help="Controlled write policy for same strategy_version/as_of/effective rows. Default skip avoids duplicating already-written preview dates.")
    parser.add_argument("--min-inserted-rows", type=int, default=1000, help="Minimum rows that must be inserted by mode=controlled_db_write.")
    parser.add_argument("--dry-run", action="store_true", help="For mode=controlled_db_write, validate and emit artifacts without inserting strategy_signal rows.")
    parser.add_argument("--feature-set-code", default="fs_daily_alpha_v1", help="M3 feature set code for preview_dry_run.")
    parser.add_argument("--feature-set-version", default="v1", help="M3 feature set version for preview_dry_run.")
    parser.add_argument("--industry-tag-type", default="SW_INDUSTRY_L2", help="Industry taxonomy tag type for preview_dry_run.")
    parser.add_argument("--lookback-days", type=int, default=20, help="Benchmark lookback observations for market regime classification.")
    parser.add_argument(
        "--preview-scoring-mode",
        choices=["base", "cleaned_v1_1"],
        default="base",
        help="preview_dry_run scoring mode. base preserves existing historical preview; cleaned_v1_1 ranks candidates by L7 true-theme + capital activity cleaned preview score.",
    )
    parser.add_argument("--env-file", default=".env.research", help="Environment file to load before importing DB settings.")
    return parser.parse_args()


def _load_env_file(env_file: str | Path) -> bool:
    path = Path(env_file)
    if not path.exists():
        return False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not ((value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'"))):
            value = value.split(" #", 1)[0].strip()
        value = value.strip('"').strip("'")
        if key:
            os.environ[key] = value
    return True


def main() -> None:
    args = parse_args()
    project_root = Path(args.project_root).resolve()
    os.chdir(project_root)
    env_loaded = _load_env_file(args.env_file)
    print(f"ENV_LOADED={Path(args.env_file).resolve() if env_loaded else False}", flush=True)

    from stock_quant_v2.db.session import engine
    from stock_quant_v2.strategy_domain.tasks.build_regime_sector_industry_historical_signal_generation_design import (
        run_build_regime_sector_industry_historical_signal_generation_design,
        run_build_regime_sector_industry_historical_signal_generation_preview,
        run_build_regime_sector_industry_historical_signal_db_write_preview,
        run_build_regime_sector_industry_historical_signal_controlled_db_write,
    )

    if args.mode == "design":
        output_dir = args.output_dir or "artifacts/m4/historical_signal_generation_design"

        def progress(message: str) -> None:
            print(f"[M4_HISTORICAL_SIGNAL_GENERATION_DESIGN] {message}", flush=True)

        progress(
            "START "
            f"mode={args.mode} "
            f"report_date={args.report_date} "
            f"strategy_code={args.strategy_code} "
            f"strategy_version_code={args.strategy_version_code} "
            f"historical_request_artifact_dir={Path(args.historical_request_artifact_dir).resolve()} "
            f"output_dir={Path(output_dir).resolve()} "
            f"request_id={args.research_backtest_request_id or '<artifact>'} "
            f"benchmark_index_code={args.benchmark_index_code} "
            f"target_top_n={args.target_top_n}"
        )
        task_result = run_build_regime_sector_industry_historical_signal_generation_design(
            engine=engine,
            report_date=args.report_date,
            historical_request_artifact_dir=args.historical_request_artifact_dir,
            output_dir=output_dir,
            strategy_code=args.strategy_code,
            strategy_version_code=args.strategy_version_code,
            research_backtest_request_id=args.research_backtest_request_id,
            benchmark_index_code=args.benchmark_index_code,
            target_top_n=args.target_top_n,
            max_signal_batches=args.max_signal_batches,
            min_signal_pairs=args.min_signal_pairs,
            progress_callback=progress,
        )
        result = task_result.result
        progress(
            "DONE "
            f"status={result.status} "
            f"request_id={result.research_backtest_request_id} "
            f"source_signal_run_id={result.source_signal_run_id} "
            f"planned_pairs={result.summary.get('planned_signal_pair_count')} "
            f"expected_signal_rows={result.summary.get('expected_signal_rows')} "
            f"can_start_preview_dry_run={result.validation_decision.get('can_start_m4_historical_signal_generation_preview_dry_run')} "
            f"can_execute_backtest_now={result.validation_decision.get('can_execute_backtest_now')} "
            f"blockers={result.validation_decision.get('blocker_count')}"
        )
        if result.artifacts:
            progress(f"ARTIFACTS_WRITTEN json={result.artifacts.json_path}")
        return



    if args.mode == "controlled_db_write":
        output_dir = args.output_dir or "artifacts/m4/historical_signal_controlled_db_write"

        def controlled_write_progress(message: str) -> None:
            print(f"[M4_HISTORICAL_SIGNAL_CONTROLLED_DB_WRITE] {message}", flush=True)

        controlled_write_progress(
            "START "
            f"mode={args.mode} "
            f"report_date={args.report_date} "
            f"strategy_code={args.strategy_code} "
            f"strategy_version_code={args.strategy_version_code} "
            f"db_write_preview_artifact_dir={Path(args.db_write_preview_artifact_dir).resolve()} "
            f"output_dir={Path(output_dir).resolve()} "
            f"request_id={args.research_backtest_request_id or '<artifact>'} "
            f"benchmark_index_code={args.benchmark_index_code} "
            f"existing_date_policy={args.existing_date_policy} "
            f"min_inserted_rows={args.min_inserted_rows} "
            f"dry_run={args.dry_run}"
        )
        task_result = run_build_regime_sector_industry_historical_signal_controlled_db_write(
            engine=engine,
            report_date=args.report_date,
            db_write_preview_artifact_dir=args.db_write_preview_artifact_dir,
            output_dir=output_dir,
            strategy_code=args.strategy_code,
            strategy_version_code=args.strategy_version_code,
            research_backtest_request_id=args.research_backtest_request_id,
            benchmark_index_code=args.benchmark_index_code,
            min_inserted_rows=args.min_inserted_rows,
            max_rows=args.max_rows,
            existing_date_policy=args.existing_date_policy,
            dry_run=args.dry_run,
            progress_callback=controlled_write_progress,
        )
        result = task_result.result
        controlled_write_progress(
            "DONE "
            f"status={result.status} "
            f"request_id={result.research_backtest_request_id} "
            f"ops_run_id={result.summary.get('ops_run_id')} "
            f"candidate_rows={result.summary.get('candidate_row_count')} "
            f"inserted_rows={result.summary.get('inserted_row_count')} "
            f"skipped_existing_rows={result.summary.get('skipped_existing_row_count')} "
            f"can_start_m5_request_write_preview={result.validation_decision.get('can_start_m5_historical_backtest_request_write_preview')} "
            f"can_execute_backtest_now={result.validation_decision.get('can_execute_backtest_now')} "
            f"blockers={result.validation_decision.get('blocker_count')}"
        )
        if result.artifacts:
            controlled_write_progress(f"ARTIFACTS_WRITTEN json={result.artifacts.json_path}")
        return

    if args.mode == "db_write_preview":
        output_dir = args.output_dir or "artifacts/m4/historical_signal_db_write_preview"

        def write_preview_progress(message: str) -> None:
            print(f"[M4_HISTORICAL_SIGNAL_DB_WRITE_PREVIEW] {message}", flush=True)

        write_preview_progress(
            "START "
            f"mode={args.mode} "
            f"report_date={args.report_date} "
            f"strategy_code={args.strategy_code} "
            f"strategy_version_code={args.strategy_version_code} "
            f"preview_artifact_dir={Path(args.preview_artifact_dir).resolve()} "
            f"output_dir={Path(output_dir).resolve()} "
            f"request_id={args.research_backtest_request_id or '<artifact>'} "
            f"benchmark_index_code={args.benchmark_index_code} "
            f"min_candidate_rows={args.min_candidate_rows} "
            f"allow_existing_same_version_date={args.allow_existing_same_version_date}"
        )
        task_result = run_build_regime_sector_industry_historical_signal_db_write_preview(
            engine=engine,
            report_date=args.report_date,
            preview_artifact_dir=args.preview_artifact_dir,
            output_dir=output_dir,
            strategy_code=args.strategy_code,
            strategy_version_code=args.strategy_version_code,
            research_backtest_request_id=args.research_backtest_request_id,
            benchmark_index_code=args.benchmark_index_code,
            min_candidate_rows=args.min_candidate_rows,
            max_rows=args.max_rows,
            allow_existing_same_version_date=args.allow_existing_same_version_date,
            progress_callback=write_preview_progress,
        )
        result = task_result.result
        write_preview_progress(
            "DONE "
            f"status={result.status} "
            f"request_id={result.research_backtest_request_id} "
            f"candidate_rows={result.summary.get('candidate_row_count')} "
            f"distinct_as_of_dates={result.summary.get('distinct_as_of_dates')} "
            f"existing_same_version_rows={result.summary.get('existing_signal_rows_same_version_dates')} "
            f"can_start_controlled_db_write={result.validation_decision.get('can_start_m4_historical_signal_controlled_db_write')} "
            f"can_write_strategy_signal_now={result.validation_decision.get('can_write_strategy_signal_now')} "
            f"can_execute_backtest_now={result.validation_decision.get('can_execute_backtest_now')} "
            f"blockers={result.validation_decision.get('blocker_count')}"
        )
        if result.artifacts:
            write_preview_progress(f"ARTIFACTS_WRITTEN json={result.artifacts.json_path}")
        return

    output_dir = args.output_dir or "artifacts/m4/historical_signal_generation_preview"

    def preview_progress(message: str) -> None:
        print(f"[M4_HISTORICAL_SIGNAL_GENERATION_PREVIEW] {message}", flush=True)

    preview_progress(
        "START "
        f"mode={args.mode} "
        f"report_date={args.report_date} "
        f"strategy_code={args.strategy_code} "
        f"strategy_version_code={args.strategy_version_code} "
        f"design_artifact_dir={Path(args.design_artifact_dir).resolve()} "
        f"output_dir={Path(output_dir).resolve()} "
        f"request_id={args.research_backtest_request_id or '<artifact>'} "
        f"benchmark_index_code={args.benchmark_index_code} "
        f"target_top_n={args.target_top_n} "
        f"max_signal_batches={args.max_signal_batches} "
        f"preview_scoring_mode={args.preview_scoring_mode}"
    )
    task_result = run_build_regime_sector_industry_historical_signal_generation_preview(
        engine=engine,
        report_date=args.report_date,
        design_artifact_dir=args.design_artifact_dir,
        output_dir=output_dir,
        strategy_code=args.strategy_code,
        strategy_version_code=args.strategy_version_code,
        research_backtest_request_id=args.research_backtest_request_id,
        benchmark_index_code=args.benchmark_index_code,
        target_top_n=args.target_top_n,
        max_signal_batches=args.max_signal_batches,
        min_preview_rows_per_batch=args.min_preview_rows_per_batch,
        feature_set_code=args.feature_set_code,
        feature_set_version=args.feature_set_version,
        industry_tag_type=args.industry_tag_type,
        lookback_days=args.lookback_days,
        preview_scoring_mode=args.preview_scoring_mode,
        progress_callback=preview_progress,
    )
    result = task_result.result
    preview_progress(
        "DONE "
        f"status={result.status} "
        f"request_id={result.research_backtest_request_id} "
        f"processed_pairs={result.summary.get('processed_signal_pair_count')} "
        f"preview_rows={result.summary.get('preview_signal_row_count')} "
        f"zero_row_batches={result.summary.get('zero_row_batch_count')} "
        f"preview_scoring_mode={result.summary.get('preview_scoring_mode')} "
        f"cleaned_v1_1_score_count={result.summary.get('cleaned_v1_1_score_count')} "
        f"can_start_db_write_preview={result.validation_decision.get('can_start_m4_historical_signal_db_write_preview')} "
        f"can_execute_backtest_now={result.validation_decision.get('can_execute_backtest_now')} "
        f"blockers={result.validation_decision.get('blocker_count')}"
    )
    if result.artifacts:
        preview_progress(f"ARTIFACTS_WRITTEN json={result.artifacts.json_path}")


if __name__ == "__main__":
    main()
