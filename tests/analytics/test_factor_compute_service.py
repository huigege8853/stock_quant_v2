from decimal import Decimal

from stock_quant_v2.analytics_domain.calculators.factors_momentum import calc_mom_20, calc_trend_strength
from stock_quant_v2.analytics_domain.calculators.factors_tradability import calc_tradability_score
from stock_quant_v2.analytics_domain.services.factor_compute_service import FactorComputeService


def test_calc_mom_20():
    assert calc_mom_20(Decimal("0.15")) == Decimal("0.15")


def test_calc_trend_strength():
    result = calc_trend_strength(adj_close=Decimal("11"), ma_20=Decimal("10"))
    assert result == Decimal("0.1")


def test_calc_tradability_score_true():
    assert calc_tradability_score(Decimal("1")) == Decimal("1")


def test_calc_tradability_score_false():
    assert calc_tradability_score(Decimal("0")) == Decimal("0")


def test_calc_percent_rank():
    values = {
        1: Decimal("1.0"),
        2: Decimal("2.0"),
        3: Decimal("3.0"),
    }
    result = FactorComputeService._calc_percent_rank(values)
    assert result[1] == Decimal("0.0")
    assert result[2] == Decimal("0.5")
    assert result[3] == Decimal("1.0")


def test_calc_quintile_bucket():
    rank_map = {
        1: Decimal("0.0"),
        2: Decimal("0.3"),
        3: Decimal("0.6"),
        4: Decimal("1.0"),
    }
    result = FactorComputeService._calc_quintile_bucket(rank_map)
    assert result[1] == "Q1"
    assert result[2] == "Q2"
    assert result[3] == "Q4"
    assert result[4] == "Q5"