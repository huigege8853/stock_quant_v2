from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_quant_v2.db.models.meta.exchange import MetaExchange
from stock_quant_v2.db.models.meta.trading_calendar import MetaTradingCalendar


def load_open_trade_dates(
    session: Session,
    *,
    start_date: date,
    end_date: date,
    exchange_codes: tuple[str, ...] = ("SSE", "SZSE", "BSE"),
) -> list[date]:
    exchange_ids = list(
        session.execute(
            select(MetaExchange.id).where(MetaExchange.exchange_code.in_(exchange_codes))
        ).scalars().all()
    )
    if not exchange_ids:
        return []

    stmt = (
        select(MetaTradingCalendar.trade_date)
        .where(
            MetaTradingCalendar.exchange_id.in_(exchange_ids),
            MetaTradingCalendar.trade_date >= start_date,
            MetaTradingCalendar.trade_date <= end_date,
            MetaTradingCalendar.is_open.is_(True),
        )
        .distinct()
        .order_by(MetaTradingCalendar.trade_date)
    )
    return list(session.execute(stmt).scalars().all())