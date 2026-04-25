from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Optional


def calc_simple_moving_average(values: Iterable[Decimal | float | int | None]) -> Optional[Decimal]:
    normalized = [Decimal(str(v)) for v in values if v is not None]
    if not normalized:
        return None
    return sum(normalized) / Decimal(len(normalized))