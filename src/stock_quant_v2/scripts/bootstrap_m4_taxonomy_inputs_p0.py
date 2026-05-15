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


def _split_csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="M4 S1.1 taxonomy input import: SW industry + Eastmoney concept mapping.")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--env-file", default=None)
    parser.add_argument("--report-date", required=True)
    parser.add_argument("--output-dir", default="artifacts/m4/strategy_research_readiness_taxonomy")
    parser.add_argument("--sw-industry-csv", default=None, help="CSV containing SW 2021 industry L1/L2/L3 mapping.")
    parser.add_argument("--fetch-sw-industry-akshare", action="store_true", help="Fetch SW industry L3 constituents through AKShare and import SW_INDUSTRY mappings.")
    parser.add_argument("--sw-industry-codes", default=None, help="Comma separated SW L3 industry codes to fetch. Omit for all SW L3 industries.")
    parser.add_argument("--max-sw-industries", type=int, default=None, help="Limit number of SW L3 industries for smoke run. 0 or omitted means no limit.")
    parser.add_argument("--concept-em-csv", default=None, help="Optional local CSV containing Eastmoney concept -> stock mapping.")
    parser.add_argument("--fetch-em-concepts", action="store_true", help="Fetch Eastmoney concepts through AKShare and import CONCEPT_EM mappings.")
    parser.add_argument("--concept-names", default=None, help="Comma separated Eastmoney concept names to fetch. Omit for all concepts.")
    parser.add_argument("--max-concepts", type=int, default=None, help="Limit number of concepts for smoke run. 0 or omitted means no limit.")
    parser.add_argument("--effective-from", default="1990-01-01")
    parser.add_argument("--effective-to", default=None)
    parser.add_argument("--progress-every", type=int, default=1, help="Print one progress line every N fetched SW industries/concepts. Default 1 for visible long-running AKShare fetches.")
    parser.add_argument("--sw-fetch-delay-seconds", type=float, default=0.0, help="Sleep between SW industry constituent fetches. Useful when Legulegu rate limits requests.")
    parser.add_argument("--sw-fallback-delay-seconds", type=float, default=2.0, help="Sleep before each Legulegu fallback request after AKShare constituent fetch fails.")
    parser.add_argument("--sw-fetch-retry-attempts", type=int, default=3, help="Retry attempts for retryable Legulegu SW constituent HTTP errors such as 429/504.")
    parser.add_argument("--sw-fetch-retry-backoff-seconds", type=float, default=5.0, help="Base backoff seconds for retryable Legulegu SW constituent HTTP errors.")
    parser.add_argument("--sw-fetch-timeout-seconds", type=float, default=20.0, help="HTTP timeout for Legulegu SW constituent fallback requests.")
    parser.add_argument("--concept-import-progress-every", type=int, default=2000, help="Print one progress line every N concept mapping rows during DB import.")
    parser.add_argument("--concept-import-commit-every", type=int, default=5000, help="Commit every N concept mapping rows. Use 0 to keep one transaction.")
    parser.add_argument("--no-progress", action="store_true", help="Disable progress logs.")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    project_root = Path(args.project_root).resolve()
    _load_env_file(project_root, args.env_file)

    from stock_quant_v2.data_domain.repositories.run_repository import RunRepository
    from stock_quant_v2.data_domain.tasks.import_strategy_taxonomy_tags import run_import_strategy_taxonomy_tags
    from stock_quant_v2.db.session import SessionLocal, dispose_engine

    effective_from = date.fromisoformat(args.effective_from)
    effective_to = date.fromisoformat(args.effective_to) if args.effective_to else None
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = project_root / output_dir

    def progress(message: str) -> None:
        if args.no_progress:
            return
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        print(f"[M4_TAXONOMY][{ts}] {message}", flush=True)

    progress(
        "START "
        f"fetch_sw_industry_akshare={args.fetch_sw_industry_akshare} "
        f"fetch_em_concepts={args.fetch_em_concepts} "
        f"sw_industry_csv={bool(args.sw_industry_csv)} "
        f"concept_em_csv={bool(args.concept_em_csv)} "
        f"output_dir={output_dir}"
    )

    session = SessionLocal()
    run_repo = RunRepository()
    run = None
    try:
        run = run_repo.create_run(
            session=session,
            run_type="DATA_BACKFILL",
            run_name="bootstrap_m4_taxonomy_inputs_p0",
            trigger_type="MANUAL",
            context_json={
                "stage": "M4_S1_1",
                "purpose": "Import SW industry and Eastmoney concept taxonomy mappings for readiness audit.",
                "sw_industry_csv": args.sw_industry_csv,
                "fetch_sw_industry_akshare": args.fetch_sw_industry_akshare,
                "sw_industry_codes": _split_csv(args.sw_industry_codes),
                "max_sw_industries": args.max_sw_industries,
                "sw_fetch_delay_seconds": args.sw_fetch_delay_seconds,
                "sw_fallback_delay_seconds": args.sw_fallback_delay_seconds,
                "sw_fetch_retry_attempts": args.sw_fetch_retry_attempts,
                "sw_fetch_retry_backoff_seconds": args.sw_fetch_retry_backoff_seconds,
                "sw_fetch_timeout_seconds": args.sw_fetch_timeout_seconds,
                "concept_em_csv": args.concept_em_csv,
                "fetch_em_concepts": args.fetch_em_concepts,
                "concept_names": _split_csv(args.concept_names),
                "max_concepts": args.max_concepts,
                "concept_import_progress_every": args.concept_import_progress_every,
                "concept_import_commit_every": args.concept_import_commit_every,
                "guardrails": ["no_strategy_signal", "no_backtest", "no_paper_trading", "no_risk_change"],
            },
        )
        run_repo.mark_run_running(session, run)
        session.commit()

        result = run_import_strategy_taxonomy_tags(
            session=session,
            run_id=run.id,
            report_date=args.report_date,
            output_dir=output_dir,
            sw_industry_csv=args.sw_industry_csv,
            fetch_sw_industry_akshare=args.fetch_sw_industry_akshare,
            sw_industry_codes=_split_csv(args.sw_industry_codes),
            max_sw_industries=args.max_sw_industries,
            concept_em_csv=args.concept_em_csv,
            fetch_em_concepts=args.fetch_em_concepts,
            concept_names=_split_csv(args.concept_names),
            max_concepts=args.max_concepts,
            effective_from=effective_from,
            effective_to=effective_to,
            progress_callback=None if args.no_progress else progress,
            progress_every=args.progress_every,
            sw_fetch_delay_seconds=args.sw_fetch_delay_seconds,
            sw_fallback_delay_seconds=args.sw_fallback_delay_seconds,
            sw_fetch_retry_attempts=args.sw_fetch_retry_attempts,
            sw_fetch_retry_backoff_seconds=args.sw_fetch_retry_backoff_seconds,
            sw_fetch_timeout_seconds=args.sw_fetch_timeout_seconds,
            concept_import_progress_every=args.concept_import_progress_every,
            concept_import_commit_every=args.concept_import_commit_every,
        )
        session.commit()
        final_status = "SUCCESS" if result.status == "SUCCESS" else "PARTIAL"
        run_repo.mark_run_finished(session, run, final_status)
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
