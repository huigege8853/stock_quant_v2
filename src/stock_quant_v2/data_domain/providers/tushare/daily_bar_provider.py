from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from stock_quant_v2.data_domain.constants import DEFAULT_MARKET_CODE
from stock_quant_v2.data_domain.dto.daily_bar import DailyBarDTO
from stock_quant_v2.data_domain.providers.base import BaseProvider
from stock_quant_v2.data_domain.providers.request_models import DailyBarRequest


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


class TushareDailyBarProvider(BaseProvider[DailyBarRequest, DailyBarDTO]):
    provider_name = "tushare"
    dataset_code = "daily_bar"

    def __init__(self, client) -> None:
        self.client = client

    def fetch(self, request: DailyBarRequest) -> Iterable[DailyBarDTO]:
        rows = self.client.fetch_daily_bar(trade_date=request.trade_date)

        for row in rows:
            ticker = str(row["ticker"])
            exchange_code = str(row["exchange_code"])
            vendor_symbol = row.get("ts_code")

            yield DailyBarDTO(
                provider_name=self.provider_name,
                market_code=DEFAULT_MARKET_CODE,
                exchange_code=exchange_code,
                ticker=ticker,
                vendor_symbol=vendor_symbol,
                trade_date=request.trade_date,
                price_adjust_type=request.adjust_type,
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
                provider_record_key=f"{ticker}:{request.trade_date.isoformat()}:{request.adjust_type}",
                raw_payload=row,
            )