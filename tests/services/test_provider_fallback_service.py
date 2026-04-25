from __future__ import annotations

from stock_quant_v2.data_domain.services.provider_fallback_service import (
    ProviderFallbackService,
)


def test_try_providers_returns_first_success() -> None:
    service = ProviderFallbackService()

    result = service.try_providers(
        [
            ("baostock", lambda: []),
            ("sina", lambda: [{"ticker": "600000"}]),
            ("akshare", lambda: [{"ticker": "000001"}]),
        ]
    )

    assert result.success is True
    assert result.provider_name == "sina"
    assert result.data == [{"ticker": "600000"}]
    assert len(result.attempts) == 2
    assert result.attempts[0].provider_name == "baostock"
    assert result.attempts[0].success is False
    assert result.attempts[0].error == "empty rows"
    assert result.attempts[1].provider_name == "sina"
    assert result.attempts[1].success is True
    assert result.attempts[1].row_count == 1


def test_try_providers_returns_failure_when_all_empty() -> None:
    service = ProviderFallbackService()

    result = service.try_providers(
        [
            ("baostock", lambda: []),
            ("sina", lambda: []),
        ]
    )

    assert result.success is False
    assert result.provider_name is None
    assert result.data is None
    assert result.error == "sina returned empty rows"
    assert len(result.attempts) == 2
    assert all(item.success is False for item in result.attempts)


def test_try_providers_returns_failure_when_all_raise() -> None:
    service = ProviderFallbackService()

    def _raise_one():
        raise ValueError("boom-1")

    def _raise_two():
        raise RuntimeError("boom-2")

    result = service.try_providers(
        [
            ("baostock", _raise_one),
            ("sina", _raise_two),
        ]
    )

    assert result.success is False
    assert result.provider_name is None
    assert result.data is None
    assert result.error == "sina: boom-2"
    assert len(result.attempts) == 2
    assert result.attempts[0].error == "boom-1"
    assert result.attempts[1].error == "boom-2"


def test_try_providers_skips_disabled_provider_without_executing() -> None:
    service = ProviderFallbackService()
    executed = {"tushare": False}

    def _tushare_fetch():
        executed["tushare"] = True
        return [{"ticker": "000001"}]

    result = service.try_providers(
        providers=[
            ("tushare", _tushare_fetch),
            ("akshare", lambda: [{"ticker": "600000"}]),
        ],
        skipped_providers={"tushare": "disabled_by_config"},
    )

    assert executed["tushare"] is False
    assert result.success is True
    assert result.provider_name == "akshare"
    assert result.data == [{"ticker": "600000"}]
    assert len(result.attempts) == 2

    skipped_attempt = result.attempts[0]
    assert skipped_attempt.provider_name == "tushare"
    assert skipped_attempt.success is False
    assert skipped_attempt.skipped is True
    assert skipped_attempt.skipped_reason == "disabled_by_config"

    success_attempt = result.attempts[1]
    assert success_attempt.provider_name == "akshare"
    assert success_attempt.success is True
    assert success_attempt.skipped is False


def test_try_providers_skipped_provider_name_is_case_insensitive() -> None:
    service = ProviderFallbackService()
    executed = {"tushare": False}

    def _tushare_fetch():
        executed["tushare"] = True
        return [{"ticker": "000001"}]

    result = service.try_providers(
        providers=[
            ("tushare", _tushare_fetch),
            ("akshare", lambda: []),
        ],
        skipped_providers={"TUSHARE": "disabled_by_config"},
    )

    assert executed["tushare"] is False
    assert result.success is False
    assert result.provider_name is None
    assert len(result.attempts) == 2
    assert result.attempts[0].skipped is True
    assert result.attempts[0].skipped_reason == "disabled_by_config"


def test_try_providers_returns_no_provider_configured_when_empty() -> None:
    service = ProviderFallbackService()

    result = service.try_providers([])

    assert result.success is False
    assert result.provider_name is None
    assert result.data is None
    assert result.error == "no providers configured"
    assert result.attempts == []