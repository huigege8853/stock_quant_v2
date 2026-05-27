from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Sequence

from sqlalchemy import text


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






# R63Z3_TAXONOMY_DAILY_CACHE_BEGIN
def _parse_utc_datetime(value: object | None) -> datetime | None:
    if value is None:
        return None
    text_value = str(value).strip()
    if not text_value:
        return None
    if text_value.endswith("Z"):
        text_value = text_value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text_value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _resolve_taxonomy_cache_manifest_path(output_dir: Path, cache_manifest: str | None) -> Path:
    if cache_manifest:
        path = Path(cache_manifest)
        return path if path.is_absolute() else output_dir / path
    return output_dir / "taxonomy_daily_refresh_manifest.json"


def _read_json_payload(path: Path) -> dict | None:
    try:
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _taxonomy_status_is_reusable(status: object | None) -> bool:
    return str(status or "").strip().upper() in {"SUCCESS", "PARTIAL"}


def _taxonomy_artifact_json_path(output_dir: Path, report_date: str) -> Path:
    return output_dir / f"m4_taxonomy_import_p0_{report_date}.json"


def _taxonomy_artifact_md_path(output_dir: Path, report_date: str) -> Path:
    return output_dir / f"m4_taxonomy_import_p0_{report_date}_skip.md"


def _taxonomy_artifact_skip_json_path(output_dir: Path, report_date: str) -> Path:
    return output_dir / f"m4_taxonomy_import_p0_{report_date}_skip.json"


def _is_fresh_timestamp(timestamp: datetime | None, *, ttl_hours: float) -> bool:
    if timestamp is None:
        return False
    if ttl_hours <= 0:
        return True
    age_seconds = (datetime.now(timezone.utc) - timestamp).total_seconds()
    return age_seconds <= ttl_hours * 3600


def _file_mtime_utc(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None


def _taxonomy_last_good_artifact(output_dir: Path) -> dict | None:
    candidates: list[tuple[float, Path, dict]] = []
    for path in output_dir.glob("m4_taxonomy_import_p0_*.json"):
        if path.name.endswith("_skip.json"):
            continue
        payload = _read_json_payload(path)
        if payload is None or not _taxonomy_status_is_reusable(payload.get("status")):
            continue
        try:
            candidates.append((path.stat().st_mtime, path, payload))
        except OSError:
            continue
    if not candidates:
        return None
    _, path, payload = sorted(candidates, key=lambda item: item[0], reverse=True)[0]
    return {
        "artifact_json": str(path),
        "status": payload.get("status"),
        "run_id": payload.get("run_id"),
        "finished_at": payload.get("finished_at"),
    }


def _build_taxonomy_daily_skip_payload(
    *,
    output_dir: Path,
    report_date: str,
    cache_manifest: str | None,
    cache_ttl_hours: float,
) -> dict | None:
    manifest_path = _resolve_taxonomy_cache_manifest_path(output_dir, cache_manifest)
    manifest_payload = _read_json_payload(manifest_path)
    canonical_json = _taxonomy_artifact_json_path(output_dir, report_date)
    source_payload: dict | None = None
    source_reason = ""
    source_timestamp: datetime | None = None

    if manifest_payload is not None:
        manifest_report_date = str(manifest_payload.get("report_date") or "")
        manifest_status = manifest_payload.get("status")
        manifest_artifact = Path(str(manifest_payload.get("artifact_json") or canonical_json))
        if (
            manifest_report_date == report_date
            and _taxonomy_status_is_reusable(manifest_status)
            and manifest_artifact.exists()
        ):
            source_timestamp = _parse_utc_datetime(
                manifest_payload.get("generated_at") or manifest_payload.get("finished_at")
            ) or _file_mtime_utc(manifest_artifact)
            if _is_fresh_timestamp(source_timestamp, ttl_hours=cache_ttl_hours):
                source_payload = manifest_payload
                source_reason = "fresh_manifest"
                canonical_json = manifest_artifact

    if source_payload is None and canonical_json.exists():
        artifact_payload = _read_json_payload(canonical_json)
        if artifact_payload is not None and _taxonomy_status_is_reusable(artifact_payload.get("status")):
            source_timestamp = _parse_utc_datetime(artifact_payload.get("finished_at")) or _file_mtime_utc(canonical_json)
            if _is_fresh_timestamp(source_timestamp, ttl_hours=cache_ttl_hours):
                source_payload = artifact_payload
                source_reason = "fresh_same_report_artifact"

    if source_payload is None:
        return None

    last_good = _taxonomy_last_good_artifact(output_dir)
    skip_payload = {
        "status": "SKIPPED_FRESH_CACHE",
        "report_date": report_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cache_ttl_hours": cache_ttl_hours,
        "skip_reason": source_reason,
        "reused_artifact_json": str(canonical_json),
        "reused_status": source_payload.get("status"),
        "reused_run_id": source_payload.get("run_id"),
        "reused_finished_at": source_payload.get("finished_at"),
        "manifest_path": str(manifest_path),
        "last_good": last_good,
        "guardrails": ["no_provider_fetch", "no_db_write", "no_strategy_signal", "no_paper_trading"],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    skip_json = _taxonomy_artifact_skip_json_path(output_dir, report_date)
    skip_md = _taxonomy_artifact_md_path(output_dir, report_date)
    skip_payload["artifact_paths"] = {"skip_json": str(skip_json), "skip_markdown": str(skip_md)}
    skip_json.write_text(json.dumps(skip_payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    skip_md.write_text(
        "\n".join([
            "# M4 Taxonomy Daily Refresh Cache Skip",
            "",
            f"- report_date: {report_date}",
            "- status: SKIPPED_FRESH_CACHE",
            f"- skip_reason: {source_reason}",
            f"- reused_artifact_json: {canonical_json}",
            f"- reused_status: {source_payload.get('status')}",
            f"- reused_run_id: {source_payload.get('run_id')}",
            f"- cache_ttl_hours: {cache_ttl_hours}",
            "- guardrail: skipped provider fetch and DB write; last-good taxonomy data remains in DB.",
            "",
        ]),
        encoding="utf-8",
    )
    return skip_payload


def _write_taxonomy_daily_refresh_manifest(
    *,
    output_dir: Path,
    report_date: str,
    cache_manifest: str | None,
    result,
) -> dict:
    manifest_path = _resolve_taxonomy_cache_manifest_path(output_dir, cache_manifest)
    artifact_json = None
    try:
        artifact_json = result.artifact_paths.get("json")
    except Exception:
        artifact_json = None
    stats_summary = []
    try:
        for item in result.stats:
            stats_summary.append({
                "import_name": item.import_name,
                "input_rows": item.input_rows,
                "instrument_tag_upsert_rows": item.instrument_tag_upsert_rows,
                "missing_instruments": item.missing_instruments,
                "error_rows": item.error_rows,
                "skipped_rows": item.skipped_rows,
            })
    except Exception:
        stats_summary = []
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "report_date": report_date,
        "status": getattr(result, "status", None),
        "run_id": getattr(result, "run_id", None),
        "started_at": getattr(result, "started_at", None),
        "finished_at": getattr(result, "finished_at", None),
        "artifact_json": artifact_json,
        "artifact_paths": getattr(result, "artifact_paths", {}),
        "stats_summary": stats_summary,
        "guardrails": ["last_good_taxonomy_cache", "daily_skip_if_fresh", "force_refresh_supported"],
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return {**payload, "manifest_path": str(manifest_path)}
# R63Z3_TAXONOMY_DAILY_CACHE_END


def _resolve_report_date(session, explicit_report_date: str | None) -> str:
    if explicit_report_date:
        return explicit_report_date

    value = session.execute(
        text(
            "select max(trade_date)::text "
            "from public.core_daily_bar "
            "where price_adjust_type = 'RAW'"
        )
    ).scalar_one_or_none()
    if not value:
        raise ValueError("Cannot resolve report date: no RAW rows in public.core_daily_bar")
    return str(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="M4 S1.1 taxonomy input import: SW industry + Eastmoney concept mapping.")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--env-file", default=None)
    parser.add_argument("--report-date", default=None, help="Report date. Default: latest RAW core_daily_bar trade_date from DB.")
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
    parser.add_argument("--daily-refresh", action="store_true", help="Daily taxonomy refresh mode. If no taxonomy input is provided, attempt SW industry and Eastmoney concept providers.")
    parser.add_argument("--fail-safe", action="store_true", help="Do not fail the caller when a taxonomy provider is unavailable; write WARN/PARTIAL artifacts and keep last-good DB data.")
    parser.add_argument("--cache-manifest", default=None, help="Optional daily taxonomy cache manifest path. Relative paths are resolved from --output-dir. Default: taxonomy_daily_refresh_manifest.json under output-dir.")
    parser.add_argument("--cache-ttl-hours", type=float, default=36.0, help="When --daily-refresh is used, skip provider fetch/DB writes if same report-date taxonomy artifact is fresh within this TTL. Use 0 to accept same-report-date artifact regardless of mtime.")
    parser.add_argument("--skip-if-fresh", action=argparse.BooleanOptionalAction, default=True, help="Daily refresh cache guard. Default true; use --no-skip-if-fresh to force normal refresh unless --force-refresh is set.")
    parser.add_argument("--force-refresh", action="store_true", help="Bypass daily taxonomy cache/manifest and fetch providers even when same report-date artifact is fresh.")
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
        resolved_report_date = _resolve_report_date(session, args.report_date)

        if args.daily_refresh and not any([
            args.sw_industry_csv,
            args.fetch_sw_industry_akshare,
            args.concept_em_csv,
            args.fetch_em_concepts,
        ]):
            args.fetch_sw_industry_akshare = True
            args.fetch_em_concepts = True

        progress(
            "RESOLVED "
            f"report_date={resolved_report_date} "
            f"daily_refresh={args.daily_refresh} "
            f"fail_safe={args.fail_safe} "
            f"skip_if_fresh={args.skip_if_fresh} "
            f"force_refresh={args.force_refresh} "
            f"cache_ttl_hours={args.cache_ttl_hours}"
        )

        if args.daily_refresh and args.skip_if_fresh and not args.force_refresh:
            skip_payload = _build_taxonomy_daily_skip_payload(
                output_dir=output_dir,
                report_date=resolved_report_date,
                cache_manifest=args.cache_manifest,
                cache_ttl_hours=args.cache_ttl_hours,
            )
            if skip_payload is not None:
                progress(
                    "CACHE_SKIP "
                    f"reason={skip_payload.get('skip_reason')} "
                    f"reused_artifact_json={skip_payload.get('reused_artifact_json')}"
                )
                print(skip_payload)
                return

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
                "daily_refresh": args.daily_refresh,
                "fail_safe": args.fail_safe,
                "cache_manifest": args.cache_manifest,
                "cache_ttl_hours": args.cache_ttl_hours,
                "skip_if_fresh": args.skip_if_fresh,
                "force_refresh": args.force_refresh,
                "report_date": resolved_report_date,
                "guardrails": ["no_strategy_signal", "no_backtest", "no_paper_trading", "no_risk_change"],
            },
        )
        run_repo.mark_run_running(session, run)
        session.commit()

        result = run_import_strategy_taxonomy_tags(
            session=session,
            run_id=run.id,
            report_date=resolved_report_date,
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
            fail_safe=args.fail_safe,
        )
        if args.daily_refresh:
            manifest_payload = _write_taxonomy_daily_refresh_manifest(
                output_dir=output_dir,
                report_date=resolved_report_date,
                cache_manifest=args.cache_manifest,
                result=result,
            )
            progress(f"CACHE_MANIFEST_WRITTEN path={manifest_payload.get('manifest_path')}")
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
