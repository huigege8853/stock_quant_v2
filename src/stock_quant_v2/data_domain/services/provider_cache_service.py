from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class ProviderCacheService:
    tushare_daily_bar_cache: dict[date, list[Any]] = field(default_factory=dict)
    tushare_daily_bar_error_cache: dict[date, str] = field(default_factory=dict)

    def get_tushare_daily_bar(self, trade_date: date) -> list[Any] | None:
        return self.tushare_daily_bar_cache.get(trade_date)

    def set_tushare_daily_bar(self, trade_date: date, rows: list[Any]) -> None:
        self.tushare_daily_bar_cache[trade_date] = rows

    def get_tushare_daily_bar_error(self, trade_date: date) -> str | None:
        return self.tushare_daily_bar_error_cache.get(trade_date)

    def set_tushare_daily_bar_error(self, trade_date: date, error: str) -> None:
        self.tushare_daily_bar_error_cache[trade_date] = error