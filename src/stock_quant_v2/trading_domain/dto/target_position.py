from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class BuildTargetPositionRequestDTO:
    run_id: int
    portfolio_id: int
    source_signal_run_id: int
    source_screen_request_id: int | None
    as_of_date: date
    effective_date: date
    construction_mode: str
    target_count: int
    long_only: bool
    sizing_mode: str = "EQUAL_WEIGHT_BY_EQUITY"
    sizing_capital: Decimal | None = None
    price_date: date | None = None
    price_source: str = "AS_OF_CLOSE"
    lot_size: Decimal = Decimal("100")
    cash_buffer_rate: Decimal = Decimal("0")


@dataclass(frozen=True)
class PaperTargetPositionCreateDTO:
    run_id: int
    portfolio_id: int
    source_signal_run_id: int
    source_screen_request_id: int | None
    strategy_signal_id: int | None
    as_of_date: date
    effective_date: date
    instrument_id: int
    target_side: str
    target_weight: Decimal
    target_amount: Decimal | None
    target_quantity: Decimal | None
    rank_no: int | None
    score: Decimal | None
    reason_code: str | None
    target_source: str
    construction_mode: str
    status: str = "PENDING"
    status_reason: str | None = None


@dataclass(frozen=True, kw_only=True)
class PaperTargetPositionDTO(PaperTargetPositionCreateDTO):
    id: int
