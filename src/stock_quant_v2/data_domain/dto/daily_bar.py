from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass(slots=True)
class DailyBarDTO:
    provider_name: str
    market_code: str
    exchange_code: str
    ticker: str
    vendor_symbol: str | None

    trade_date: date
    price_adjust_type: str

    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    pre_close: Decimal | None

    volume: Decimal | None
    turnover: Decimal | None
    amplitude: Decimal | None
    pct_change: Decimal | None
    price_change: Decimal | None
    turnover_rate: Decimal | None

    suspended_flag: bool

    provider_record_key: str
    raw_payload: dict[str, Any]