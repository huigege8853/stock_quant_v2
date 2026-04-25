from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from stock_quant_v2.trading_domain.services.paper_position_snapshot_service import (
    PaperPositionSnapshotService,
)


@dataclass(frozen=True)
class UpdatePaperPositionsTaskRequest:
    run_id: int
    fill_run_id: int
    portfolio_id: int
    snapshot_date: date


@dataclass(frozen=True)
class UpdatePaperPositionsTaskResult:
    run_id: int
    fill_run_id: int
    portfolio_id: int
    snapshot_date: date
    position_count: int
    snapshot_id: int
    status: str


def update_paper_positions(
    session: Session,
    request: UpdatePaperPositionsTaskRequest,
) -> UpdatePaperPositionsTaskResult:
    service = PaperPositionSnapshotService(session)

    positions, snapshot = service.build_positions_and_snapshot_from_fills(
        run_id=request.run_id,
        fill_run_id=request.fill_run_id,
        portfolio_id=request.portfolio_id,
        snapshot_date=request.snapshot_date,
    )

    session.flush()

    return UpdatePaperPositionsTaskResult(
        run_id=request.run_id,
        fill_run_id=request.fill_run_id,
        portfolio_id=request.portfolio_id,
        snapshot_date=request.snapshot_date,
        position_count=len(positions),
        snapshot_id=snapshot.id,
        status="SUCCESS",
    )