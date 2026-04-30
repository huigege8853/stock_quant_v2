from __future__ import annotations

import json
import os
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.research_domain.tasks.check_backtest import (
    check_backtest_quality_first_chain,
)


def _resolve_run_id_from_env() -> int | None:
    value = os.getenv("M5_BACKTEST_RUN_ID")
    if value is None or value == "":
        return None
    return int(value)


def _resolve_latest_successful_backtest_result_run_id(session) -> int | None:
    row = session.execute(
        text(
            """
            select run_id
            from research_backtest_result
            where result_status in ('SUCCESS', 'SUCCESS_WITH_WARN')
            order by completed_at desc nulls last, id desc
            limit 1
            """
        )
    ).first()
    if not row or row[0] is None:
        return None
    return int(row[0])


def _resolve_latest_backtest_result_run_id(session) -> int | None:
    row = session.execute(
        text(
            """
            select run_id
            from research_backtest_result
            where result_status is not null
            order by completed_at desc nulls last, id desc
            limit 1
            """
        )
    ).first()
    if not row or row[0] is None:
        return None
    return int(row[0])


def _resolve_latest_backtest_request_run_id(session) -> int | None:
    row = session.execute(
        text(
            """
            select run_id
            from research_backtest_request
            order by id desc
            limit 1
            """
        )
    ).first()
    if not row or row[0] is None:
        return None
    return int(row[0])


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def main() -> None:
    run_id = _resolve_run_id_from_env()

    with SessionLocal() as session:
        if run_id is None:
            # For manual standalone use, prefer the newest completed real result.
            # A user may have just run bootstrap_m5_backtest_chain alone, which
            # creates a new skeleton request without a result. Reporting that run
            # as a traceback is noisy; the quality check should describe the most
            # recent completed M5 backtest unless M5_BACKTEST_RUN_ID is explicit.
            run_id = _resolve_latest_successful_backtest_result_run_id(session)
        if run_id is None:
            run_id = _resolve_latest_backtest_result_run_id(session)
        if run_id is None:
            run_id = _resolve_latest_backtest_request_run_id(session)
        if run_id is None:
            raise RuntimeError("no research_backtest_request or research_backtest_result found")

        try:
            result = check_backtest_quality_first_chain(session, run_id=run_id)
        except RuntimeError as exc:
            # Keep the command JSON-safe even when an explicit run_id points at a
            # skeleton request that has no research_backtest_result yet.
            result = {
                "run_id": run_id,
                "backtest_request_id": None,
                "overall_status": "FAIL",
                "execution_mode": None,
                "warnings": [],
                "checks": {
                    "result_status_check": False,
                    "trade_log_check": False,
                    "equity_curve_check": False,
                    "series_check": False,
                    "artifact_check": False,
                    "metric_check": False,
                },
                "error": str(exc),
                "notes": [
                    "No research_backtest_result exists for this run_id yet.",
                    "Run bootstrap_m5_backtest_execute with M5_BACKTEST_REQUEST_ID set, or run the full bootstrap_m5_research_refresh_chain.",
                    "If M5_BACKTEST_RUN_ID is not set, this script normally checks the latest completed real backtest result.",
                ],
            }

    print(
        json.dumps(
            {
                "run_id": run_id,
                "result": _json_safe(result),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
