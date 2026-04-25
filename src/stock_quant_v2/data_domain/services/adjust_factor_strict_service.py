from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
import io
from contextlib import redirect_stderr, redirect_stdout


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _to_decimal(value: Any) -> Decimal | None:
    if value in (None, "", "null", "-", "--"):
        return None
    return Decimal(str(value))


def _to_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def baostock_code(exchange_code: str, ticker: str) -> str:
    if exchange_code == "SSE":
        return f"sh.{ticker}"
    if exchange_code == "SZSE":
        return f"sz.{ticker}"
    if exchange_code == "BSE":
        return f"bj.{ticker}"
    return ticker


@dataclass
class AdjustFactorEvent:
    exchange_code: str
    ticker: str
    event_date: date
    vendor_symbol: str
    forward_factor: Decimal | None
    backward_factor: Decimal | None
    adjust_factor: Decimal | None
    raw_payload: dict


@dataclass
class DailyExpandedAdjustFactor:
    trade_date: date
    forward_factor: Decimal
    backward_factor: Decimal


def query_adjust_factor_events(
    api_client,
    *,
    exchange_code: str,
    ticker: str,
    start_date: date,
    end_date: date,
) -> list[AdjustFactorEvent]:
    if api_client is None:
        return []

    bs_code = baostock_code(exchange_code, ticker)

    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        rs = api_client.query_adjust_factor(
            code=bs_code,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
        )


    error_code = getattr(rs, "error_code", "0")
    error_msg = getattr(rs, "error_msg", None)
    if error_code != "0":
        raise RuntimeError(
            f"baostock query_adjust_factor failed: code={bs_code}, "
            f"error_code={error_code}, error_msg={error_msg}"
        )

    fields = list(getattr(rs, "fields", []) or [])
    rows: list[AdjustFactorEvent] = []

    while rs.next():
        row_data = rs.get_row_data()
        row = dict(zip(fields, row_data))

        event_date = _to_date(row.get("dividOperateDate"))
        if event_date is None:
            continue

        rows.append(
            AdjustFactorEvent(
                exchange_code=exchange_code,
                ticker=ticker,
                event_date=event_date,
                vendor_symbol=row.get("code") or bs_code,
                forward_factor=_to_decimal(row.get("foreAdjustFactor")),
                backward_factor=_to_decimal(row.get("backAdjustFactor")),
                adjust_factor=_to_decimal(row.get("adjustFactor")),
                raw_payload=row,
            )
        )

    rows.sort(key=lambda x: x.event_date)
    return rows


def _resolve_effective_trade_date(
    expected_trade_dates: list[date],
    *,
    event_date: date,
    effective_offset_trade_days: int,
) -> date | None:
    """
    BaoStock 的 adjust factor 是事件点，不是日频表。
    这里把事件点映射到目标日频交易日上。

    默认 effective_offset_trade_days=1：
    - 事件日之后的第一个“目标交易日”开始生效

    如果你后续用样本核对后确认应该 event 当天生效，把它改成 0 即可。
    """
    if not expected_trade_dates:
        return None

    sorted_dates = sorted(expected_trade_dates)

    if effective_offset_trade_days <= 0:
        for d in sorted_dates:
            if d >= event_date:
                return d
        return None

    # 默认：事件后第一个目标交易日生效
    after_dates = [d for d in sorted_dates if d > event_date]
    if not after_dates:
        return None

    idx = effective_offset_trade_days - 1
    if idx >= len(after_dates):
        return None
    return after_dates[idx]


def expand_events_to_daily_factors(
    *,
    events: list[AdjustFactorEvent],
    expected_trade_dates: list[date],
    effective_offset_trade_days: int = 1,
    default_forward_factor: Decimal = Decimal("1"),
    default_backward_factor: Decimal = Decimal("1"),
) -> list[DailyExpandedAdjustFactor]:
    """
    严格模式下，core_adjust_factor 需要日频因子。
    BaoStock 返回的是事件点，所以这里做展开。

    当前实现约定：
    - 第一条事件生效前，因子默认为 1
    - 事件生效后，使用最近一次事件的 fore/back factor 向后持有
    """
    if not expected_trade_dates:
        return []

    sorted_expected_dates = sorted(expected_trade_dates)

    effective_event_map: dict[date, AdjustFactorEvent] = {}
    for event in events:
        effective_date = _resolve_effective_trade_date(
            sorted_expected_dates,
            event_date=event.event_date,
            effective_offset_trade_days=effective_offset_trade_days,
        )
        if effective_date is None:
            continue
        effective_event_map[effective_date] = event

    current_forward = default_forward_factor
    current_backward = default_backward_factor

    daily_rows: list[DailyExpandedAdjustFactor] = []
    for trade_date in sorted_expected_dates:
        event = effective_event_map.get(trade_date)
        if event is not None:
            if event.forward_factor is not None:
                current_forward = event.forward_factor
            if event.backward_factor is not None:
                current_backward = event.backward_factor

        daily_rows.append(
            DailyExpandedAdjustFactor(
                trade_date=trade_date,
                forward_factor=current_forward,
                backward_factor=current_backward,
            )
        )

    return daily_rows