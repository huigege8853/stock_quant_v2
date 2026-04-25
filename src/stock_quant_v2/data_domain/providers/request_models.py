from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(slots=True)
class DailyBarRequest:
    trade_date: date
    market_code: str = "CN_A"
    adjust_type: str = "RAW"