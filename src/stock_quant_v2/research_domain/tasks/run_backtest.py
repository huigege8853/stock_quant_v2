from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from stock_quant_v2.research_domain.dto.backtest import BacktestRequestDTO
from stock_quant_v2.research_domain.services.backtest_request_service import (
    BacktestRequestService,
)
from stock_quant_v2.research_domain.services.backtest_result_service import (
    BacktestResultService,
)
from stock_quant_v2.research_domain.services.backtest_execution_plan_service import (
    BacktestExecutionPlanService,
)
from stock_quant_v2.research_domain.services.backtest_real_execution_service import (
    BacktestRealExecutionService,
)


def create_backtest_request_first_chain(
    session: Session,
    dto: BacktestRequestDTO,
) -> dict[str, Any]:
    return BacktestRequestService(session).create_backtest_request(dto)


def create_backtest_result_placeholder_first_chain(
    session: Session,
    *,
    backtest_request_id: int | None = None,
) -> dict[str, Any]:
    return BacktestResultService(session).create_placeholder_result(
        backtest_request_id=backtest_request_id,
    )


def build_backtest_execution_plan_first_chain(
    session: Session,
    *,
    backtest_request_id: int | None = None,
) -> dict[str, Any]:
    return BacktestExecutionPlanService(session).build_execution_plan(
        backtest_request_id=backtest_request_id,
    )


def execute_minimal_backtest_first_chain(
    session: Session,
    *,
    backtest_request_id: int | None = None,
) -> dict[str, Any]:
    return BacktestRealExecutionService(session).execute_minimal_backtest(
        backtest_request_id=backtest_request_id,
    )