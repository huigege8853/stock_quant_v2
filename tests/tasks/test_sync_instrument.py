from __future__ import annotations

from stock_quant_v2.data_domain.tasks.sync_instrument import (
    _build_skipped_providers,
    _normalize_instrument_row,
)


def test_normalize_instrument_row_uses_display_name_first() -> None:
    row = {
        "market_code": "CN_A",
        "exchange_code": "sse",
        "ticker": "600000",
        "display_name": "浦发银行",
        "name": "不应被优先使用",
        "instrument_type": "stock",
        "currency": "CNY",
        "list_date": None,
        "delist_date": None,
        "is_active": True,
    }

    normalized = _normalize_instrument_row(row, provider_name="akshare")

    assert normalized["market_code"] == "CN_A"
    assert normalized["exchange_code"] == "SSE"
    assert normalized["ticker"] == "600000"
    assert normalized["instrument_code"] == "600000.SSE"
    assert normalized["display_name"] == "浦发银行"
    assert normalized["instrument_type"] is not None
    assert normalized["currency"] == "CNY"
    assert normalized["is_active"] is True
    assert normalized["provider_name"] == "akshare"


def test_normalize_instrument_row_falls_back_to_name() -> None:
    row = {
        "exchange_code": "szse",
        "ticker": "000001",
        "name": "平安银行",
        "instrument_type": "stock",
    }

    normalized = _normalize_instrument_row(row, provider_name="tushare")

    assert normalized["market_code"] == "CN_A"
    assert normalized["exchange_code"] == "SZSE"
    assert normalized["ticker"] == "000001"
    assert normalized["instrument_code"] == "000001.SZSE"
    assert normalized["display_name"] == "平安银行"
    assert normalized["currency"] == "CNY"
    assert normalized["provider_name"] == "tushare"


def test_normalize_instrument_row_uses_default_values() -> None:
    row = {
        "exchange_code": "bse",
        "ticker": "430001",
    }

    normalized = _normalize_instrument_row(row, provider_name="akshare")

    assert normalized["market_code"] == "CN_A"
    assert normalized["exchange_code"] == "BSE"
    assert normalized["ticker"] == "430001"
    assert normalized["instrument_code"] == "430001.BSE"
    assert normalized["display_name"] == ""
    assert normalized["currency"] == "CNY"
    assert normalized["is_active"] is True
    assert normalized["provider_name"] == "akshare"


def test_normalize_instrument_row_does_not_return_name_field() -> None:
    row = {
        "exchange_code": "szse",
        "ticker": "920001",
        "name": "某北交所映射股票",
    }

    normalized = _normalize_instrument_row(row, provider_name="akshare")

    assert "name" not in normalized
    assert normalized["display_name"] == "某北交所映射股票"


def test_build_skipped_providers_returns_tushare_when_disabled(monkeypatch) -> None:
    from stock_quant_v2.data_domain.tasks import sync_instrument as module

    monkeypatch.setattr(module.settings, "tushare_enabled", False)

    skipped = _build_skipped_providers()

    assert skipped == {"tushare": "disabled_by_config"}


def test_build_skipped_providers_returns_empty_when_tushare_enabled(monkeypatch) -> None:
    from stock_quant_v2.data_domain.tasks import sync_instrument as module

    monkeypatch.setattr(module.settings, "tushare_enabled", True)

    skipped = _build_skipped_providers()

    assert skipped == {}