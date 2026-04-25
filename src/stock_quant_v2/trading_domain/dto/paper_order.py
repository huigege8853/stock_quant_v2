from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class GeneratePaperOrderRequestDTO:
    run_id: int
    portfolio_id: int
    effective_date: date
    price_fill_rule: str
    cash_rule: str
    lot_size: int


@dataclass(frozen=True)
class PaperOrderCreateDTO:
    run_id: int
    portfolio_id: int
    target_position_id: int | None
    instrument_id: int
    order_date: date
    effective_date: date
    order_side: str
    order_type: str
    price_fill_rule: str
    time_in_force: str
    target_quantity: Decimal | None
    order_quantity: Decimal
    estimated_price: Decimal
    estimated_gross_amount: Decimal
    estimated_fee: Decimal
    estimated_net_amount: Decimal
    status: str = "NEW"
    reject_reason: str | None = None


@dataclass(frozen=True, kw_only=True)
class PaperOrderDTO(PaperOrderCreateDTO):
    id: int