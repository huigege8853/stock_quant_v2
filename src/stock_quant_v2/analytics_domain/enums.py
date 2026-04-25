from __future__ import annotations

from enum import Enum


class IndicatorCategory(str, Enum):
    PRICE = "price"
    RETURN = "return"
    TREND = "trend"
    VOLATILITY = "volatility"
    TRADABILITY = "tradability"