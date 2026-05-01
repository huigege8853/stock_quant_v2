from __future__ import annotations

import os
import subprocess
import sys

from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.ops_domain.services.m8_scheduler_service import M8SchedulerService
from stock_quant_v2.scripts._m8_cli_utils import env_bool, env_int, env_path, env_str, print_json


M9_FINALIZER_MODULES: tuple[tuple[str, str], ...] = (
    (
        "bootstrap_m9_1_1_platform_overview_chain",
        "stock_quant_v2.scripts.bootstrap_m9_1_1_platform_overview_chain",
    ),
    (
        "bootstrap_m9_1_1_research_portfolio_daily",
        "stock_quant_v2.scripts.bootstrap_m9_1_1_research_portfolio_daily",
    ),
)


def _m9_report_date_args() -> list[str]:
    report_date = os.getenv("M8_REPORT_DATE")
    if report_date:
        return ["--report-date", report_date]
    return []


def _run_m9_finalizer(name: str, module_name: str) -> int:
    cmd = [sys.executable, "-m", module_name, *_m9_report_date_args()]
    print(f"[M8][daily_finalizer:{name}] starting: {module_name}", flush=True)
    completed = subprocess.run(cmd, check=False)
    exit_code = int(completed.returncode)
    if exit_code == 0:
        print(f"[M8][daily_finalizer:{name}] succeeded.", flush=True)
    else:
        print(
            f"[M8][daily_finalizer:{name}] soft-failed (exit_code={exit_code}).",
            flush=True,
        )
    return exit_code


def _run_m9_finalizers_best_effort() -> list[dict[str, object]]:
    print("[M8] Running M9.1.1 daily finalizer reports best-effort.", flush=True)
    results: list[dict[str, object]] = []

    for name, module_name in M9_FINALIZER_MODULES:
        try:
            exit_code = _run_m9_finalizer(name, module_name)
        except Exception as exc:  # pragma: no cover - defensive finalizer guard
            exit_code = 1
            print(
                f"[M8][daily_finalizer:{name}] soft-failed with exception: {exc}",
                flush=True,
            )

        results.append(
            {
                "name": name,
                "module": module_name,
                "exit_code": exit_code,
                "status": "PASS" if exit_code == 0 else "SOFT_FAIL",
            }
        )

    failed = [item for item in results if item["exit_code"] != 0]
    if failed:
        print("[M8] M9.1.1 daily finalizer soft-failed steps:", flush=True)
        for item in failed:
            print(f"  - {item['name']} (exit_code={item['exit_code']})", flush=True)
    return results


def main() -> None:
    portfolio_id = env_int("M8_PORTFOLIO_ID", 1)
    profile_code = env_str("M8_RISK_PROFILE_CODE")
    output_dir = env_path("M8_REPORT_OUTPUT_DIR", "artifacts/m8/daily_ops")
    fail_on_warn = env_bool("M8_FAIL_ON_WARN", False)

    if portfolio_id is None:
        raise RuntimeError("Missing env var: M8_PORTFOLIO_ID")

    scheduler_exit_code = 0
    pending_error: Exception | None = None

    session = SessionLocal()
    try:
        result = M8SchedulerService(session).daily_ops_entrypoint(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
            output_dir=output_dir,
            fail_on_warn=fail_on_warn,
        )
        print_json(result)
        scheduler_exit_code = int(result.get("scheduler_exit_code") or 0)
    except Exception as exc:
        pending_error = exc
    finally:
        session.close()

    # M9 reports explain the state produced by M8. They are best-effort finalizers:
    # they should run even when the daily ops entrypoint fails, but they must not
    # hide or replace the original M8 exit state.
    _run_m9_finalizers_best_effort()

    if pending_error is not None:
        raise pending_error

    if scheduler_exit_code != 0:
        raise SystemExit(scheduler_exit_code)


if __name__ == "__main__":
    main()
