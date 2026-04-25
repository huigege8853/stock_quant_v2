from __future__ import annotations

from datetime import date, timedelta


class LeakageGuardService:
    @staticmethod
    def assert_eod_indicator_publish_lag(trade_date: date, available_date: date, publish_lag_days: int = 1) -> None:
        expected_min = trade_date + timedelta(days=publish_lag_days)
        if available_date < expected_min:
            raise ValueError(
                f"available_date={available_date} violates publish_lag_days={publish_lag_days} for trade_date={trade_date}"
            )