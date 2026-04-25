from __future__ import annotations

from decimal import Decimal
from typing import Optional


def calc_forward_return(
    anchor_adj_close: Decimal | float | int | None,
    future_adj_close: Decimal | float | int | None,
) -> Optional[Decimal]:
    if anchor_adj_close is None or future_adj_close is None:
        return None

    anchor = Decimal(str(anchor_adj_close))
    future = Decimal(str(future_adj_close))
    if anchor == 0:
        return None

    return (future / anchor) - Decimal("1")


def calc_binary_up_label(forward_return: Decimal | float | int | None, threshold: Decimal | float | int) -> Optional[str]:
    if forward_return is None:
        return None
    return "1" if Decimal(str(forward_return)) >= Decimal(str(threshold)) else "0"


def calc_binary_down_label(forward_return: Decimal | float | int | None, threshold: Decimal | float | int) -> Optional[str]:
    if forward_return is None:
        return None
    return "1" if Decimal(str(forward_return)) <= Decimal(str(threshold)) else "0"