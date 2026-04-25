from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_quant_v2.db.models.core.market_index import MarketIndex
from stock_quant_v2.db.models.meta.exchange import MetaExchange
from stock_quant_v2.db.models.meta.trading_calendar import MetaTradingCalendar


class MarketIndexLookupRepository:
    def list_active_market_indexes(
        self,
        session: Session,
        index_codes: list[str] | None = None,
        limit: int | None = None,
    ) -> list[MarketIndex]:
        stmt = select(MarketIndex).where(MarketIndex.is_active.is_(True)).order_by(MarketIndex.index_code)
        if index_codes:
            stmt = stmt.where(MarketIndex.index_code.in_(index_codes))
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(session.execute(stmt).scalars().all())

    def get_market_index_id_map(
        self,
        session: Session,
        index_codes: list[str],
    ) -> dict[str, int]:
        if not index_codes:
            return {}
        stmt = select(MarketIndex.index_code, MarketIndex.id).where(MarketIndex.index_code.in_(index_codes))
        return {row[0]: row[1] for row in session.execute(stmt).all()}

    def list_trading_dates(
        self,
        session: Session,
        start_date: date,
        end_date: date,
        exchange_code: str = "SSE",
    ) -> list[date]:
        exchange_stmt = select(MetaExchange.id).where(MetaExchange.exchange_code == exchange_code)
        exchange_id = session.execute(exchange_stmt).scalar_one_or_none()
        if exchange_id is None:
            return []

        stmt = (
            select(MetaTradingCalendar.trade_date)
            .where(
                MetaTradingCalendar.exchange_id == exchange_id,
                MetaTradingCalendar.trade_date >= start_date,
                MetaTradingCalendar.trade_date <= end_date,
                MetaTradingCalendar.is_open.is_(True),
            )
            .order_by(MetaTradingCalendar.trade_date)
        )
        return list(session.execute(stmt).scalars().all())
