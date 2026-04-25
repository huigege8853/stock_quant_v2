from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from stock_quant_v2.data_domain.constants import DEFAULT_MARKET_CODE
from stock_quant_v2.data_domain.dto.daily_bar import DailyBarDTO
from stock_quant_v2.data_domain.providers.base import BaseProvider


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


class BaoStockDailyBarProvider(
    BaseProvider[dict, DailyBarDTO]
):
    provider_name = "baostock"
    dataset_code = "daily_bar"

    def __init__(self, client) -> None:
        self.client = client

    def fetch(self, request: dict) -> Iterable[DailyBarDTO]:
        exchange_code = request["exchange_code"]
        ticker = request["ticker"]
        trade_date = request["trade_date"]
        adjust_type = request.get("adjust_type", "RAW")

        rows = self.client.fetch_daily_bar_by_symbol(
            exchange_code=exchange_code,
            ticker=ticker,
            trade_date=trade_date,
        )

        for row in rows:
            yield DailyBarDTO(
                provider_name=self.provider_name,
                market_code=DEFAULT_MARKET_CODE,
                exchange_code=exchange_code,
                ticker=ticker,
                vendor_symbol=None,
                trade_date=trade_date,
                price_adjust_type=adjust_type,
                open=_to_decimal(row.get("open")),
                high=_to_decimal(row.get("high")),
                low=_to_decimal(row.get("low")),
                close=_to_decimal(row.get("close")),
                pre_close=_to_decimal(row.get("pre_close")),
                volume=_to_decimal(row.get("volume")),
                turnover=_to_decimal(row.get("turnover")),
                amplitude=_to_decimal(row.get("amplitude")),
                pct_change=_to_decimal(row.get("pct_change")),
                price_change=_to_decimal(row.get("price_change")),
                turnover_rate=_to_decimal(row.get("turnover_rate")),
                suspended_flag=bool(row.get("suspended_flag", False)),
                provider_record_key=f"{ticker}:{trade_date.isoformat()}:{adjust_type}",
                raw_payload=row,
            )