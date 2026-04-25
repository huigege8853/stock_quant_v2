from __future__ import annotations

from decimal import Decimal


def calc_tradable_flag(
    trading_status: str | None,
    is_suspended: bool,
    close_price: Decimal | float | int | None,
    up_limit_price: Decimal | float | int | None,
) -> bool:
    if trading_status != "TRADING":
        return False
    if is_suspended:
        return False
    if close_price is not None and up_limit_price is not None:
        if Decimal(str(close_price)) >= Decimal(str(up_limit_price)):
            return False
    return True