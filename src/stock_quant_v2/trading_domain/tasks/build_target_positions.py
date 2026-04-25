from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from stock_quant_v2.trading_domain.constants import (
    DEFAULT_PORTFOLIO_CONSTRUCTION_MODE,
    DEFAULT_TARGET_COUNT,
)
from stock_quant_v2.trading_domain.dto.target_position import (
    BuildTargetPositionRequestDTO,
)
from stock_quant_v2.trading_domain.services.signal_to_target_service import (
    SignalToTargetService,
)


@dataclass(frozen=True)
class BuildTargetPositionsTaskRequest:
    run_id: int
    portfolio_id: int
    source_signal_run_id: int
    source_screen_request_id: int | None
    as_of_date: date
    effective_date: date
    construction_mode: str = DEFAULT_PORTFOLIO_CONSTRUCTION_MODE
    target_count: int = DEFAULT_TARGET_COUNT
    long_only: bool = True
    sizing_mode: str = "EQUAL_WEIGHT_BY_EQUITY"
    sizing_capital: Decimal | None = None
    price_date: date | None = None
    price_source: str = "AS_OF_CLOSE"
    lot_size: Decimal = Decimal("100")
    cash_buffer_rate: Decimal = Decimal("0")


@dataclass(frozen=True)
class BuildTargetPositionsTaskResult:
    run_id: int
    portfolio_id: int
    source_signal_run_id: int
    source_screen_request_id: int | None
    as_of_date: date
    effective_date: date
    target_position_count: int
    target_quantity_total: Decimal
    target_amount_total: Decimal
    zero_quantity_count: int
    construction_mode: str
    sizing_mode: str
    status: str


def build_target_positions(
    session: Session,
    request: BuildTargetPositionsTaskRequest,
) -> BuildTargetPositionsTaskResult:
    service = SignalToTargetService(session)

    targets = service.build_equal_weight_targets(
        BuildTargetPositionRequestDTO(
            run_id=request.run_id,
            portfolio_id=request.portfolio_id,
            source_signal_run_id=request.source_signal_run_id,
            source_screen_request_id=request.source_screen_request_id,
            as_of_date=request.as_of_date,
            effective_date=request.effective_date,
            construction_mode=request.construction_mode,
            target_count=request.target_count,
            long_only=request.long_only,
            sizing_mode=request.sizing_mode,
            sizing_capital=request.sizing_capital,
            price_date=request.price_date,
            price_source=request.price_source,
            lot_size=request.lot_size,
            cash_buffer_rate=request.cash_buffer_rate,
        )
    )

    session.flush()

    summary = session.execute(
        text(
            """
            select
                coalesce(sum(target_quantity), 0) as target_quantity_total,
                coalesce(sum(target_amount), 0) as target_amount_total,
                count(*) filter (where coalesce(target_quantity, 0) <= 0) as zero_quantity_count
            from trading_paper_target_position
            where run_id = :run_id
              and portfolio_id = :portfolio_id
            """
        ),
        {"run_id": request.run_id, "portfolio_id": request.portfolio_id},
    ).mappings().one()

    return BuildTargetPositionsTaskResult(
        run_id=request.run_id,
        portfolio_id=request.portfolio_id,
        source_signal_run_id=request.source_signal_run_id,
        source_screen_request_id=request.source_screen_request_id,
        as_of_date=request.as_of_date,
        effective_date=request.effective_date,
        target_position_count=len(targets),
        target_quantity_total=summary["target_quantity_total"],
        target_amount_total=summary["target_amount_total"],
        zero_quantity_count=int(summary["zero_quantity_count"] or 0),
        construction_mode=request.construction_mode,
        sizing_mode=request.sizing_mode,
        status="SUCCESS",
    )
