from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from stock_quant_v2.trading_domain.services.ops_run_ensure_service import (
    OpsRunEnsureService,
)

from stock_quant_v2.trading_domain.services.paper_position_apply_fill_service import (
    PaperPositionApplyFillService,
)
from stock_quant_v2.trading_domain.services.paper_position_carry_service import (
    PaperPositionCarryService,
)
from stock_quant_v2.trading_domain.services.paper_portfolio_snapshot_m7_service import (
    PaperPortfolioSnapshotM7Service,
)
from stock_quant_v2.trading_domain.services.paper_rebalance_fill_service import (
    PaperRebalanceFillService,
)
from stock_quant_v2.trading_domain.services.paper_rebalance_service import (
    PaperRebalanceService,
)


@dataclass(frozen=True)
class PaperTradingDailyPlan:
    """M7.6 single-day rebalance plan.

    Naming convention:
    - source_position_run_id: previous final position run.
    - carry_position_run_id: pre-trade current position run after T+1 carry.
    - position_run_id: final position run after fills.
    - previous_snapshot_run_id: previous portfolio snapshot run.
    - snapshot_run_id: new portfolio snapshot run.
    """

    portfolio_id: int
    as_of_date: date
    effective_date: date
    source_position_run_id: int
    carry_position_run_id: int
    target_position_run_id: int
    order_run_id: int
    fill_run_id: int
    position_run_id: int
    previous_snapshot_run_id: int
    snapshot_run_id: int
    source_effective_date: date | None = None
    template_order_run_id: int | None = None
    target_quantity_source: str = "AUTO"
    replace_existing: bool = False
    write_hold_orders: bool = False
    keep_closed_positions: bool = True
    commission_rate: Decimal = Decimal("0.0003")
    min_commission: Decimal = Decimal("5")
    stamp_duty_rate: Decimal = Decimal("0.001")
    slippage_rate: Decimal = Decimal("0")


@dataclass(frozen=True)
class PaperTradingDailyResult:
    portfolio_id: int
    as_of_date: str
    effective_date: str
    source_position_run_id: int
    carry_position_run_id: int
    target_position_run_id: int
    order_run_id: int
    fill_run_id: int
    position_run_id: int
    previous_snapshot_run_id: int
    snapshot_run_id: int
    carry_result: dict[str, Any]
    order_result: dict[str, Any]
    fill_result: dict[str, Any]
    position_result: dict[str, Any]
    snapshot_result: dict[str, Any]
    status: str


class PaperTradingOrchestrator:
    """M7.6 daily paper-trading rebalance orchestrator.

    This class stitches together the verified M7.1 -> M7.3-C services:
    carry -> rebalance order -> fill -> position after fill -> portfolio snapshot.
    It auto-creates lightweight ops_run placeholder rows for explicit M7.6 run ids
    before inserting child rows, so FK constraints remain valid.
    """

    def __init__(self, session: Session):
        self.session = session

    def _ensure_ops_runs(self, *, plan: PaperTradingDailyPlan) -> None:
        OpsRunEnsureService(self.session).ensure_many(
            run_ids_by_role={
                "carry_position": plan.carry_position_run_id,
                "order": plan.order_run_id,
                "fill": plan.fill_run_id,
                "position": plan.position_run_id,
                "snapshot": plan.snapshot_run_id,
            },
            portfolio_id=plan.portfolio_id,
            effective_date=plan.effective_date,
            as_of_date=plan.as_of_date,
            module_code="M7",
            run_prefix="m7_6_paper_trading",
        )
        self.session.flush()

    def run_daily_rebalance(self, *, plan: PaperTradingDailyPlan) -> PaperTradingDailyResult:
        self._ensure_ops_runs(plan=plan)

        carry_result_obj = PaperPositionCarryService(self.session).carry_forward(
            source_position_run_id=plan.source_position_run_id,
            target_position_run_id=plan.carry_position_run_id,
            portfolio_id=plan.portfolio_id,
            source_effective_date=plan.source_effective_date,
            target_effective_date=plan.effective_date,
            target_as_of_date=plan.as_of_date,
            replace_existing=plan.replace_existing,
        )
        self.session.flush()

        order_result_obj = PaperRebalanceService(self.session).generate_rebalance_orders(
            order_run_id=plan.order_run_id,
            portfolio_id=plan.portfolio_id,
            current_position_run_id=plan.carry_position_run_id,
            target_position_run_id=plan.target_position_run_id,
            effective_date=plan.effective_date,
            as_of_date=plan.as_of_date,
            template_order_run_id=plan.template_order_run_id,
            target_quantity_source=plan.target_quantity_source,
            replace_existing=plan.replace_existing,
            write_hold_orders=plan.write_hold_orders,
        )
        self.session.flush()

        fill_result_obj = PaperRebalanceFillService(self.session).simulate_rebalance_fills(
            fill_run_id=plan.fill_run_id,
            order_run_id=plan.order_run_id,
            portfolio_id=plan.portfolio_id,
            effective_date=plan.effective_date,
            commission_rate=plan.commission_rate,
            min_commission=plan.min_commission,
            stamp_duty_rate=plan.stamp_duty_rate,
            slippage_rate=plan.slippage_rate,
            replace_existing=plan.replace_existing,
        )
        self.session.flush()

        position_result_obj = PaperPositionApplyFillService(self.session).apply_fills_to_positions(
            new_position_run_id=plan.position_run_id,
            current_position_run_id=plan.carry_position_run_id,
            fill_run_id=plan.fill_run_id,
            portfolio_id=plan.portfolio_id,
            effective_date=plan.effective_date,
            replace_existing=plan.replace_existing,
            keep_closed_positions=plan.keep_closed_positions,
        )
        self.session.flush()

        snapshot_result_obj = PaperPortfolioSnapshotM7Service(self.session).build_snapshot(
            snapshot_run_id=plan.snapshot_run_id,
            previous_snapshot_run_id=plan.previous_snapshot_run_id,
            position_run_id=plan.position_run_id,
            fill_run_id=plan.fill_run_id,
            portfolio_id=plan.portfolio_id,
            snapshot_date=plan.effective_date,
            replace_existing=plan.replace_existing,
        )
        self.session.flush()

        return PaperTradingDailyResult(
            portfolio_id=plan.portfolio_id,
            as_of_date=plan.as_of_date.isoformat(),
            effective_date=plan.effective_date.isoformat(),
            source_position_run_id=plan.source_position_run_id,
            carry_position_run_id=plan.carry_position_run_id,
            target_position_run_id=plan.target_position_run_id,
            order_run_id=plan.order_run_id,
            fill_run_id=plan.fill_run_id,
            position_run_id=plan.position_run_id,
            previous_snapshot_run_id=plan.previous_snapshot_run_id,
            snapshot_run_id=plan.snapshot_run_id,
            carry_result=asdict(carry_result_obj),
            order_result=asdict(order_result_obj),
            fill_result=asdict(fill_result_obj),
            position_result=asdict(position_result_obj),
            snapshot_result=asdict(snapshot_result_obj),
            status="SUCCESS",
        )


def result_to_dict(result: PaperTradingDailyResult) -> dict[str, Any]:
    return asdict(result)
