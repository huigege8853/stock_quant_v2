from __future__ import annotations

from stock_quant_v2.data_domain.provider_priority import (
    ADJUST_FACTOR_PROVIDER_PRIORITY,
    DAILY_BAR_PROVIDER_PRIORITY,
    build_disabled_provider_set,
    get_enabled_provider_priority,
    get_provider_priority,
    should_disable_tushare,
)


def test_get_provider_priority_daily_bar() -> None:
    result = get_provider_priority("daily_bar")
    assert result == list(DAILY_BAR_PROVIDER_PRIORITY)


def test_get_provider_priority_adjust_factor() -> None:
    result = get_provider_priority("adjust_factor")
    assert result == list(ADJUST_FACTOR_PROVIDER_PRIORITY)


def test_get_provider_priority_normalizes_dataset_code() -> None:
    result = get_provider_priority("  DAILY_BAR  ")
    assert result == list(DAILY_BAR_PROVIDER_PRIORITY)


def test_get_provider_priority_falls_back_to_default() -> None:
    result = get_provider_priority("unknown_dataset")
    assert "baostock" in result
    assert "skip" in result


def test_get_enabled_provider_priority_filters_disabled_provider() -> None:
    result = get_enabled_provider_priority(
        "daily_bar",
        disabled_providers={"tushare"},
    )
    assert "tushare" not in result
    assert "baostock" in result
    assert "sina" in result


def test_get_enabled_provider_priority_normalizes_disabled_provider() -> None:
    result = get_enabled_provider_priority(
        "daily_bar",
        disabled_providers={"  TUSHARE  "},
    )
    assert "tushare" not in result


def test_should_disable_tushare_when_no_token() -> None:
    assert should_disable_tushare(has_token=False, has_permission=True) is True


def test_should_disable_tushare_when_no_permission() -> None:
    assert should_disable_tushare(has_token=True, has_permission=False) is True


def test_should_disable_tushare_when_token_and_permission_ok() -> None:
    assert should_disable_tushare(has_token=True, has_permission=True) is False


def test_build_disabled_provider_set_with_tushare_disabled() -> None:
    result = build_disabled_provider_set(tushare_enabled=False)
    assert "tushare" in result


def test_build_disabled_provider_set_with_tushare_enabled() -> None:
    result = build_disabled_provider_set(tushare_enabled=True)
    assert "tushare" not in result


def test_build_disabled_provider_set_merges_extra_disabled() -> None:
    result = build_disabled_provider_set(
        tushare_enabled=False,
        extra_disabled={" paid ", "SINA"},
    )
    assert result == {"tushare", "paid", "sina"}