"""Build contract artifacts and optionally write preview-scope M4 strategy_signal rows.

Default mode is dry-run only. DB write requires both:
- --write-db
- --write-confirmation PREVIEW_SCOPE_ONLY
"""

from __future__ import annotations

import argparse
import os
from datetime import date
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert S3 preview artifacts into a guarded strategy_signal DB-write contract.")
    parser.add_argument("--project-root", default=".", help="Project root. The script changes cwd before resolving relative paths.")
    parser.add_argument("--report-date", required=True, help="Report suffix date, for example 2026-05-15.")
    parser.add_argument("--preview-artifact-dir", default="artifacts/m4/strategy_signal_preview_v1_1", help="Directory containing S3 preview artifacts.")
    parser.add_argument("--output-dir", default="artifacts/m4/strategy_signal_db_write_contract", help="Output directory for contract/write artifacts.")
    parser.add_argument("--strategy-code", default="regime_sector_industry_selection_v1", help="Strategy code to resolve.")
    parser.add_argument("--strategy-version-code", default="v1", help="Strategy version code to resolve.")
    parser.add_argument("--effective-date", default=None, help="Optional DB effective_date override. Default uses report_date when it is after as_of_date.")
    parser.add_argument("--write-db", action="store_true", help="Actually insert preview-scope rows into strategy_signal. Omit for dry-run only.")
    parser.add_argument("--write-confirmation", default="", help="Must equal PREVIEW_SCOPE_ONLY when --write-db is supplied.")
    parser.add_argument("--allow-existing-same-version-date", action="store_true", help="Allow append-new-run when rows already exist for same strategy version/date. Default blocks append.")
    parser.add_argument("--max-rows", type=int, default=None, help="Optional cap for smoke tests.")
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
        if key and key not in os.environ:
            os.environ[key] = value
    return True


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value[:10])


def main() -> None:
    args = parse_args()
    project_root = Path(args.project_root).resolve()
    os.chdir(project_root)
    env_loaded = _load_env_file(args.env_file)
    print(f"ENV_LOADED={Path(args.env_file).resolve() if env_loaded else False}", flush=True)

    from stock_quant_v2.db.session import engine
    from stock_quant_v2.strategy_domain.tasks.build_regime_sector_industry_signal_preview_db_write import (
        run_build_regime_sector_industry_signal_preview_db_write,
    )

    def progress(message: str) -> None:
        print(f"[M4_SIGNAL_PREVIEW_DB_WRITE] {message}", flush=True)

    progress(
        "START "
        f"report_date={args.report_date} "
        f"strategy_code={args.strategy_code} "
        f"strategy_version_code={args.strategy_version_code} "
        f"preview_artifact_dir={Path(args.preview_artifact_dir).resolve()} "
        f"output_dir={Path(args.output_dir).resolve()} "
        f"effective_date={args.effective_date} "
        f"write_db={args.write_db} "
        f"max_rows={args.max_rows} "
        f"allow_existing_same_version_date={args.allow_existing_same_version_date}"
    )
    task_result = run_build_regime_sector_industry_signal_preview_db_write(
        engine=engine,
        report_date=args.report_date,
        preview_artifact_dir=args.preview_artifact_dir,
        output_dir=args.output_dir,
        strategy_code=args.strategy_code,
        strategy_version_code=args.strategy_version_code,
        effective_date=_parse_date(args.effective_date),
        write_db=args.write_db,
        write_confirmation=args.write_confirmation,
        allow_existing_same_version_date=args.allow_existing_same_version_date,
        max_rows=args.max_rows,
        progress_callback=progress,
    )
    result = task_result.result
    progress(
        "DONE "
        f"status={result.status} "
        f"run_id={result.run_id} "
        f"candidate_rows={result.summary.get('candidate_row_count')} "
        f"inserted_rows={result.summary.get('inserted_row_count')} "
        f"can_write_strategy_signal_now={result.validation_decision.get('can_write_strategy_signal_now')} "
        f"can_start_m5_backtest_design={result.validation_decision.get('can_start_m5_backtest_design')} "
        f"can_submit_m5_backtest_now={result.validation_decision.get('can_submit_m5_backtest_now')} "
        f"blockers={result.validation_decision.get('blocker_count')}"
    )
    if result.artifacts:
        progress(f"ARTIFACTS_WRITTEN json={result.artifacts.json_path}")


if __name__ == "__main__":
    main()
