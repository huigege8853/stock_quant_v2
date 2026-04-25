from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class SimulatePaperFillRequestDTO:
    run_id: int
    portfolio_id: int
    effective_date: date
    execution_assumption_profile_id: int


@dataclass(frozen=True)
class PaperFillCreateDTO:
    run_id: int
    portfolio_id: int
    order_id: int
    instrument_id: int
    fill_date: date
    fill_price: Decimal
    fill_quantity: Decimal
    gross_amount: Decimal
    commission_amount: Decimal
    stamp_duty_amount: Decimal
    transfer_fee_amount: Decimal
    slippage_amount: Decimal
    total_fee_amount: Decimal
    net_amount: Decimal
    cash_delta: Decimal
    price_source: str
    fill_rule: str
    fill_status: str = "COMPLETED"


@dataclass(frozen=True, kw_only=True)
class PaperFillDTO(PaperFillCreateDTO):
    id: int