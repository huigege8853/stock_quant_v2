from __future__ import annotations

from decimal import Decimal
from statistics import pstdev
from typing import Iterable, Optional


def calc_population_std(values: Iterable[Decimal | float | int | None]) -> Optional[Decimal]:
    normalized = [float(v) for v in values if v is not None]
    if len(normalized) < 2:
        return None
    return Decimal(str(pstdev(normalized)))