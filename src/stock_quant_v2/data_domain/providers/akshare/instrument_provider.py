from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from stock_quant_v2.data_domain.mappers.instrument_mapper import normalize_instrument_row
from stock_quant_v2.data_domain.providers.base import BaseProvider


class AkshareInstrumentProvider(BaseProvider[dict, dict]):
    provider_name = "akshare"
    dataset_code = "instrument"

    def __init__(self, client) -> None:
        self.client = client

    def fetch(self, request: dict | None = None) -> Iterable[dict]:
        rows: list[dict[str, Any]] = self.client.fetch_instruments()

        for row in rows:
            try:
                normalized = normalize_instrument_row(
                    {
                        "market_code": row.get("market_code", "CN_A"),
                        "exchange_code": row.get("exchange_code"),
                        "ticker": row.get("ticker") or row.get("symbol") or row.get("code"),
                        "name": row.get("name"),
                        "instrument_type": row.get("instrument_type", "EQUITY"),
                        "instrument_code": row.get("instrument_code"),
                        "currency": row.get("currency", "CNY"),
                        "list_date": row.get("list_date") or row.get("ipo_date"),
                        "delist_date": row.get("delist_date"),
                        "is_active": row.get("is_active"),
                    }
                )
            except ValueError:
                # 当前阶段只稳股票，非股票资产先跳过
                continue

            yield normalized