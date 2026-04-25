from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_quant_v2.data_domain.services.universe_service import is_valid_cn_stock
from stock_quant_v2.db.models.meta.exchange import MetaExchange
from stock_quant_v2.db.models.meta.instrument import MetaInstrument
from stock_quant_v2.db.models.meta.market import MetaMarket


def load_cn_stock_backfill_universe(
    session: Session,
    *,
    start_date: date,
    end_date: date,
    market_code: str = "CN_A",
) -> list[dict]:
    stmt = (
        select(
            MetaInstrument.id,
            MetaExchange.exchange_code,
            MetaInstrument.symbol,
            MetaInstrument.instrument_type,
            MetaInstrument.list_date,
            MetaInstrument.delist_date,
        )
        .join(MetaExchange, MetaExchange.id == MetaInstrument.exchange_id)
        .join(MetaMarket, MetaMarket.id == MetaInstrument.market_id)
        .where(
            MetaMarket.market_code == market_code,
            MetaInstrument.is_active.is_(True),
            (MetaInstrument.list_date.is_(None) | (MetaInstrument.list_date <= end_date)),
            (MetaInstrument.delist_date.is_(None) | (MetaInstrument.delist_date >= start_date)),
        )
        .order_by(MetaExchange.exchange_code, MetaInstrument.symbol)
    )

    rows: list[dict] = []
    for instrument_id, exchange_code, symbol, instrument_type, list_date, delist_date in session.execute(stmt).all():
        ticker = str(symbol)
        if not is_valid_cn_stock(str(exchange_code), ticker):
            continue

        rows.append(
            {
                "instrument_id": int(instrument_id),
                "exchange_code": str(exchange_code),
                "ticker": ticker,
                "instrument_type": str(instrument_type),
                "list_date": list_date,
                "delist_date": delist_date,
            }
        )

    return rows