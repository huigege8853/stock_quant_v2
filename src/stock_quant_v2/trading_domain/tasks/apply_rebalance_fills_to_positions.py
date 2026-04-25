from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from stock_quant_v2.trading_domain.services.paper_position_apply_fill_service import (
    PaperPositionApplyFillService,
    result_to_dict,
)


def run_apply_rebalance_fills_to_positions(
    *,
    session: Session,
    new_position_run_id: int,
    current_position_run_id: int,
    fill_run_id: int,
    portfolio_id: int,
    effective_date: date,
    replace_existing: bool = False,
    keep_closed_positions: bool = True,
) -> dict[str, Any]:
    service = PaperPositionApplyFillService(session=session)
    result = service.apply_fills_to_positions(
        new_position_run_id=new_position_run_id,
        current_position_run_id=current_position_run_id,
        fill_run_id=fill_run_id,
        portfolio_id=portfolio_id,
        effective_date=effective_date,
        replace_existing=replace_existing,
        keep_closed_positions=keep_closed_positions,
    )
    return result_to_dict(result)