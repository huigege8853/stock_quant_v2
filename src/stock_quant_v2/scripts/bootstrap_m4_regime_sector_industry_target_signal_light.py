from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import create_engine, text

DEFAULT_STRATEGY_CODE = "regime_sector_industry_selection_v1"
DEFAULT_STRATEGY_VERSION_CODE = "v1_regime_state_machine"
DEFAULT_PREVIEW_ARTIFACT_DIR = pathlib.Path("artifacts/m4/strategy_signal_preview_v1_1")
DEFAULT_OUTPUT_DIR = pathlib.Path("artifacts/m4/strategy_signal_db_write_contract")
DEFAULT_BUILD_MODULES = [
    "stock_quant_v2.scripts.bootstrap_m4_regime_sector_industry_signal_preview_s3",
]
OPTIONAL_PREVIEW_MODULES = [
    "stock_quant_v2.scripts.bootstrap_m4_industry_strength_feature_s1_2",
    "stock_quant_v2.scripts.bootstrap_m4_regime_sector_industry_rule_validation_s2",
    "stock_quant_v2.scripts.bootstrap_m4_regime_sector_industry_signal_preview_s3",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, pathlib.Path):
        return str(value)
    return str(value)


def parse_date(value: str | None) -> date | None:
    if value is None or str(value).strip() == "":
        return None
    return date.fromisoformat(str(value).strip())


def resolve_engine():
    # Prefer the project SessionLocal/bound engine because it respects the existing app config.
    try:
        from stock_quant_v2.db import session as session_module  # type: ignore

        for attr in ("engine", "ENGINE", "_engine"):
            engine = getattr(session_module, attr, None)
            if engine is not None:
                return engine, f"stock_quant_v2.db.session.{attr}"

        session_local = getattr(session_module, "SessionLocal", None)
        if session_local is not None:
            bind = getattr(session_local, "kw", {}).get("bind")
            if bind is not None:
                return bind, "stock_quant_v2.db.session.SessionLocal.kw.bind"
            try:
                with session_local() as session:
                    bind = session.get_bind()
                    if bind is not None:
                        return bind, "stock_quant_v2.db.session.SessionLocal().get_bind()"
            except Exception:
                pass
    except Exception:
        pass

    for key in (
        "V2_SQLALCHEMY_URL",
        "SQLALCHEMY_URL",
        "DATABASE_URL",
        "POSTGRES_DSN",
        "V2_DATABASE_URL",
    ):
        value = os.getenv(key, "").strip()
        if value:
            return create_engine(value, future=True), f"env:{key}"

    raise RuntimeError("No SQLAlchemy engine/DSN found. Expected SessionLocal bind or V2_SQLALCHEMY_URL.")


def safe_scalar(conn, sql: str, params: dict[str, Any] | None = None) -> Any:
    try:
        return conn.execute(text(sql), params or {}).scalar()
    except Exception:
        return None


def resolve_latest_closed_trade_date(engine) -> date:
    candidates = [
        "SELECT MAX(trade_date)::date FROM core_daily_bar WHERE trade_date IS NOT NULL",
        "SELECT MAX(trade_date)::date FROM daily_bar WHERE trade_date IS NOT NULL",
        "SELECT MAX(trade_date)::date FROM core_daily_bar",
        "SELECT MAX(trade_date)::date FROM market_daily_bar",
    ]
    with engine.connect() as conn:
        for sql in candidates:
            value = safe_scalar(conn, sql)
            if value is not None:
                if isinstance(value, date):
                    return value
                return date.fromisoformat(str(value)[:10])
    raise RuntimeError("Could not resolve latest closed trade date from known daily-bar tables.")


def fetch_target_signal_summary(engine, strategy_code: str, strategy_version_code: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "strategy_code": strategy_code,
        "strategy_version_code": strategy_version_code,
    }
    sql = """
    WITH target AS (
        SELECT sv.id AS strategy_version_id
        FROM strategy_version sv
        JOIN strategy_definition sd ON sd.id = sv.strategy_definition_id
        WHERE sd.strategy_code = :strategy_code
          AND sv.version_code = :strategy_version_code
        ORDER BY sv.id DESC
        LIMIT 1
    )
    SELECT
        (SELECT strategy_version_id FROM target) AS strategy_version_id,
        COUNT(ss.*) AS total_rows,
        MIN(ss.effective_date)::date AS min_effective_date,
        MAX(ss.effective_date)::date AS max_effective_date,
        MAX(ss.created_at) AS max_created_at
    FROM strategy_signal ss
    JOIN target t ON t.strategy_version_id = ss.strategy_version_id
    """
    recent_sql = """
    WITH target AS (
        SELECT sv.id AS strategy_version_id
        FROM strategy_version sv
        JOIN strategy_definition sd ON sd.id = sv.strategy_definition_id
        WHERE sd.strategy_code = :strategy_code
          AND sv.version_code = :strategy_version_code
        ORDER BY sv.id DESC
        LIMIT 1
    )
    SELECT ss.effective_date::date AS effective_date, COUNT(*) AS rows, MAX(ss.created_at) AS max_created_at
    FROM strategy_signal ss
    JOIN target t ON t.strategy_version_id = ss.strategy_version_id
    GROUP BY ss.effective_date
    ORDER BY ss.effective_date DESC
    LIMIT 10
    """
    with engine.connect() as conn:
        row = conn.execute(text(sql), {"strategy_code": strategy_code, "strategy_version_code": strategy_version_code}).mappings().first()
        recent = conn.execute(text(recent_sql), {"strategy_code": strategy_code, "strategy_version_code": strategy_version_code}).mappings().all()
    payload.update({
        "ok": True,
        "summary": dict(row) if row else None,
        "recent_dates": [dict(r) for r in recent],
    })
    return payload


def run_module(module: str, *, report_date: date, effective_date: date, output_root: pathlib.Path) -> dict[str, Any]:
    env = os.environ.copy()
    d = report_date.isoformat()
    env.update({
        "M4_AS_OF_DATE": d,
        "M4_SIGNAL_AS_OF_DATE": d,
        "M4_TRADE_DATE": d,
        "M4_EFFECTIVE_DATE": effective_date.isoformat(),
        "SQV2_RESEARCH_STRATEGY_CODE": DEFAULT_STRATEGY_CODE,
        "SQV2_RESEARCH_STRATEGY_VERSION_CODE": DEFAULT_STRATEGY_VERSION_CODE,
    })
    log_dir = output_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    safe_name = module.replace(".", "_")
    stdout_path = log_dir / f"{safe_name}.stdout.log"
    stderr_path = log_dir / f"{safe_name}.stderr.log"
    cmd = [sys.executable, "-m", module]
    started = utc_now_iso()
    with stdout_path.open("w", encoding="utf-8") as out, stderr_path.open("w", encoding="utf-8") as err:
        proc = subprocess.run(cmd, cwd=pathlib.Path.cwd(), env=env, stdout=out, stderr=err, text=True)
    return {
        "module": module,
        "cmd": cmd,
        "started_at_utc": started,
        "finished_at_utc": utc_now_iso(),
        "return_code": proc.returncode,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }


def result_to_dict(value: Any) -> dict[str, Any]:
    obj = getattr(value, "result", value)
    if hasattr(obj, "to_dict"):
        try:
            return obj.to_dict(include_rows=False)  # type: ignore[misc]
        except TypeError:
            return obj.to_dict()  # type: ignore[misc]
    if hasattr(obj, "__dict__"):
        return dict(obj.__dict__)
    return {"repr": repr(obj)}


def run_contract_or_write(
    *,
    engine,
    report_date: date,
    effective_date: date,
    preview_artifact_dir: pathlib.Path,
    output_dir: pathlib.Path,
    strategy_code: str,
    strategy_version_code: str,
    write_db: bool,
    write_confirmation: str,
    allow_existing_same_version_date: bool,
    max_rows: int | None,
) -> dict[str, Any]:
    from stock_quant_v2.strategy_domain.tasks.build_regime_sector_industry_signal_preview_db_write import (  # type: ignore
        run_build_regime_sector_industry_signal_preview_db_write,
    )

    result = run_build_regime_sector_industry_signal_preview_db_write(
        engine=engine,
        report_date=report_date.isoformat(),
        preview_artifact_dir=preview_artifact_dir,
        output_dir=output_dir,
        strategy_code=strategy_code,
        strategy_version_code=strategy_version_code,
        effective_date=effective_date,
        write_db=write_db,
        write_confirmation=write_confirmation,
        allow_existing_same_version_date=allow_existing_same_version_date,
        max_rows=max_rows,
        progress_callback=lambda msg: print(f"[TARGET_M4_LIGHT] {msg}", flush=True),
    )
    return result_to_dict(result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build/write regime_sector_industry target M4 strategy_signal using existing production/research code paths."
    )
    parser.add_argument("--report-date", default="", help="Signal preview report/as-of date. Default: latest closed trade date.")
    parser.add_argument("--effective-date", default="", help="Signal effective date. Default: report-date.")
    parser.add_argument("--strategy-code", default=os.getenv("SQV2_RESEARCH_STRATEGY_CODE", DEFAULT_STRATEGY_CODE))
    parser.add_argument("--strategy-version-code", default=os.getenv("SQV2_RESEARCH_STRATEGY_VERSION_CODE", DEFAULT_STRATEGY_VERSION_CODE))
    parser.add_argument("--preview-artifact-dir", default=str(DEFAULT_PREVIEW_ARTIFACT_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--build-preview", action="store_true", help="Run existing target preview module before db-write contract.")
    parser.add_argument("--run-full-target-preview-chain", action="store_true", help="Run s1_2, s2, s3 modules before db-write contract. This still skips taxonomy p0.")
    parser.add_argument("--write-db", action="store_true", help="Allow db write via existing signal preview db-write service.")
    parser.add_argument("--write-confirmation", default=os.getenv("M4_TARGET_SIGNAL_WRITE_CONFIRMATION", ""))
    parser.add_argument("--allow-existing-same-version-date", action="store_true")
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--output-json", default="")
    args = parser.parse_args(argv)

    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    engine, engine_source = resolve_engine()
    report_date = parse_date(args.report_date) or resolve_latest_closed_trade_date(engine)
    effective_date = parse_date(args.effective_date) or report_date

    payload: dict[str, Any] = {
        "stage": "bootstrap_m4_regime_sector_industry_target_signal_light",
        "generated_at_utc": utc_now_iso(),
        "boundary": {
            "source_code_changed": False,
            "taxonomy_refresh_executed": False,
            "daily_runtime_executed": False,
            "paper_simulation_executed": False,
            "broker_order_enabled": False,
        },
        "engine_source": engine_source,
        "target": {
            "strategy_code": args.strategy_code,
            "strategy_version_code": args.strategy_version_code,
            "report_date": report_date,
            "effective_date": effective_date,
            "preview_artifact_dir": pathlib.Path(args.preview_artifact_dir),
            "output_dir": output_dir,
        },
        "pre_signal": fetch_target_signal_summary(engine, args.strategy_code, args.strategy_version_code),
        "preview_modules": [],
        "contract_or_write": None,
        "post_signal": None,
        "status": "INIT",
    }

    modules: list[str] = []
    if args.run_full_target_preview_chain:
        modules = OPTIONAL_PREVIEW_MODULES
    elif args.build_preview:
        modules = DEFAULT_BUILD_MODULES

    for module in modules:
        step = run_module(module, report_date=report_date, effective_date=effective_date, output_root=output_dir)
        payload["preview_modules"].append(step)
        if step["return_code"] != 0:
            payload["status"] = "FAIL_PREVIEW_MODULE"
            payload["failed_module"] = module
            break
    else:
        try:
            payload["contract_or_write"] = run_contract_or_write(
                engine=engine,
                report_date=report_date,
                effective_date=effective_date,
                preview_artifact_dir=pathlib.Path(args.preview_artifact_dir),
                output_dir=output_dir,
                strategy_code=args.strategy_code,
                strategy_version_code=args.strategy_version_code,
                write_db=bool(args.write_db),
                write_confirmation=args.write_confirmation,
                allow_existing_same_version_date=bool(args.allow_existing_same_version_date),
                max_rows=args.max_rows,
            )
            payload["post_signal"] = fetch_target_signal_summary(engine, args.strategy_code, args.strategy_version_code)
            pre_max = ((payload["pre_signal"].get("summary") or {}).get("max_effective_date")) if payload.get("pre_signal") else None
            post_max = ((payload["post_signal"].get("summary") or {}).get("max_effective_date")) if payload.get("post_signal") else None
            if args.write_db and str(post_max)[:10] >= effective_date.isoformat():
                payload["status"] = "PASS_TARGET_SIGNAL_WRITTEN_OR_ALREADY_FRESH"
            elif not args.write_db:
                payload["status"] = "PASS_CONTRACT_BUILT_NO_DB_WRITE"
            else:
                payload["status"] = "WARN_WRITE_ATTEMPTED_SIGNAL_NOT_FRESH"
            payload["pre_max_effective_date"] = pre_max
            payload["post_max_effective_date"] = post_max
        except Exception as exc:
            payload["status"] = "FAIL_CONTRACT_OR_WRITE_EXCEPTION"
            payload["exception"] = f"{type(exc).__name__}: {exc}"

    out_path = pathlib.Path(args.output_json) if args.output_json else output_dir / f"target_m4_signal_light_{report_date.isoformat()}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=json_default))
    return 0 if str(payload.get("status", "")).startswith("PASS") else 2


if __name__ == "__main__":
    raise SystemExit(main())
