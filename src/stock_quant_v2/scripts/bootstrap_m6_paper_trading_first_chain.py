import ast
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ModuleStepResult:
    payload: dict
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0


def _clean_env(base_env: dict[str, str]) -> dict[str, str]:
    env = dict(base_env)

    keys_to_clear = [
        "M6_TARGET_RUN_ID",
        "M6_ORDER_RUN_ID",
        "M6_FILL_RUN_ID",
        "M6_LEDGER_RUN_ID",
        "M6_POSITION_SNAPSHOT_RUN_ID",
        "M6_PAPER_PORTFOLIO_ID",
    ]

    for key in keys_to_clear:
        env.pop(key, None)

    return env


def _run_module(module_name: str, extra_env: dict[str, str] | None = None) -> ModuleStepResult:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)

    proc = subprocess.run(
        [sys.executable, "-m", module_name],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[3],
        env=env,
    )

    if proc.returncode != 0:
        raise RuntimeError(
            f"submodule failed: module={module_name}, returncode={proc.returncode}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )

    payload = _parse_last_dict(proc.stdout)
    if not isinstance(payload, dict):
        raise ValueError(f"parsed payload is not dict: module={module_name}, payload={payload}")

    return ModuleStepResult(
        payload=payload,
        stdout=proc.stdout,
        stderr=proc.stderr,
        returncode=proc.returncode,
    )


def _parse_last_dict(stdout: str) -> dict:
    text = (stdout or "").strip()
    if not text:
        raise ValueError("cannot parse dict output from empty stdout")

    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    try:
        obj = ast.literal_eval(text)
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
            pass

        try:
            obj = ast.literal_eval(candidate)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

    raise ValueError(f"cannot parse dict output from stdout: {stdout}")


def _require_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if value is None:
        raise ValueError(f"missing key in payload: {key}, payload={payload}")
    return int(value)


def _require_status_success(payload: dict[str, Any]) -> None:
    status = payload.get("status")
    if status != "SUCCESS":
        raise ValueError(f"step status is not SUCCESS: payload={payload}")


def main() -> None:
    env = _clean_env(os.environ)

    source_signal_run_id = env.get("M6_SOURCE_SIGNAL_RUN_ID")
    source_screen_request_id = env.get("M6_SOURCE_SCREEN_REQUEST_ID")
    as_of_date = env.get("M6_AS_OF_DATE")
    effective_date = env.get("M6_EFFECTIVE_DATE")
    target_count = env.get("M6_TARGET_COUNT", "30")

    if not source_signal_run_id:
        raise RuntimeError("M6_SOURCE_SIGNAL_RUN_ID is required.")
    if not source_screen_request_id:
        raise RuntimeError("M6_SOURCE_SCREEN_REQUEST_ID is required.")
    if not as_of_date:
        raise RuntimeError("M6_AS_OF_DATE is required.")
    if not effective_date:
        raise RuntimeError("M6_EFFECTIVE_DATE is required.")

    common = {
        "M6_PAPER_ACCOUNT_CODE": env.get(
            "M6_PAPER_ACCOUNT_CODE",
            "paper_cn_a_default",
        ),
        "M6_PAPER_PORTFOLIO_CODE": env.get(
            "M6_PAPER_PORTFOLIO_CODE",
            "paper_alpha_selection_v1_default",
        ),
        "M6_STRATEGY_VERSION_ID": env.get("M6_STRATEGY_VERSION_ID", "1"),
        "M6_EXECUTION_ASSUMPTION_PROFILE_ID": env.get(
            "M6_EXECUTION_ASSUMPTION_PROFILE_ID",
            "1",
        ),
        "M6_SOURCE_SIGNAL_RUN_ID": source_signal_run_id,
        "M6_SOURCE_SCREEN_REQUEST_ID": source_screen_request_id,
        "M6_AS_OF_DATE": as_of_date,
        "M6_EFFECTIVE_DATE": effective_date,
        "M6_START_DATE": effective_date,
        "M6_TARGET_DATE": env.get("M6_TARGET_DATE", effective_date),
        "M6_TRADE_DATE": env.get("M6_TRADE_DATE", effective_date),
        "M6_TARGET_COUNT": target_count,
        "M6_INITIAL_CASH": env.get("M6_INITIAL_CASH", "10000000"),
        "M6_PORTFOLIO_CONSTRUCTION_MODE": env.get(
            "M6_PORTFOLIO_CONSTRUCTION_MODE",
            "EQUAL_WEIGHT_SELECTED",
        ),
    }

    results: dict[str, dict[str, Any]] = {}

    account_step = _run_module(
        "stock_quant_v2.scripts.bootstrap_m6_paper_account",
        common,
    )
    _require_status_success(account_step.payload)
    results["account"] = account_step.payload

    portfolio_id = _require_int(account_step.payload, "portfolio_id")

    target_step = _run_module(
        "stock_quant_v2.scripts.bootstrap_m6_target_position_chain",
        {
            **common,
            "M6_PAPER_PORTFOLIO_ID": str(portfolio_id),
        },
    )
    _require_status_success(target_step.payload)
    results["target"] = target_step.payload

    target_run_id = _require_int(target_step.payload, "run_id")

    order_step = _run_module(
        "stock_quant_v2.scripts.bootstrap_m6_paper_order_chain",
        {
            **common,
            "M6_PAPER_PORTFOLIO_ID": str(portfolio_id),
            "M6_TARGET_RUN_ID": str(target_run_id),
        },
    )
    _require_status_success(order_step.payload)
    results["order"] = order_step.payload

    order_run_id = _require_int(order_step.payload, "order_run_id")

    fill_step = _run_module(
        "stock_quant_v2.scripts.bootstrap_m6_paper_fill_chain",
        {
            **common,
            "M6_PAPER_PORTFOLIO_ID": str(portfolio_id),
            "M6_ORDER_RUN_ID": str(order_run_id),
        },
    )
    _require_status_success(fill_step.payload)
    results["fill"] = fill_step.payload

    fill_run_id = _require_int(fill_step.payload, "fill_run_id")

    resolved_effective_date = str(fill_step.payload.get("effective_date", effective_date))
    common["M6_EFFECTIVE_DATE"] = resolved_effective_date
    common["M6_START_DATE"] = resolved_effective_date
    common["M6_TARGET_DATE"] = resolved_effective_date
    common["M6_TRADE_DATE"] = resolved_effective_date

    position_step = _run_module(
        "stock_quant_v2.scripts.bootstrap_m6_paper_position_snapshot_chain",
        {
            **common,
            "M6_PAPER_PORTFOLIO_ID": str(portfolio_id),
            "M6_FILL_RUN_ID": str(fill_run_id),
            "M6_SNAPSHOT_DATE": resolved_effective_date,
        },
    )
    _require_status_success(position_step.payload)
    results["position_snapshot"] = position_step.payload

    position_snapshot_run_id = _require_int(position_step.payload, "run_id")

    ledger_step = _run_module(
        "stock_quant_v2.scripts.bootstrap_m6_trade_ledger_chain",
        {
            **common,
            "M6_PAPER_PORTFOLIO_ID": str(portfolio_id),
            "M6_TARGET_RUN_ID": str(target_run_id),
            "M6_ORDER_RUN_ID": str(order_run_id),
            "M6_FILL_RUN_ID": str(fill_run_id),
            "M6_POSITION_SNAPSHOT_RUN_ID": str(position_snapshot_run_id),
        },
    )
    _require_status_success(ledger_step.payload)
    results["ledger"] = ledger_step.payload

    ledger_run_id = _require_int(ledger_step.payload, "ledger_run_id")

    run_result_step = _run_module(
        "stock_quant_v2.scripts.bootstrap_m6_run_results_chain",
        {
            **common,
            "M6_PAPER_PORTFOLIO_ID": str(portfolio_id),
            "M6_TARGET_RUN_ID": str(target_run_id),
            "M6_ORDER_RUN_ID": str(order_run_id),
            "M6_FILL_RUN_ID": str(fill_run_id),
            "M6_LEDGER_RUN_ID": str(ledger_run_id),
            "M6_POSITION_SNAPSHOT_RUN_ID": str(position_snapshot_run_id),
        },
    )
    _require_status_success(run_result_step.payload)
    results["run_results"] = run_result_step.payload

    quality_step = _run_module(
        "stock_quant_v2.scripts.check_m6_paper_trading_quality",
        {
            **common,
            "M6_PAPER_PORTFOLIO_ID": str(portfolio_id),
            "M6_TARGET_RUN_ID": str(target_run_id),
            "M6_ORDER_RUN_ID": str(order_run_id),
            "M6_FILL_RUN_ID": str(fill_run_id),
            "M6_POSITION_SNAPSHOT_RUN_ID": str(position_snapshot_run_id),
        },
    )
    results["quality"] = quality_step.payload

    if quality_step.payload.get("overall_status") != "PASS":
        raise RuntimeError(f"M6 quality check failed: {quality_step.payload}")

    final_result = {
        "status": "SUCCESS",
        "overall_status": "PASS",
        "portfolio_id": portfolio_id,
        "source_signal_run_id": int(source_signal_run_id),
        "source_screen_request_id": int(source_screen_request_id),
        "as_of_date": as_of_date,
        "requested_effective_date": effective_date,
        "effective_date": resolved_effective_date,
        "target_run_id": target_run_id,
        "order_run_id": order_run_id,
        "fill_run_id": fill_run_id,
        "position_snapshot_run_id": position_snapshot_run_id,
        "ledger_run_id": ledger_run_id,
        "metric_written": results["run_results"].get("metric_written"),
        "series_written": results["run_results"].get("series_written"),
        "quality_checks": results["quality"].get("checks"),
    }

    print(final_result)


if __name__ == "__main__":
    main()