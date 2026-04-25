from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_quant_v2.db.models.meta.exchange import MetaExchange
from stock_quant_v2.db.models.meta.instrument import MetaInstrument


def is_valid_cn_stock(exchange_code: str, symbol: str) -> bool:
    symbol = str(symbol or "").strip()
    exchange = (exchange_code or "").strip().upper()

    if exchange == "SSE":
        return symbol.startswith(("600", "601", "603", "605", "688", "689"))

    if exchange == "SZSE":
        return symbol.startswith(("000", "001", "002", "003", "300", "301"))

    if exchange == "BSE":
        return symbol.startswith(("430", "830", "831", "832", "833", "835", "836", "837", "838", "839"))

    return False


def load_cn_stock_universe(session: Session, trade_date: date) -> list[dict]:
    stmt = (
        select(
            MetaInstrument.id,
            MetaExchange.exchange_code,
            MetaInstrument.symbol,
            MetaInstrument.instrument_type,
        )
        .join(MetaExchange, MetaExchange.id == MetaInstrument.exchange_id)
        .where(
            MetaInstrument.is_active.is_(True),
            (MetaInstrument.list_date.is_(None) | (MetaInstrument.list_date <= trade_date)),
            (MetaInstrument.delist_date.is_(None) | (MetaInstrument.delist_date >= trade_date)),
        )
        .order_by(MetaExchange.exchange_code, MetaInstrument.symbol)
    )

    rows: list[dict] = []
    for instrument_id, exchange_code, symbol, instrument_type in session.execute(stmt).all():
        if not is_valid_cn_stock(exchange_code, str(symbol)):
            continue

        rows.append(
            {
                "instrument_id": instrument_id,
                "exchange_code": exchange_code,
                "ticker": str(symbol),
                "instrument_type": instrument_type,
            }
        )

    return rows


def load_cn_index_universe(session: Session, trade_date: date) -> list[dict]:
    stmt = (
        select(
            MetaInstrument.id,
            MetaExchange.exchange_code,
            MetaInstrument.symbol,
            MetaInstrument.instrument_type,
        )
        .join(MetaExchange, MetaExchange.id == MetaInstrument.exchange_id)
        .where(
            MetaInstrument.is_active.is_(True),
            (MetaInstrument.list_date.is_(None) | (MetaInstrument.list_date <= trade_date)),
            (MetaInstrument.delist_date.is_(None) | (MetaInstrument.delist_date >= trade_date)),
            MetaInstrument.instrument_type.in_(("INDEX", "BOND_INDEX", "FUND_INDEX")),
        )
        .order_by(MetaExchange.exchange_code, MetaInstrument.symbol)
    )

    return [
        {
            "instrument_id": instrument_id,
            "exchange_code": exchange_code,
            "ticker": str(symbol),
            "instrument_type": instrument_type,
        }
        for instrument_id, exchange_code, symbol, instrument_type in session.execute(stmt).all()
    ]