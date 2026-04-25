from __future__ import annotations

from decimal import Decimal
from typing import Optional


def calc_mom_20(ret_20d: Decimal | float | int | None) -> Optional[Decimal]:
    if ret_20d is None:
        return None
    return Decimal(str(ret_20d))


def calc_trend_strength(adj_close: Decimal | float | int | None, ma_20: Decimal | float | int | None) -> Optional[Decimal]:
    if adj_close is None or ma_20 is None:
        return None

    ma20 = Decimal(str(ma_20))
    if ma20 == 0:
        return None

    close = Decimal(str(adj_close))
    return (close / ma20) - Decimal("1")