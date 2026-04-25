from dataclasses import dataclass

from sqlalchemy.orm import Session

from stock_quant_v2.trading_domain.services.paper_trade_ledger_service import (
    PaperTradeLedgerService,
)


@dataclass(frozen=True)
class BuildTradeLedgerTaskRequest:
    ledger_run_id: int
    portfolio_id: int
    target_run_id: int
    order_run_id: int
    fill_run_id: int
    position_snapshot_run_id: int


@dataclass(frozen=True)
class BuildTradeLedgerTaskResult:
    ledger_run_id: int
    portfolio_id: int
    target_run_id: int
    order_run_id: int
    fill_run_id: int
    position_snapshot_run_id: int
    ledger_count: int
    status: str


def build_trade_ledger(
    session: Session,
    request: BuildTradeLedgerTaskRequest,
) -> BuildTradeLedgerTaskResult:
    service = PaperTradeLedgerService(session)

    ledgers = service.build_ledger_for_chain(
        ledger_run_id=request.ledger_run_id,
        portfolio_id=request.portfolio_id,
        target_run_id=request.target_run_id,
        order_run_id=request.order_run_id,
        fill_run_id=request.fill_run_id,
        position_snapshot_run_id=request.position_snapshot_run_id,
    )

    session.flush()

    return BuildTradeLedgerTaskResult(
        ledger_run_id=request.ledger_run_id,
        portfolio_id=request.portfolio_id,
        target_run_id=request.target_run_id,
        order_run_id=request.order_run_id,
        fill_run_id=request.fill_run_id,
        position_snapshot_run_id=request.position_snapshot_run_id,
        ledger_count=len(ledgers),
        status="SUCCESS",
    )