from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from stock_quant_v2.data_domain.providers.base import BaseProvider


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


class PaidMarketIndexBarProvider(BaseProvider[dict, dict]):
    provider_name = "paid"
    dataset_code = "market_index_bar"

    def __init__(self, client) -> None:
        self.client = client

    def fetch(self, request: dict) -> Iterable[dict]:
        index_code = request["index_code"]
        trade_date = request["trade_date"]

        rows = self.client.fetch_market_index_bar_by_symbol(
            index_code=index_code,
            trade_date=trade_date,
        )

        for row in rows:
            yield {
                "provider_name": self.provider_name,
                "dataset_code": self.dataset_code,
                "index_code": index_code,
                "trade_date": trade_date,
                "exchange_code": row.get("exchange_code"),
                "index_name": row.get("index_name"),
                "index_type": row.get("index_type"),
                "open": _to_decimal(row.get("open")),
                "high": _to_decimal(row.get("high")),
                "low": _to_decimal(row.get("low")),
                "close": _to_decimal(row.get("close")),
                "volume": _to_decimal(row.get("volume")),
                "turnover": _to_decimal(row.get("turnover")),
                "provider_record_key": f"{index_code}:{trade_date.isoformat()}",
                "raw_payload": row,
            }