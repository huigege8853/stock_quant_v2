from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable


@dataclass(slots=True)
class QualityResult:
    passed: bool
    issue_code: str | None = None
    severity: str | None = None
    detail: dict | None = None


class QualityService:
    def validate_daily_bar_row(self, row: dict) -> list[QualityResult]:
        issues: list[QualityResult] = []

        required_fields = ("open", "high", "low", "close", "trade_date", "ticker", "exchange_code")
        for field in required_fields:
            if row.get(field) is None:
                issues.append(
                    QualityResult(
                        passed=False,
                        issue_code="REQUIRED_FIELD_NOT_NULL",
                        severity="ERROR",
                        detail={"field": field},
                    )
                )

        high = row.get("high")
        low = row.get("low")
        open_ = row.get("open")
        close = row.get("close")

        if None not in (high, low, open_, close):
            if high < max(open_, close, low):
                issues.append(
                    QualityResult(
                        passed=False,
                        issue_code="INVALID_HIGH_PRICE",
                        severity="ERROR",
                        detail=row,
                    )
                )
            if low > min(open_, close, high):
                issues.append(
                    QualityResult(
                        passed=False,
                        issue_code="INVALID_LOW_PRICE",
                        severity="ERROR",
                        detail=row,
                    )
                )

        volume = row.get("volume")
        turnover = row.get("turnover")
        if volume is not None and volume < 0:
            issues.append(QualityResult(False, "NEGATIVE_VOLUME", "ERROR", {"volume": str(volume)}))
        if turnover is not None and turnover < 0:
            issues.append(QualityResult(False, "NEGATIVE_TURNOVER", "ERROR", {"turnover": str(turnover)}))

        suspended_flag = row.get("suspended_flag")
        if suspended_flag is True and volume not in (None, 0):
            issues.append(
                QualityResult(
                    False,
                    "SUSPENDED_WITH_NONZERO_VOLUME",
                    "WARN",
                    {"volume": str(volume)},
                )
            )

        return issues

    def validate_trade_date_is_open_day(
        self,
        row: dict,
        is_open_day_lookup: Callable[[str, date], bool | None],
    ) -> list[QualityResult]:
        issues: list[QualityResult] = []
        exchange_code = row.get("exchange_code")
        trade_date = row.get("trade_date")

        if exchange_code is None or trade_date is None:
            return issues

        is_open = is_open_day_lookup(exchange_code, trade_date)
        if is_open is False:
            issues.append(
                QualityResult(
                    passed=False,
                    issue_code="TRADE_DATE_NOT_OPEN_DAY",
                    severity="ERROR",
                    detail={
                        "exchange_code": exchange_code,
                        "trade_date": str(trade_date),
                    },
                )
            )
        elif is_open is None:
            issues.append(
                QualityResult(
                    passed=False,
                    issue_code="TRADING_CALENDAR_NOT_FOUND",
                    severity="WARN",
                    detail={
                        "exchange_code": exchange_code,
                        "trade_date": str(trade_date),
                    },
                )
            )
        return issues

    def validate_trade_date_within_instrument_lifecycle(
        self,
        row: dict,
        instrument_lifecycle_lookup: Callable[[str, str, str], tuple[date | None, date | None] | None],
    ) -> list[QualityResult]:
        issues: list[QualityResult] = []

        market_code = row.get("market_code")
        exchange_code = row.get("exchange_code")
        ticker = row.get("ticker")
        trade_date = row.get("trade_date")

        if None in (market_code, exchange_code, ticker, trade_date):
            return issues

        lifecycle = instrument_lifecycle_lookup(market_code, exchange_code, ticker)
        if lifecycle is None:
            issues.append(
                QualityResult(
                    passed=False,
                    issue_code="INSTRUMENT_LIFECYCLE_NOT_FOUND",
                    severity="WARN",
                    detail={
                        "market_code": market_code,
                        "exchange_code": exchange_code,
                        "ticker": ticker,
                    },
                )
            )
            return issues

        list_date, delist_date = lifecycle

        if list_date is not None and trade_date < list_date:
            issues.append(
                QualityResult(
                    passed=False,
                    issue_code="TRADE_DATE_BEFORE_LIST_DATE",
                    severity="ERROR",
                    detail={
                        "trade_date": str(trade_date),
                        "list_date": str(list_date),
                    },
                )
            )

        if delist_date is not None and trade_date > delist_date:
            issues.append(
                QualityResult(
                    passed=False,
                    issue_code="TRADE_DATE_AFTER_DELIST_DATE",
                    severity="ERROR",
                    detail={
                        "trade_date": str(trade_date),
                        "delist_date": str(delist_date),
                    },
                )
            )

        return issues

    def validate_market_index_bar_row(self, row: dict) -> list[QualityResult]:
        issues: list[QualityResult] = []

        required_fields = ("close", "trade_date", "index_code", "exchange_code")
        for field in required_fields:
            if row.get(field) is None:
                issues.append(
                    QualityResult(
                        passed=False,
                        issue_code="REQUIRED_FIELD_NOT_NULL",
                        severity="ERROR",
                        detail={"field": field},
                    )
                )

        high = row.get("high")
        low = row.get("low")
        open_ = row.get("open")
        close = row.get("close")

        if None not in (high, low, open_, close):
            if high < max(open_, close, low):
                issues.append(QualityResult(False, "INVALID_HIGH_PRICE", "ERROR", row))
            if low > min(open_, close, high):
                issues.append(QualityResult(False, "INVALID_LOW_PRICE", "ERROR", row))

        volume = row.get("volume")
        turnover = row.get("turnover")
        if volume is not None and volume < 0:
            issues.append(QualityResult(False, "NEGATIVE_VOLUME", "ERROR", {"volume": str(volume)}))
        if turnover is not None and turnover < 0:
            issues.append(QualityResult(False, "NEGATIVE_TURNOVER", "ERROR", {"turnover": str(turnover)}))

        return issues