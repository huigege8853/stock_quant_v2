from __future__ import annotations

import argparse
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Sequence


def _parse_env_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    if stripped.startswith("export "):
        stripped = stripped[len("export ") :].strip()
    key, value = stripped.split("=", 1)
    key = key.strip()
    value = value.strip()
    if not key:
        return None
    quoted = len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}
    if not quoted:
        value = value.split(" #", 1)[0].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return key, value


def _load_env_file(project_root: Path, env_file: str | None) -> None:
    candidates = [project_root / env_file] if env_file else [project_root / ".env.research", project_root / ".env", project_root / ".env.local"]
    for path in candidates:
        if path.exists():
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                parsed = _parse_env_line(line)
                if parsed is None:
                    continue
                key, value = parsed
                if key not in os.environ or not os.environ.get(key):
                    os.environ[key] = value
            print(f"ENV_LOADED={path}")
            return
    print("ENV_LOADED=NONE")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="M4 S2 validate regime / sector / industry rule design without generating strategy_signal.")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--env-file", default=None)
    parser.add_argument("--report-date", required=True)
    parser.add_argument("--trade-date", required=True, help="Requested validation date. Latest feature date <= this date will be used.")
    parser.add_argument("--output-dir", default="artifacts/m4/strategy_rule_validation")
    parser.add_argument("--feature-set-code", default="fs_daily_alpha_v1")
    parser.add_argument("--feature-set-version", default="v1")
    parser.add_argument("--industry-tag-type", default="SW_INDUSTRY_L2")
    parser.add_argument("--benchmark-index-code", default="000300.SH")
    parser.add_argument("--lookback-days", type=int, default=20)
    parser.add_argument("--min-preview-rows", type=int, default=50)
    parser.add_argument("--top-n", type=int, default=100)
    parser.add_argument("--no-progress", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    project_root = Path(args.project_root).resolve()
    _load_env_file(project_root, args.env_file)

    from stock_quant_v2.db.session import SessionLocal, dispose_engine
    from stock_quant_v2.strategy_domain.tasks.build_regime_sector_industry_rule_validation import (
        run_build_regime_sector_industry_rule_validation,
    )

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = project_root / output_dir

    requested_trade_date = date.fromisoformat(args.trade_date)

    def progress(message: str) -> None:
        if args.no_progress:
            return
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        print(f"[M4_S2_RULE_VALIDATION][{ts}] {message}", flush=True)

    progress(
        "START "
        f"trade_date={requested_trade_date} feature_set={args.feature_set_code}/{args.feature_set_version} "
        f"industry_tag_type={args.industry_tag_type} benchmark_index_code={args.benchmark_index_code} output_dir={output_dir}"
    )
    session = SessionLocal()
    try:
        task_result = run_build_regime_sector_industry_rule_validation(
            session=session,
            report_date=args.report_date,
            output_dir=output_dir,
            trade_date=requested_trade_date,
            feature_set_code=args.feature_set_code,
            feature_set_version=args.feature_set_version,
            industry_tag_type=args.industry_tag_type,
            benchmark_index_code=args.benchmark_index_code,
            lookback_days=args.lookback_days,
            min_preview_rows=args.min_preview_rows,
            top_n=args.top_n,
            progress_callback=None if args.no_progress else progress,
        )
        progress(f"ARTIFACTS_WRITTEN status={task_result.status} output_dir={output_dir}")
        print(task_result.to_dict())
    except Exception as exc:  # noqa: BLE001
        progress(f"FAILED error={type(exc).__name__}: {exc}")
        raise
    finally:
        session.close()
        dispose_engine()


if __name__ == "__main__":
    main()
