from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from stock_quant_v2.trading_domain.services.paper_fill_service import (
    PaperFillService,
)


@dataclass(frozen=True)
class SimulatePaperFillsTaskRequest:
    fill_run_id: int
    order_run_id: int
    portfolio_id: int
    effective_date: date


@dataclass(frozen=True)
class SimulatePaperFillsTaskResult:
    fill_run_id: int
    order_run_id: int
    portfolio_id: int
    effective_date: date
    fill_count: int
    status: str


def simulate_paper_fills(
    session: Session,
    request: SimulatePaperFillsTaskRequest,
) -> SimulatePaperFillsTaskResult:
    service = PaperFillService(session)

    fills = service.simulate_fills_from_orders(
        fill_run_id=request.fill_run_id,
        order_run_id=request.order_run_id,
        portfolio_id=request.portfolio_id,
        effective_date=request.effective_date,
    )

    session.flush()

    return SimulatePaperFillsTaskResult(
        fill_run_id=request.fill_run_id,
        order_run_id=request.order_run_id,
        portfolio_id=request.portfolio_id,
        effective_date=request.effective_date,
        fill_count=len(fills),
        status="SUCCESS",
    )