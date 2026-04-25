from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(slots=True)
class ExpectedTradeDatePlan:
    expected_trade_dates: list[date]
    metadata_issue_code: str | None = None
    metadata_issue_detail: dict | None = None


def build_expected_trade_date_plan(
    *,
    exchange_trade_dates: list[date],
    start_date: date,
    end_date: date,
    list_date: date | None,
    delist_date: date | None,
) -> ExpectedTradeDatePlan:
    """
    严格模式规则：
    1. list_date 缺失时，不生成 expected_trade_dates，避免把整段都误判为停牌/缺失
    2. list_date / delist_date 完整时，才按生命周期裁剪 expected_trade_dates
    """
    if list_date is None:
        return ExpectedTradeDatePlan(
            expected_trade_dates=[],
            metadata_issue_code="METADATA_LIST_DATE_MISSING",
            metadata_issue_detail={
                "reason": "meta_instrument.list_date_is_null",
                "strict_mode_action": "skip_expected_trade_date_generation",
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        )

    effective_start = max(start_date, list_date)
    effective_end = min(end_date, delist_date) if delist_date else end_date

    if effective_start > effective_end:
        return ExpectedTradeDatePlan(expected_trade_dates=[])

    return ExpectedTradeDatePlan(
        expected_trade_dates=[
            trade_date
            for trade_date in exchange_trade_dates
            if effective_start <= trade_date <= effective_end
        ]
    )


def classify_missing_daily_bar_issue(
    *,
    expected_trade_date: date,
) -> str:
    _ = expected_trade_date
    return "SUSPENDED_OR_NO_BAR"


def classify_missing_adjust_factor_issue(
    *,
    expected_trade_date: date,
) -> str:
    _ = expected_trade_date
    return "PROVIDER_MISSING_ADJUST_FACTOR"