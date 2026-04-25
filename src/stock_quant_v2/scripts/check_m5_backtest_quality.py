from __future__ import annotations

import os

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


def _resolve_latest_backtest_request_run_id() -> int:
    with SessionLocal() as session:
        row = session.execute(
            text(
                """
                SELECT run_id
                FROM research_backtest_request
                ORDER BY id DESC
                LIMIT 1
                """
            )
        ).first()

    if not row or row[0] is None:
        raise RuntimeError("latest research_backtest_request.run_id not found")

    return int(row[0])


def main() -> None:
    run_id = _resolve_run_id_from_env()
    if run_id is None:
        run_id = _resolve_latest_backtest_request_run_id()

    with SessionLocal() as session:
        result = check_backtest_quality_first_chain(session, run_id=run_id)

    print(
        {
            "run_id": run_id,
            "result": result,
        }
    )


if __name__ == "__main__":
    main()