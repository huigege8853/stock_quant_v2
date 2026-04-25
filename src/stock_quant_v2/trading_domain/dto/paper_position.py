from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class PaperPositionCreateDTO:
    run_id: int
    portfolio_id: int
    instrument_id: int
    position_date: date
    quantity: Decimal
    available_quantity: Decimal
    frozen_quantity: Decimal
    avg_cost: Decimal
    cost_amount: Decimal
    market_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    total_pnl: Decimal
    position_status: str = "OPEN"


@dataclass(frozen=True, kw_only=True)
class PaperPositionDTO(PaperPositionCreateDTO):
    id: int