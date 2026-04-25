from datetime import date
from decimal import Decimal

from stock_quant_v2.analytics_domain.calculators.primitive_metrics import calc_adj_close, calc_return
from stock_quant_v2.analytics_domain.calculators.indicators_trend import calc_simple_moving_average
from stock_quant_v2.analytics_domain.calculators.indicators_tradability import calc_tradable_flag


def test_calc_adj_close():
    assert calc_adj_close(10, 2) == Decimal("20")


def test_calc_return():
    assert calc_return(120, 100) == Decimal("0.2")


def test_calc_simple_moving_average():
    result = calc_simple_moving_average([10, 20, 30, 40])
    assert result == Decimal("25")


def test_calc_tradable_flag_false_when_suspended():
    assert calc_tradable_flag(
        trading_status="SUSPENDED",
        is_suspended=True,
        close_price=Decimal("10"),
        up_limit_price=Decimal("11"),
    ) is False


def test_calc_tradable_flag_false_when_close_hits_up_limit():
    assert calc_tradable_flag(
        trading_status="TRADING",
        is_suspended=False,
        close_price=Decimal("11"),
        up_limit_price=Decimal("11"),
    ) is False


def test_calc_tradable_flag_true_when_normal_trading():
    assert calc_tradable_flag(
        trading_status="TRADING",
        is_suspended=False,
        close_price=Decimal("10.5"),
        up_limit_price=Decimal("11"),
    ) is True