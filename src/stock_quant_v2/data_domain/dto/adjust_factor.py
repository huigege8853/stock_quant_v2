from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass(slots=True)
class AdjustFactorDTO:
    provider_name: str
    market_code: str
    exchange_code: str
    ticker: str
    vendor_symbol: str | None

    trade_date: date
    adjust_factor: Decimal | None

    provider_record_key: str
    raw_payload: dict[str, Any]