from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from stock_quant_v2.trading_domain.services.paper_position_carry_service import (
    PaperPositionCarryService,
    result_to_dict,
)


def run_carry_forward_positions(
    *,
    session: Session,
    source_position_run_id: int,
    target_position_run_id: int,
    portfolio_id: int,
    target_effective_date: date,
    source_effective_date: date | None = None,
    target_as_of_date: date | None = None,
    replace_existing: bool = False,
) -> dict[str, Any]:
    service = PaperPositionCarryService(session=session)
    result = service.carry_forward(
        source_position_run_id=source_position_run_id,
        target_position_run_id=target_position_run_id,
        portfolio_id=portfolio_id,
        source_effective_date=source_effective_date,
        target_effective_date=target_effective_date,
        target_as_of_date=target_as_of_date,
        replace_existing=replace_existing,
    )
    return result_to_dict(result)