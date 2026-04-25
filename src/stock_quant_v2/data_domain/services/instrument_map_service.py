from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_quant_v2.db.models.meta.exchange import MetaExchange
from stock_quant_v2.db.models.meta.instrument import MetaInstrument
from stock_quant_v2.db.models.meta.market import MetaMarket


def load_instrument_id_map(
    session: Session,
    *,
    market_code: str | None = None,
) -> dict[tuple[str, str], int]:
    stmt = (
        select(
            MetaExchange.exchange_code,
            MetaInstrument.symbol,
            MetaInstrument.id,
        )
        .join(MetaExchange, MetaExchange.id == MetaInstrument.exchange_id)
        .join(MetaMarket, MetaMarket.id == MetaInstrument.market_id)
        .where(MetaInstrument.is_active.is_(True))
    )

    if market_code:
        stmt = stmt.where(MetaMarket.market_code == market_code)

    rows = session.execute(stmt).all()

    result: dict[tuple[str, str], int] = {}
    for exchange_code, symbol, instrument_id in rows:
        result[(str(exchange_code), str(symbol))] = int(instrument_id)

    return result


def lookup_instrument_id(
    instrument_id_map: dict[tuple[str, str], int],
    *,
    exchange_code: str,
    ticker: str,
) -> int | None:
    return instrument_id_map.get((str(exchange_code), str(ticker)))