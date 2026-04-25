from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass(slots=True)
class FundamentalSnapshotDTO:
    provider_name: str
    market_code: str
    exchange_code: str
    ticker: str
    vendor_symbol: str | None
    trade_date: date
    snapshot_type: str

    pe_ttm: Decimal | None
    pb: Decimal | None
    ps_ttm: Decimal | None
    dv_ttm: Decimal | None
    total_mv: Decimal | None
    circ_mv: Decimal | None

    roe: Decimal | None
    roa: Decimal | None
    gross_margin: Decimal | None
    net_profit_yoy: Decimal | None

    report_period: date | None
    announcement_date: date | None

    provider_record_key: str
    raw_payload: dict[str, Any]