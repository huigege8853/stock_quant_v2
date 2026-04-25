from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from stock_quant_v2.trading_domain.services.paper_trading_orchestrator import (
    PaperTradingDailyPlan,
    PaperTradingOrchestrator,
    result_to_dict,
)


def run_paper_trading_daily(
    *,
    session: Session,
    portfolio_id: int,
    as_of_date: date,
    effective_date: date,
    source_position_run_id: int,
    carry_position_run_id: int,
    target_position_run_id: int,
    order_run_id: int,
    fill_run_id: int,
    position_run_id: int,
    previous_snapshot_run_id: int,
    snapshot_run_id: int,
    source_effective_date: date | None = None,
    template_order_run_id: int | None = None,
    target_quantity_source: str = "AUTO",
    replace_existing: bool = False,
    write_hold_orders: bool = False,
    keep_closed_positions: bool = True,
    commission_rate: Decimal = Decimal("0.0003"),
    min_commission: Decimal = Decimal("5"),
    stamp_duty_rate: Decimal = Decimal("0.001"),
    slippage_rate: Decimal = Decimal("0"),
) -> dict[str, Any]:
    plan = PaperTradingDailyPlan(
        portfolio_id=portfolio_id,
        as_of_date=as_of_date,
        effective_date=effective_date,
        source_position_run_id=source_position_run_id,
        carry_position_run_id=carry_position_run_id,
        target_position_run_id=target_position_run_id,
        order_run_id=order_run_id,
        fill_run_id=fill_run_id,
        position_run_id=position_run_id,
        previous_snapshot_run_id=previous_snapshot_run_id,
        snapshot_run_id=snapshot_run_id,
        source_effective_date=source_effective_date,
        template_order_run_id=template_order_run_id,
        target_quantity_source=target_quantity_source,
        replace_existing=replace_existing,
        write_hold_orders=write_hold_orders,
        keep_closed_positions=keep_closed_positions,
        commission_rate=commission_rate,
        min_commission=min_commission,
        stamp_duty_rate=stamp_duty_rate,
        slippage_rate=slippage_rate,
    )
    result = PaperTradingOrchestrator(session=session).run_daily_rebalance(plan=plan)
    return result_to_dict(result)
