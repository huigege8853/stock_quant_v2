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
        value = (value.split(" #", 1)[0]).strip()
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
    parser = argparse.ArgumentParser(description="M4 S1.2 build industry strength features into analytics_feature_snapshot.")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--env-file", default=None)
    parser.add_argument("--report-date", required=True)
    parser.add_argument("--output-dir", default="artifacts/m4/strategy_research_readiness_industry_strength")
    parser.add_argument("--trade-date", default=None, help="Build one date. If non-trading day, latest <= date is used.")
    parser.add_argument("--start-date", default=None, help="Build date range start, inclusive. Requires --end-date.")
    parser.add_argument("--end-date", default=None, help="Build date range end, inclusive. Requires --start-date.")
    parser.add_argument("--window-size", type=int, default=20)
    parser.add_argument("--industry-tag-type", default="SW_INDUSTRY_L2")
    parser.add_argument("--min-industry-size", type=int, default=1)
    parser.add_argument("--min-industry-count", type=int, default=5, help="Minimum distinct industries required before writing features. Guards against UNKNOWN_SW_L1-style collapsed taxonomy.")
    parser.add_argument("--commit-every", type=int, default=1, help="Commit every N trade dates. Default 1 for recoverable manual bootstrap.")
    parser.add_argument("--no-progress", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    project_root = Path(args.project_root).resolve()
    _load_env_file(project_root, args.env_file)

    from stock_quant_v2.analytics_domain.tasks.build_industry_strength_feature import run_build_industry_strength_feature
    from stock_quant_v2.data_domain.repositories.run_repository import RunRepository
    from stock_quant_v2.db.session import SessionLocal, dispose_engine

    trade_date = date.fromisoformat(args.trade_date) if args.trade_date else None
    start_date = date.fromisoformat(args.start_date) if args.start_date else None
    end_date = date.fromisoformat(args.end_date) if args.end_date else None
    if trade_date is None and (start_date is None or end_date is None):
        raise ValueError("Provide --trade-date or both --start-date and --end-date.")
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = project_root / output_dir

    def progress(message: str) -> None:
        if args.no_progress:
            return
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        print(f"[M4_INDUSTRY_STRENGTH][{ts}] {message}", flush=True)

    progress(
        "START "
        f"trade_date={trade_date} start_date={start_date} end_date={end_date} "
        f"window_size={args.window_size} industry_tag_type={args.industry_tag_type} output_dir={output_dir}"
    )

    session = SessionLocal()
    run_repo = RunRepository()
    run = None
    try:
        run = run_repo.create_run(
            session=session,
            run_type="ANALYTICS_BUILD",
            run_name="bootstrap_m4_industry_strength_feature_s1_2",
            trigger_type="MANUAL",
            context_json={
                "stage": "M4_S1_2",
                "purpose": "Build industry strength features for M4 readiness; no strategy signal generation.",
                "trade_date": str(trade_date) if trade_date else None,
                "start_date": str(start_date) if start_date else None,
                "end_date": str(end_date) if end_date else None,
                "window_size": args.window_size,
                "industry_tag_type": args.industry_tag_type,
                "min_industry_size": args.min_industry_size,
                "min_industry_count": args.min_industry_count,
                "guardrails": ["no_strategy_signal", "no_backtest", "no_paper_trading", "no_risk_change"],
            },
        )
        run_repo.mark_run_running(session, run)
        session.commit()

        result = run_build_industry_strength_feature(
            session=session,
            run_id=run.id,
            report_date=args.report_date,
            output_dir=output_dir,
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date,
            window_size=args.window_size,
            industry_tag_type=args.industry_tag_type,
            min_industry_size=args.min_industry_size,
            min_industry_count=args.min_industry_count,
            commit_every=args.commit_every,
            progress_callback=None if args.no_progress else progress,
        )
        session.commit()
        run_repo.mark_run_finished(session, run, "SUCCESS" if result.status == "SUCCESS" else "PARTIAL")
        session.commit()
        progress("RUN_MARK_SUCCESS")
        print(result.to_dict())
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        if run is not None:
            try:
                run = session.get(type(run), run.id)
                if run is not None:
                    run_repo.mark_run_finished(session, run, "FAILED", error_message=str(exc))
                    session.commit()
            except Exception:
                session.rollback()
        progress(f"FAILED error={type(exc).__name__}: {exc}")
        raise
    finally:
        session.close()
        dispose_engine()


if __name__ == "__main__":
    main()
