from __future__ import annotations

import json
import os
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.research_domain.services.backtest_real_execution_service import (
    BacktestRealExecutionService,
)


def _env_int(name: str, default: int | None = None) -> int | None:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


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


def _resolve_latest_core_daily_bar_date(session) -> Any | None:
    return session.execute(text("select max(trade_date) from core_daily_bar")).scalar()


def _resolve_default_backtest_request_id(session) -> int:
    """Resolve a safe default request for standalone execution.

    During M5.10, ``bootstrap_m5_backtest_chain`` can still be run by itself and
    may create a historical skeleton request using its own older default end_date
    (for example 2024-12-31). If ``bootstrap_m5_backtest_execute`` blindly picks
    that newest request, the selected latest signal basket may have no common
    executable bar in that old window.

    The full ``bootstrap_m5_research_refresh_chain`` passes
    ``M5_BACKTEST_REQUEST_ID`` explicitly, so this resolver only affects manual
    standalone execution. It prefers the newest request whose end_date reaches
    the latest loaded daily-bar waterline, then falls back to the newest request.
    """

    latest_bar_date = _resolve_latest_core_daily_bar_date(session)

    if latest_bar_date is not None:
        row = session.execute(
            text(
                """
                select id
                from research_backtest_request
                where end_date >= :latest_bar_date
                order by id desc
                limit 1
                """
            ),
            {"latest_bar_date": latest_bar_date},
        ).first()
        if row and row[0] is not None:
            return int(row[0])

    row = session.execute(
        text(
            """
            select id
            from research_backtest_request
            order by id desc
            limit 1
            """
        )
    ).first()
    if not row or row[0] is None:
        raise RuntimeError("no research_backtest_request found")
    return int(row[0])


def main() -> None:
    backtest_request_id = _env_int("M5_BACKTEST_REQUEST_ID")

    with SessionLocal() as session:
        if backtest_request_id is None:
            backtest_request_id = _resolve_default_backtest_request_id(session)
            print(f"[M5][backtest_execute] default M5_BACKTEST_REQUEST_ID={backtest_request_id}")
        else:
            print(f"[M5][backtest_execute] using M5_BACKTEST_REQUEST_ID={backtest_request_id}")

        try:
            result = BacktestRealExecutionService(session).execute_minimal_backtest(
                backtest_request_id=backtest_request_id,
            )
        except Exception:
            session.rollback()
            raise

    print(json.dumps(_json_safe(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
