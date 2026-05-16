from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


_NON_TRADABLE_STATUS_VALUES = {
    "SUSPENDED",
    "SUSPEND",
    "HALT",
    "HALTED",
    "PAUSED",
    "STOP",
    "STOPPED",
    "DELISTED",
    "退市",
    "停牌",
}

_MISSING_OR_UNKNOWN_STATUS_VALUES = {
    "",
    "NO_BAR",
    "UNKNOWN",
    "MISSING",
    "NONE",
    "NULL",
}


def _to_decimal(value: Any | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _is_positive(value: Any | None) -> bool:
    decimal_value = _to_decimal(value)
    return decimal_value is not None and decimal_value > 0


def _normalize_status(trading_status: str | None) -> str:
    if trading_status is None:
        return ""
    return str(trading_status).strip().upper()


def calc_tradable_flag(
    trading_status: str | None,
    is_suspended: bool,
    close_price: Decimal | float | int | None,
    up_limit_price: Decimal | float | int | None,
    volume: Decimal | float | int | None = None,
    amount: Decimal | float | int | None = None,
) -> bool:
    """Return whether an instrument is tradable for M3 daily feature purposes.

    The first-chain M3 implementation only trusted ``core_instrument_status_daily``.
    In the current research DB this table can be incomplete, so the SQL loader supplies
    ``NO_BAR`` even when ``core_daily_bar`` clearly has a valid bar with positive volume
    and amount.  For S2 readiness, a missing status row must not force every stock to
    non-tradable.  We therefore use daily-bar liquidity as a conservative fallback only
    when the status is missing/unknown.
    """

    if is_suspended:
        return False

    close_value = _to_decimal(close_price)
    if close_value is None or close_value <= 0:
        return False

    up_limit_value = _to_decimal(up_limit_price)
    if up_limit_value is not None and close_value >= up_limit_value:
        # For a buy-side candidate list, limit-up names are not considered tradable.
        return False

    normalized_status = _normalize_status(trading_status)
    if normalized_status in _NON_TRADABLE_STATUS_VALUES:
        return False

    if normalized_status == "TRADING":
        return True

    if normalized_status in _MISSING_OR_UNKNOWN_STATUS_VALUES:
        return _is_positive(volume) and _is_positive(amount)

    # Unknown positive-like provider values should still require actual traded volume.
    return _is_positive(volume) and _is_positive(amount)
