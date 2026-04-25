from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class M8Step:
    name: str
    module_name: str
    required_env_keys: tuple[str, ...] = ()
    soft_fail_in_ops_profile: bool = False


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _resolve_report_date() -> str:
    env_date = os.getenv("M8_REPORT_DATE")
    if env_date:
        return env_date

    tz_name = os.getenv("APP_TIMEZONE", "Asia/Shanghai")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Asia/Shanghai")

    return datetime.now(tz).date().isoformat()


def _parse_json_payload(stdout_text: str) -> dict | None:
    text = (stdout_text or "").strip()
    if not text:
        return None

    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    lines = text.splitlines()
    for start in range(len(lines)):
        candidate = "\n".join(lines[start:]).strip()
        if not (candidate.startswith("{") and candidate.endswith("}")):
            continue
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue

    return None


def _run_module(module_name: str, env: dict[str, str]) -> tuple[int, dict | None]:
    completed = subprocess.run(
        [sys.executable, "-m", module_name],
        cwd=_project_root(),
        env=env,
        text=True,
        capture_output=True,
    )

    if completed.stdout.strip():
        print(completed.stdout.strip())
    if completed.stderr.strip():
        print(completed.stderr.strip(), file=sys.stderr)

    payload = _parse_json_payload(completed.stdout)
    return int(completed.returncode), payload


def _missing_required_env(step: M8Step, env: dict[str, str]) -> list[str]:
    return [key for key in step.required_env_keys if env.get(key) in (None, "")]


def _build_shared_env(args: argparse.Namespace) -> dict[str, str]:
    env = os.environ.copy()

    env["M8_REPORT_DATE"] = args.report_date or os.getenv("M8_REPORT_DATE") or _resolve_report_date()

    if args.output_dir:
        env["M8_OUTPUT_DIR"] = args.output_dir

    optional_arg_to_env = {
        "run_id": "M8_RUN_ID",
        "portfolio_id": "M8_PORTFOLIO_ID",
        "target_run_id": "M8_TARGET_RUN_ID",
        "order_run_id": "M8_ORDER_RUN_ID",
        "fill_run_id": "M8_FILL_RUN_ID",
        "position_run_id": "M8_POSITION_RUN_ID",
        "snapshot_run_id": "M8_SNAPSHOT_RUN_ID",
        "source_target_run_id": "M8_SOURCE_TARGET_RUN_ID",
        "adjusted_target_run_id": "M8_ADJUSTED_TARGET_RUN_ID",
        "risk_run_id": "M8_RISK_RUN_ID",
    }

    for arg_name, env_name in optional_arg_to_env.items():
        value = getattr(args, arg_name)
        if value is not None:
            env[env_name] = str(value)

    return env


def _inject_env_from_env_check(payload: dict | None, env: dict[str, str]) -> None:
    if not payload or not isinstance(payload, dict):
        return

    portfolio_id = payload.get("portfolio_id")
    if portfolio_id not in (None, "") and not env.get("M8_PORTFOLIO_ID"):
        env["M8_PORTFOLIO_ID"] = str(portfolio_id)

    latest_runs = payload.get("latest_runs") or {}
    trading_chain = latest_runs.get("trading_chain") or {}
    risk_chain = latest_runs.get("risk_chain") or {}

    mapping = {
        "M8_TARGET_RUN_ID": trading_chain.get("target_run_id"),
        "M8_ORDER_RUN_ID": trading_chain.get("order_run_id"),
        "M8_FILL_RUN_ID": trading_chain.get("fill_run_id"),
        "M8_POSITION_RUN_ID": trading_chain.get("position_run_id"),
        "M8_SNAPSHOT_RUN_ID": trading_chain.get("snapshot_run_id"),
        "M8_SOURCE_TARGET_RUN_ID": risk_chain.get("source_target_run_id"),
        "M8_ADJUSTED_TARGET_RUN_ID": risk_chain.get("adjusted_target_run_id"),
        "M8_RISK_RUN_ID": risk_chain.get("risk_run_id"),
    }

    for env_key, value in mapping.items():
        if value not in (None, "") and not env.get(env_key):
            env[env_key] = str(value)


def _ops_steps() -> list[M8Step]:
    return [
        M8Step("env_check", "stock_quant_v2.scripts.m8_env_check", soft_fail_in_ops_profile=True),
        M8Step("startup_check", "stock_quant_v2.scripts.m8_startup_check", soft_fail_in_ops_profile=True),
        M8Step("daily_ops_check", "stock_quant_v2.scripts.m8_daily_ops_check"),
        M8Step("ops_run_hygiene_check", "stock_quant_v2.scripts.m8_ops_run_hygiene_check"),
        M8Step("ops_alert_check", "stock_quant_v2.scripts.m8_ops_alert_check"),
        M8Step("scheduler_health_check", "stock_quant_v2.scripts.m8_scheduler_health_check"),
        M8Step("export_daily_ops_report", "stock_quant_v2.scripts.m8_export_daily_ops_report"),
        M8Step("export_ops_summary_pack", "stock_quant_v2.scripts.m8_export_ops_summary_pack"),
        M8Step("export_human_review_pack", "stock_quant_v2.scripts.m8_export_human_review_pack"),
        M8Step("export_alert_report", "stock_quant_v2.scripts.m8_export_alert_report"),
        M8Step("export_audit_snapshot", "stock_quant_v2.scripts.m8_export_audit_snapshot"),
        M8Step(
            "export_env_report",
            "stock_quant_v2.scripts.m8_export_env_report",
            soft_fail_in_ops_profile=True,
        ),
        M8Step(
            "export_paper_chain_report",
            "stock_quant_v2.scripts.m8_export_paper_chain_report",
            required_env_keys=(
                "M8_PORTFOLIO_ID",
                "M8_TARGET_RUN_ID",
                "M8_ORDER_RUN_ID",
                "M8_FILL_RUN_ID",
                "M8_POSITION_RUN_ID",
                "M8_SNAPSHOT_RUN_ID",
            ),
        ),
        M8Step(
            "export_portfolio_snapshot_report",
            "stock_quant_v2.scripts.m8_export_portfolio_snapshot_report",
            required_env_keys=("M8_PORTFOLIO_ID", "M8_SNAPSHOT_RUN_ID"),
        ),
        M8Step(
            "export_risk_report",
            "stock_quant_v2.scripts.m8_export_risk_report",
            required_env_keys=("M8_SOURCE_TARGET_RUN_ID", "M8_ADJUSTED_TARGET_RUN_ID"),
        ),
        M8Step(
            "export_run_summary_report",
            "stock_quant_v2.scripts.m8_export_run_summary_report",
            required_env_keys=("M8_RUN_ID",),
        ),
        M8Step("export_excel_daily_ops", "stock_quant_v2.scripts.m8_export_excel_daily_ops"),
        M8Step("export_excel_human_review_pack", "stock_quant_v2.scripts.m8_export_excel_human_review_pack"),
        M8Step("export_excel_ops_summary", "stock_quant_v2.scripts.m8_export_excel_ops_summary"),
        M8Step("scheduler_plan", "stock_quant_v2.scripts.m8_scheduler_plan"),
        M8Step(
            "scheduler_registration_check",
            "stock_quant_v2.scripts.m8_scheduler_registration_check",
            soft_fail_in_ops_profile=True,
        ),
        M8Step("export_scheduler_registration_pack", "stock_quant_v2.scripts.m8_export_scheduler_registration_pack"),
        M8Step("enhanced_final_check", "stock_quant_v2.scripts.m8_enhanced_final_check", soft_fail_in_ops_profile=True),
    ]


def _api_steps() -> list[M8Step]:
    return [
        M8Step("env_check", "stock_quant_v2.scripts.m8_env_check"),
        M8Step("startup_check", "stock_quant_v2.scripts.m8_startup_check"),
        M8Step("api_openapi_export", "stock_quant_v2.scripts.m8_api_openapi_export"),
    ]


def _full_steps() -> list[M8Step]:
    steps = _ops_steps()
    api_names = {step.name for step in steps}
    for step in _api_steps():
        if step.name not in api_names:
            steps.append(step)
    return steps


def _select_steps(profile: str) -> list[M8Step]:
    if profile == "api":
        return _api_steps()
    if profile == "full":
        return _full_steps()
    return _ops_steps()


def run_m8_ops_master_chain(args: argparse.Namespace) -> int:
    env = _build_shared_env(args)
    steps = _select_steps(args.profile)

    print("[M8] Ops master chain started.")
    print(f"[M8] profile = {args.profile}")
    print(f"[M8] report_date = {env['M8_REPORT_DATE']}")
    if env.get("M8_OUTPUT_DIR"):
        print(f"[M8] output_dir = {env['M8_OUTPUT_DIR']}")

    tracked_keys = [
        "M8_RUN_ID",
        "M8_PORTFOLIO_ID",
        "M8_TARGET_RUN_ID",
        "M8_ORDER_RUN_ID",
        "M8_FILL_RUN_ID",
        "M8_POSITION_RUN_ID",
        "M8_SNAPSHOT_RUN_ID",
        "M8_SOURCE_TARGET_RUN_ID",
        "M8_ADJUSTED_TARGET_RUN_ID",
        "M8_RISK_RUN_ID",
    ]
    for key in tracked_keys:
        if env.get(key):
            print(f"[M8] {key} = {env[key]}")

    failures: list[str] = []
    skipped: list[str] = []

    for step in steps:
        missing = _missing_required_env(step, env)
        if missing:
            skipped.append(f"{step.name} (missing env: {', '.join(missing)})")
            print(f"\n[M8][{step.name}] skipped: missing env -> {', '.join(missing)}")
            continue

        print(f"\n[M8][{step.name}] starting: {step.module_name}")
        rc, payload = _run_module(step.module_name, env)

        if step.name == "env_check":
            _inject_env_from_env_check(payload, env)
            for key in tracked_keys:
                if env.get(key):
                    print(f"[M8][env_check] inferred {key} = {env[key]}")

        if rc != 0:
            failures.append(f"{step.name} (exit_code={rc})")
            print(f"[M8][{step.name}] failed (exit_code={rc})")

            soft_fail = args.profile == "ops" and step.soft_fail_in_ops_profile
            if soft_fail:
                print(f"[M8][{step.name}] treated as soft-fail under ops profile; continuing.")
                continue

            if not args.continue_on_error:
                print("[M8] Chain stopped because continue_on_error=false.")
                return rc
        else:
            print(f"[M8][{step.name}] succeeded.")

    print("\n[M8] Ops master chain completed.")
    if skipped:
        print("[M8] Skipped steps:")
        for item in skipped:
            print(f"  - {item}")

    if failures:
        print("[M8] Failed steps:")
        for item in failures:
            print(f"  - {item}")
        return 1

    print("[M8] All runnable steps succeeded.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the M8 ops master chain. "
            "Profiles: ops (default), full, api."
        )
    )
    parser.add_argument(
        "--profile",
        choices=["ops", "full", "api"],
        default="ops",
        help="Execution profile. Default: ops.",
    )
    parser.add_argument("--report-date", help="Override M8_REPORT_DATE, format YYYY-MM-DD.")
    parser.add_argument("--output-dir", help="Optional override M8_OUTPUT_DIR.")
    parser.add_argument("--risk-run-id", type=int, help="Optional M8_RISK_RUN_ID for risk report.")
    parser.add_argument("--run-id", type=int, help="Optional M8_RUN_ID for run summary export.")
    parser.add_argument("--portfolio-id", type=int, help="Optional M8_PORTFOLIO_ID.")
    parser.add_argument("--target-run-id", type=int, help="Optional M8_TARGET_RUN_ID for paper chain export.")
    parser.add_argument("--order-run-id", type=int, help="Optional M8_ORDER_RUN_ID for paper chain export.")
    parser.add_argument("--fill-run-id", type=int, help="Optional M8_FILL_RUN_ID for paper chain export.")
    parser.add_argument("--position-run-id", type=int, help="Optional M8_POSITION_RUN_ID for paper chain export.")
    parser.add_argument("--snapshot-run-id", type=int, help="Optional M8_SNAPSHOT_RUN_ID for paper chain / snapshot export.")
    parser.add_argument("--source-target-run-id", type=int, help="Optional M8_SOURCE_TARGET_RUN_ID for risk report.")
    parser.add_argument("--adjusted-target-run-id", type=int, help="Optional M8_ADJUSTED_TARGET_RUN_ID for risk report.")

    parser.add_argument("--continue-on-error", action="store_true", help="Continue running remaining steps after a hard failure.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run_m8_ops_master_chain(args)


if __name__ == "__main__":
    raise SystemExit(main())