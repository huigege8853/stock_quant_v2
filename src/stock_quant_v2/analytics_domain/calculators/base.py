from __future__ import annotations

from decimal import Decimal
from typing import Optional


def to_decimal(value: float | int | Decimal | None, scale: int = 10) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    q = Decimal("1").scaleb(-scale)
    return Decimal(str(value)).quantize(q)