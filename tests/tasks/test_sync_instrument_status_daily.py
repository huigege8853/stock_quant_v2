from __future__ import annotations

from stock_quant_v2.data_domain.tasks.sync_instrument_status_daily import (
    _derive_trading_status,
)


def test_derive_trading_status_trading() -> None:
    result = _derive_trading_status(
        has_bar=True,
        is_suspended=False,
    )
    assert result == "TRADING"


def test_derive_trading_status_suspended() -> None:
    result = _derive_trading_status(
        has_bar=True,
        is_suspended=True,
    )
    assert result == "SUSPENDED"


def test_derive_trading_status_no_bar_when_has_bar_false() -> None:
    result = _derive_trading_status(
        has_bar=False,
        is_suspended=None,
    )
    assert result == "NO_BAR"


def test_derive_trading_status_no_bar_even_if_suspended_unknown() -> None:
    result = _derive_trading_status(
        has_bar=False,
        is_suspended=False,
    )
    assert result == "NO_BAR"