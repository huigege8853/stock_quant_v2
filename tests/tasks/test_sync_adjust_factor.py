from __future__ import annotations

from datetime import date
from decimal import Decimal

from stock_quant_v2.data_domain.dto.adjust_factor import AdjustFactorDTO
from stock_quant_v2.data_domain.tasks.sync_adjust_factor import (
    _normalize_adjust_factor_row,
)


def test_normalize_adjust_factor_row_reads_adjust_factor_field() -> None:
    dto = _normalize_adjust_factor_row(
        provider_name="baostock",
        exchange_code="SSE",
        ticker="600000",
        trade_date=date(2024, 1, 2),
        row={
            "vendor_symbol": "sh.600000",
            "adjust_factor": "11.949786",
        },
    )

    assert isinstance(dto, AdjustFactorDTO)
    assert dto.provider_name == "baostock"
    assert dto.market_code == "CN"
    assert dto.exchange_code == "SSE"
    assert dto.ticker == "600000"
    assert dto.vendor_symbol == "sh.600000"
    assert dto.trade_date == date(2024, 1, 2)
    assert dto.adjust_factor == Decimal("11.949786")
    assert dto.provider_record_key == "baostock:SSE:600000:2024-01-02"


def test_normalize_adjust_factor_row_reads_adj_factor_fallback_field() -> None:
    dto = _normalize_adjust_factor_row(
        provider_name="akshare",
        exchange_code="SZSE",
        ticker="000001",
        trade_date=date(2024, 1, 2),
        row={
            "vendor_symbol": "sz.000001",
            "adj_factor": 2.5,
        },
    )

    assert dto.adjust_factor == Decimal("2.5")
    assert dto.provider_record_key == "akshare:SZSE:000001:2024-01-02"


def test_normalize_adjust_factor_row_respects_existing_provider_record_key() -> None:
    dto = _normalize_adjust_factor_row(
        provider_name="baostock",
        exchange_code="SSE",
        ticker="600010",
        trade_date=date(2024, 1, 2),
        row={
            "vendor_symbol": "sh.600010",
            "adjust_factor": "7.241088",
            "provider_record_key": "custom-key-001",
        },
    )

    assert dto.adjust_factor == Decimal("7.241088")
    assert dto.provider_record_key == "custom-key-001"


def test_normalize_adjust_factor_row_allows_missing_adjust_factor() -> None:
    dto = _normalize_adjust_factor_row(
        provider_name="baostock",
        exchange_code="SSE",
        ticker="600015",
        trade_date=date(2024, 1, 2),
        row={
            "vendor_symbol": "sh.600015",
        },
    )

    assert dto.adjust_factor is None
    assert dto.provider_record_key == "baostock:SSE:600015:2024-01-02"


def test_normalize_adjust_factor_row_keeps_raw_payload() -> None:
    row = {
        "vendor_symbol": "sh.600006",
        "adjust_factor": "2.828427",
        "source": "test",
    }

    dto = _normalize_adjust_factor_row(
        provider_name="baostock",
        exchange_code="SSE",
        ticker="600006",
        trade_date=date(2024, 1, 2),
        row=row,
    )

    assert dto.raw_payload == row