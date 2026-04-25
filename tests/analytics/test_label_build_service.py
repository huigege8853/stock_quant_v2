from decimal import Decimal

from stock_quant_v2.analytics_domain.calculators.labels_forward_return import (
    calc_binary_down_label,
    calc_binary_up_label,
    calc_forward_return,
)


def test_calc_forward_return():
    result = calc_forward_return(Decimal("10"), Decimal("11"))
    assert result == Decimal("0.1")


def test_calc_binary_up_label():
    assert calc_binary_up_label(Decimal("0.05"), Decimal("0.03")) == "1"
    assert calc_binary_up_label(Decimal("0.01"), Decimal("0.03")) == "0"


def test_calc_binary_down_label():
    assert calc_binary_down_label(Decimal("-0.05"), Decimal("-0.03")) == "1"
    assert calc_binary_down_label(Decimal("-0.01"), Decimal("-0.03")) == "0"