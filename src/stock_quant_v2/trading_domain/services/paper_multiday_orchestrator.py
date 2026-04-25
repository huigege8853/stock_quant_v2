from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from stock_quant_v2.trading_domain.services.paper_trading_orchestrator import (
    PaperTradingDailyPlan,
    PaperTradingDailyResult,
    PaperTradingOrchestrator,
)


@dataclass(frozen=True)
class PaperTradingDateRangePlan:
    """M7.6 date-range plan.

    Each daily plan must provide its own run ids. For day 2+, source_position_run_id
    and previous_snapshot_run_id can be omitted by passing 0; they will be chained
    from the previous day's position_run_id and snapshot_run_id.
    """

    daily_plans: list[PaperTradingDailyPlan]
    chain_previous_outputs: bool = True
    stop_on_error: bool = True


@dataclass(frozen=True)
class PaperTradingDateRangeResult:
    first_effective_date: str | None
    last_effective_date: str | None
    day_count: int
    success_count: int
    failed_count: int
    final_position_run_id: int | None
    final_snapshot_run_id: int | None
    daily_results: list[dict[str, Any]]
    status: str


class PaperMultidayOrchestrator:
    """M7.6 multi-day paper-trading orchestrator.

    Scope: orchestration only. It reuses the already verified daily chain and does
    not introduce target sizing, signal generation, risk rules, API, or scheduler.
    """

    def __init__(self, session: Session):
        self.session = session
        self.daily_orchestrator = PaperTradingOrchestrator(session=session)

    def run_date_range(self, *, plan: PaperTradingDateRangePlan) -> PaperTradingDateRangeResult:
        if not plan.daily_plans:
            return PaperTradingDateRangeResult(
                first_effective_date=None,
                last_effective_date=None,
                day_count=0,
                success_count=0,
                failed_count=0,
                final_position_run_id=None,
                final_snapshot_run_id=None,
                daily_results=[],
                status="SUCCESS",
            )

        sorted_plans = sorted(plan.daily_plans, key=lambda item: item.effective_date)
        daily_results: list[dict[str, Any]] = []
        success_count = 0
        failed_count = 0
        previous_position_run_id: int | None = None
        previous_snapshot_run_id: int | None = None

        for index, raw_daily_plan in enumerate(sorted_plans):
            daily_plan = raw_daily_plan

            if plan.chain_previous_outputs and index > 0:
                if previous_position_run_id is None or previous_snapshot_run_id is None:
                    raise RuntimeError("无法串联多日推进：上一日输出 run_id 不完整。")

                daily_plan = PaperTradingDailyPlan(
                    portfolio_id=raw_daily_plan.portfolio_id,
                    as_of_date=raw_daily_plan.as_of_date,
                    effective_date=raw_daily_plan.effective_date,
                    source_position_run_id=(
                        raw_daily_plan.source_position_run_id or previous_position_run_id
                    ),
                    carry_position_run_id=raw_daily_plan.carry_position_run_id,
                    target_position_run_id=raw_daily_plan.target_position_run_id,
                    order_run_id=raw_daily_plan.order_run_id,
                    fill_run_id=raw_daily_plan.fill_run_id,
                    position_run_id=raw_daily_plan.position_run_id,
                    previous_snapshot_run_id=(
                        raw_daily_plan.previous_snapshot_run_id or previous_snapshot_run_id
                    ),
                    snapshot_run_id=raw_daily_plan.snapshot_run_id,
                    source_effective_date=raw_daily_plan.source_effective_date,
                    template_order_run_id=raw_daily_plan.template_order_run_id,
                    target_quantity_source=raw_daily_plan.target_quantity_source,
                    replace_existing=raw_daily_plan.replace_existing,
                    write_hold_orders=raw_daily_plan.write_hold_orders,
                    keep_closed_positions=raw_daily_plan.keep_closed_positions,
                    commission_rate=raw_daily_plan.commission_rate,
                    min_commission=raw_daily_plan.min_commission,
                    stamp_duty_rate=raw_daily_plan.stamp_duty_rate,
                    slippage_rate=raw_daily_plan.slippage_rate,
                )

            try:
                result = self.daily_orchestrator.run_daily_rebalance(plan=daily_plan)
                result_dict = asdict(result)
                daily_results.append(result_dict)
                success_count += 1
                previous_position_run_id = result.position_run_id
                previous_snapshot_run_id = result.snapshot_run_id
            except Exception as exc:  # noqa: BLE001
                failed_count += 1
                failure_payload = {
                    "portfolio_id": daily_plan.portfolio_id,
                    "as_of_date": daily_plan.as_of_date.isoformat(),
                    "effective_date": daily_plan.effective_date.isoformat(),
                    "source_position_run_id": daily_plan.source_position_run_id,
                    "carry_position_run_id": daily_plan.carry_position_run_id,
                    "target_position_run_id": daily_plan.target_position_run_id,
                    "order_run_id": daily_plan.order_run_id,
                    "fill_run_id": daily_plan.fill_run_id,
                    "position_run_id": daily_plan.position_run_id,
                    "previous_snapshot_run_id": daily_plan.previous_snapshot_run_id,
                    "snapshot_run_id": daily_plan.snapshot_run_id,
                    "status": "FAILED",
                    "error": str(exc),
                }
                daily_results.append(failure_payload)
                if plan.stop_on_error:
                    raise

        status = "SUCCESS" if failed_count == 0 else "PARTIAL_SUCCESS"
        if success_count == 0 and failed_count > 0:
            status = "FAILED"

        return PaperTradingDateRangeResult(
            first_effective_date=sorted_plans[0].effective_date.isoformat(),
            last_effective_date=sorted_plans[-1].effective_date.isoformat(),
            day_count=len(sorted_plans),
            success_count=success_count,
            failed_count=failed_count,
            final_position_run_id=previous_position_run_id,
            final_snapshot_run_id=previous_snapshot_run_id,
            daily_results=daily_results,
            status=status,
        )


def result_to_dict(result: PaperTradingDateRangeResult) -> dict[str, Any]:
    return asdict(result)
