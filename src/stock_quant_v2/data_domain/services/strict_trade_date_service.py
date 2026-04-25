from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_quant_v2.db.models.meta.exchange import MetaExchange
from stock_quant_v2.db.models.meta.trading_calendar import MetaTradingCalendar


def load_open_trade_dates_by_exchange(
    session: Session,
    *,
    start_date: date,
    end_date: date,
    exchange_codes: tuple[str, ...] = ("SSE", "SZSE", "BSE"),
) -> dict[str, list[date]]:
    exchange_rows = session.execute(
        select(MetaExchange.id, MetaExchange.exchange_code)
        .where(MetaExchange.exchange_code.in_(exchange_codes))
    ).all()

    exchange_id_to_code = {int(exchange_id): str(exchange_code) for exchange_id, exchange_code in exchange_rows}
    if not exchange_id_to_code:
        return {}

    calendar_rows = session.execute(
        select(
            MetaTradingCalendar.exchange_id,
            MetaTradingCalendar.trade_date,
        )
        .where(
            MetaTradingCalendar.exchange_id.in_(tuple(exchange_id_to_code.keys())),
            MetaTradingCalendar.trade_date >= start_date,
            MetaTradingCalendar.trade_date <= end_date,
            MetaTradingCalendar.is_open.is_(True),
        )
        .order_by(MetaTradingCalendar.exchange_id, MetaTradingCalendar.trade_date)
    ).all()

    result: dict[str, list[date]] = {code: [] for code in exchange_id_to_code.values()}
    for exchange_id, trade_date in calendar_rows:
        exchange_code = exchange_id_to_code[int(exchange_id)]
        result.setdefault(exchange_code, []).append(trade_date)

    return result