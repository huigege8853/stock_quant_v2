from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from stock_quant_v2.trading_domain.services.paper_rebalance_service import (
    PaperRebalanceService,
    result_to_dict,
)


def run_generate_rebalance_orders(
    *,
    session: Session,
    order_run_id: int,
    portfolio_id: int,
    current_position_run_id: int,
    target_position_run_id: int,
    effective_date: date,
    as_of_date: date | None = None,
    template_order_run_id: int | None = None,
    target_quantity_source: str = "AUTO",
    replace_existing: bool = False,
    write_hold_orders: bool = False,
) -> dict[str, Any]:
    service = PaperRebalanceService(session=session)
    result = service.generate_rebalance_orders(
        order_run_id=order_run_id,
        portfolio_id=portfolio_id,
        current_position_run_id=current_position_run_id,
        target_position_run_id=target_position_run_id,
        effective_date=effective_date,
        as_of_date=as_of_date,
        template_order_run_id=template_order_run_id,
        target_quantity_source=target_quantity_source,
        replace_existing=replace_existing,
        write_hold_orders=write_hold_orders,
    )
    return result_to_dict(result)