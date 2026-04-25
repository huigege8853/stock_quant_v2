from __future__ import annotations

from decimal import Decimal
from typing import Optional


def calc_adj_close(close: Decimal | float | int | None, adjust_factor: Decimal | float | int | None) -> Optional[Decimal]:
    if close is None or adjust_factor is None:
        return None
    return Decimal(str(close)) * Decimal(str(adjust_factor))


def calc_return(current_value: Decimal | float | int | None, previous_value: Decimal | float | int | None) -> Optional[Decimal]:
    if current_value is None or previous_value is None:
        return None
    previous = Decimal(str(previous_value))
    current = Decimal(str(current_value))
    if previous == 0:
        return None
    return (current / previous) - Decimal("1")