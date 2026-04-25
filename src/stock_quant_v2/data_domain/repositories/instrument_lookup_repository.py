from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_quant_v2.db.models.meta.exchange import MetaExchange
from stock_quant_v2.db.models.meta.instrument import MetaInstrument


class InstrumentLookupRepository:
    def get_exchange_id(self, session: Session, exchange_code: str) -> int | None:
        stmt = select(MetaExchange.id).where(MetaExchange.exchange_code == exchange_code)
        return session.execute(stmt).scalar_one_or_none()

    def get_instrument_id(
        self,
        session: Session,
        market_code: str,
        exchange_code: str,
        ticker: str,
    ) -> int | None:
        # 当前版本先不使用 market_code 过滤，因为 MetaInstrument 实际存的是 market_id
        exchange_id = self.get_exchange_id(session=session, exchange_code=exchange_code)
        if exchange_id is None:
            return None

        stmt = select(MetaInstrument.id).where(
            MetaInstrument.exchange_id == exchange_id,
            MetaInstrument.symbol == ticker,
        )
        return session.execute(stmt).scalar_one_or_none()

    def get_instrument_lifecycle(
        self,
        session: Session,
        exchange_code: str,
        ticker: str,
    ) -> tuple | None:
        exchange_id = self.get_exchange_id(session=session, exchange_code=exchange_code)
        if exchange_id is None:
            return None

        stmt = select(MetaInstrument.list_date, MetaInstrument.delist_date).where(
            MetaInstrument.exchange_id == exchange_id,
            MetaInstrument.symbol == ticker,
        )
        return session.execute(stmt).one_or_none()