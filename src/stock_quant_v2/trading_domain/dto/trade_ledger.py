from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class PaperTradeLedgerCreateDTO:
    run_id: int
    portfolio_id: int
    event_date: date
    event_type: str
    instrument_id: int | None = None
    target_position_id: int | None = None
    order_id: int | None = None
    fill_id: int | None = None
    position_id: int | None = None
    portfolio_snapshot_id: int | None = None
    quantity_delta: Decimal | None = None
    cash_delta: Decimal | None = None
    amount_delta: Decimal | None = None
    reason_code: str | None = None
    message: str | None = None
    payload_json: dict[str, Any] | None = None