from __future__ import annotations

from decimal import Decimal
from typing import Optional


def calc_tradability_score(tradable_flag: Decimal | float | int | None) -> Optional[Decimal]:
    if tradable_flag is None:
        return None

    value = Decimal(str(tradable_flag))
    return Decimal("1") if value > 0 else Decimal("0")