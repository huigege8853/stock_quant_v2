from __future__ import annotations

from datetime import date
from decimal import Decimal

from stock_quant_v2.data_domain.tasks.sync_price_limit_daily import (
    _calc_limits,
    _infer_limit_pct,
    _is_no_limit_window,
    _round_price,
)


def test_round_price_keeps_four_decimals() -> None:
    assert _round_price(Decimal("7.28204")) == Decimal("7.2820")
    assert _round_price(Decimal("7.28205")) == Decimal("7.2821")


def test_infer_limit_pct_main_board() -> None:
    assert _infer_limit_pct("SSE", "600000") == Decimal("0.10")
    assert _infer_limit_pct("SZSE", "000001") == Decimal("0.10")


def test_infer_limit_pct_star_market() -> None:
    assert _infer_limit_pct("SSE", "688001") == Decimal("0.20")


def test_infer_limit_pct_chinext() -> None:
    assert _infer_limit_pct("SZSE", "300001") == Decimal("0.20")
    assert _infer_limit_pct("SZSE", "301001") == Decimal("0.20")


def test_infer_limit_pct_bse() -> None:
    assert _infer_limit_pct("BSE", "430001") == Decimal("0.30")


def test_is_no_limit_window_false_when_no_list_date() -> None:
    result = _is_no_limit_window(
        exchange_code="SSE",
        ticker="688001",
        trade_date=date(2024, 1, 2),
        list_date=None,
    )
    assert result is False


def test_is_no_limit_window_true_for_star_market_first_days() -> None:
    result = _is_no_limit_window(
        exchange_code="SSE",
        ticker="688001",
        trade_date=date(2024, 1, 5),
        list_date=date(2024, 1, 2),
    )
    assert result is True


def test_is_no_limit_window_true_for_chinext_first_days() -> None:
    result = _is_no_limit_window(
        exchange_code="SZSE",
        ticker="300001",
        trade_date=date(2024, 1, 8),
        list_date=date(2024, 1, 2),
    )
    assert result is True


def test_is_no_limit_window_false_after_first_days() -> None:
    result = _is_no_limit_window(
        exchange_code="SSE",
        ticker="688001",
        trade_date=date(2024, 1, 10),
        list_date=date(2024, 1, 2),
    )
    assert result is False


def test_is_no_limit_window_false_for_main_board() -> None:
    result = _is_no_limit_window(
        exchange_code="SSE",
        ticker="600000",
        trade_date=date(2024, 1, 3),
        list_date=date(2024, 1, 2),
    )
    assert result is False


def test_calc_limits_main_board() -> None:
    up_limit, down_limit = _calc_limits(
        pre_close=Decimal("6.6200"),
        limit_pct=Decimal("0.10"),
    )

    assert up_limit == Decimal("7.2820")
    assert down_limit == Decimal("5.9580")


def test_calc_limits_twenty_percent_board() -> None:
    up_limit, down_limit = _calc_limits(
        pre_close=Decimal("10.0000"),
        limit_pct=Decimal("0.20"),
    )

    assert up_limit == Decimal("12.0000")
    assert down_limit == Decimal("8.0000")


def test_calc_limits_thirty_percent_board() -> None:
    up_limit, down_limit = _calc_limits(
        pre_close=Decimal("10.0000"),
        limit_pct=Decimal("0.30"),
    )

    assert up_limit == Decimal("13.0000")
    assert down_limit == Decimal("7.0000")