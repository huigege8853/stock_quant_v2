from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import date
from typing import Any

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

_REPORT_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _normalize_report_date(value: object) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    match = _REPORT_DATE_RE.search(text)
    if not match:
        return None
    return match.group(0)


def _iter_nested_values(value: Any):
    if isinstance(value, dict):
        for item in value.values():
            yield from _iter_nested_values(item)
        return

    if isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _iter_nested_values(item)
        return

    yield value


def _extract_report_date_from_result(result: dict[str, Any] | None) -> str | None:
    """
    Best-effort extraction from the M8 entrypoint result.

    M8 daily_ops artifacts are named by business data date, while M9 report_date
    is the report generation date. Therefore this function is intentionally only
    a fallback after explicit env vars. It is still useful when a scheduler pins
    the report date through a returned field or file path.
    """
    if not result:
        return None

    direct_candidates = [
        result.get("report_date"),
        result.get("requested_report_date"),
        result.get("generated_report_date"),
    ]
    daily_report = result.get("daily_report")
    if isinstance(daily_report, dict):
        direct_candidates.extend(
            [
                daily_report.get("report_date"),
                daily_report.get("requested_report_date"),
                daily_report.get("generated_report_date"),
            ]
        )

    for candidate in direct_candidates:
        normalized = _normalize_report_date(candidate)
        if normalized:
            return normalized

    # Last structured fallback: scan returned strings for a YYYY-MM-DD date.
    # This may resolve to the daily_ops business date, so date.today() remains
    # preferred when no explicit report date was supplied.
    for value in _iter_nested_values(result):
        if isinstance(value, str):
            normalized = _normalize_report_date(value)
            if normalized:
                return normalized

    return None


def _resolve_m9_report_date(result: dict[str, Any] | None = None) -> str:
    """Resolve the report_date required by M9 finalizer scripts.

    Priority:
    1. Explicit M8_REPORT_DATE, set by top-level DailyRun --report-date.
    2. Explicit M9_REPORT_DATE, reserved for M9-only scheduler overrides.
    3. A structured date from the M8 daily_ops result, if present.
    4. Local current date, so scheduler/DailyRun can run without extra env vars.
    """
    for env_name in ("M8_REPORT_DATE", "M9_REPORT_DATE"):
        normalized = _normalize_report_date(os.getenv(env_name))
        if normalized:
            return normalized

    normalized = _extract_report_date_from_result(result)
    if normalized:
        return normalized

    return date.today().isoformat()


def _m9_report_date_args(report_date: str) -> list[str]:
    return ["--report-date", report_date]


def _run_m9_finalizer(name: str, module_name: str, report_date: str) -> int:
    cmd = [sys.executable, "-m", module_name, *_m9_report_date_args(report_date)]
    print(
        f"[M8][daily_finalizer:{name}] starting: {module_name} --report-date {report_date}",
        flush=True,
    )
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


def _run_m9_finalizers_best_effort(report_date: str) -> list[dict[str, object]]:
    print("[M8] Running M9.1.1 daily finalizer reports best-effort.", flush=True)
    print(f"[M8] M9.1.1 daily finalizer report_date = {report_date}", flush=True)
    results: list[dict[str, object]] = []

    for name, module_name in M9_FINALIZER_MODULES:
        try:
            exit_code = _run_m9_finalizer(name, module_name, report_date)
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
                "report_date": report_date,
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
    result: dict[str, Any] | None = None

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
    report_date = _resolve_m9_report_date(result)
    _run_m9_finalizers_best_effort(report_date)

    if pending_error is not None:
        raise pending_error

    if scheduler_exit_code != 0:
        raise SystemExit(scheduler_exit_code)


if __name__ == "__main__":
    main()
