from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from stock_quant_v2.trading_domain.services.paper_order_service import (
    PaperOrderService,
)


@dataclass(frozen=True)
class GeneratePaperOrdersTaskRequest:
    order_run_id: int
    target_run_id: int
    portfolio_id: int
    effective_date: date


@dataclass(frozen=True)
class GeneratePaperOrdersTaskResult:
    order_run_id: int
    target_run_id: int
    portfolio_id: int
    effective_date: date
    order_count: int
    status: str


def generate_paper_orders(
    session: Session,
    request: GeneratePaperOrdersTaskRequest,
) -> GeneratePaperOrdersTaskResult:
    service = PaperOrderService(session)

    orders = service.generate_orders_from_target_positions(
        order_run_id=request.order_run_id,
        target_run_id=request.target_run_id,
        portfolio_id=request.portfolio_id,
        effective_date=request.effective_date,
    )

    session.flush()

    return GeneratePaperOrdersTaskResult(
        order_run_id=request.order_run_id,
        target_run_id=request.target_run_id,
        portfolio_id=request.portfolio_id,
        effective_date=request.effective_date,
        order_count=len(orders),
        status="SUCCESS",
    )