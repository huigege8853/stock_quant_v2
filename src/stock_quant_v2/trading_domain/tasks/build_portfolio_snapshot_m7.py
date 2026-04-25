from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from stock_quant_v2.trading_domain.services.paper_portfolio_snapshot_m7_service import (
    PaperPortfolioSnapshotM7Service,
    result_to_dict,
)


def run_build_portfolio_snapshot_m7(
    *,
    session: Session,
    snapshot_run_id: int,
    previous_snapshot_run_id: int,
    position_run_id: int,
    fill_run_id: int,
    portfolio_id: int,
    snapshot_date: date,
    replace_existing: bool = False,
) -> dict[str, Any]:
    service = PaperPortfolioSnapshotM7Service(session=session)
    result = service.build_snapshot(
        snapshot_run_id=snapshot_run_id,
        previous_snapshot_run_id=previous_snapshot_run_id,
        position_run_id=position_run_id,
        fill_run_id=fill_run_id,
        portfolio_id=portfolio_id,
        snapshot_date=snapshot_date,
        replace_existing=replace_existing,
    )
    return result_to_dict(result)