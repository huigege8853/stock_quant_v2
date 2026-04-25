from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from stock_quant_v2.trading_domain.services.paper_rebalance_fill_service import (
    PaperRebalanceFillService,
    result_to_dict,
)


def run_simulate_rebalance_fills(
    *,
    session: Session,
    fill_run_id: int,
    order_run_id: int,
    portfolio_id: int,
    effective_date: date,
    commission_rate: Decimal = Decimal("0.0003"),
    min_commission: Decimal = Decimal("5"),
    stamp_duty_rate: Decimal = Decimal("0.001"),
    slippage_rate: Decimal = Decimal("0"),
    replace_existing: bool = False,
) -> dict[str, Any]:
    service = PaperRebalanceFillService(session=session)
    result = service.simulate_rebalance_fills(
        fill_run_id=fill_run_id,
        order_run_id=order_run_id,
        portfolio_id=portfolio_id,
        effective_date=effective_date,
        commission_rate=commission_rate,
        min_commission=min_commission,
        stamp_duty_rate=stamp_duty_rate,
        slippage_rate=slippage_rate,
        replace_existing=replace_existing,
    )
    return result_to_dict(result)