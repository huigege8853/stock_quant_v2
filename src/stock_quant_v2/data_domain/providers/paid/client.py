from __future__ import annotations

from datetime import date
from typing import Any


class PaidClient:
    def __init__(self, api_client: Any = None) -> None:
        self.api_client = api_client

    def fetch_daily_bar_by_symbol(
        self,
        exchange_code: str,
        ticker: str,
        trade_date: date,
    ) -> list[dict[str, Any]]:
        _ = exchange_code, ticker, trade_date
        return []

    def fetch_market_index_bar_by_symbol(
        self,
        index_code: str,
        trade_date: date,
    ) -> list[dict[str, Any]]:
        _ = index_code, trade_date
        return []