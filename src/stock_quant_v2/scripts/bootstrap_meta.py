from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.db.models import load_all_models
from stock_quant_v2.db.models.meta.market import MetaMarket
from stock_quant_v2.db.models.meta.exchange import MetaExchange
from stock_quant_v2.db.models.meta.data_vendor import MetaDataVendor
from stock_quant_v2.db.models.meta.dataset import MetaDataset


def seed_markets() -> None:
    rows = [
        {"market_code": "CN", "market_name": "China A Share"},
        {"market_code": "HK", "market_name": "Hong Kong"},
        {"market_code": "US", "market_name": "United States"},
    ]
    with SessionLocal.begin() as session:
        stmt = pg_insert(MetaMarket).values(rows)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["market_code"],
        )
        session.execute(stmt)


def seed_exchanges() -> None:
    with SessionLocal() as session:
        market_rows = session.execute(
            select(MetaMarket.id, MetaMarket.market_code)
        ).all()

    market_map = {row.market_code: row.id for row in market_rows}
    rows = [
        {
            "market_id": market_map["CN"],
            "exchange_code": "SSE",
            "exchange_name": "Shanghai Stock Exchange",
            "timezone_name": "Asia/Shanghai",
            "country_code": "CN",
        },
        {
            "market_id": market_map["CN"],
            "exchange_code": "SZSE",
            "exchange_name": "Shenzhen Stock Exchange",
            "timezone_name": "Asia/Shanghai",
            "country_code": "CN",
        },
        {
            "market_id": market_map["HK"],
            "exchange_code": "HKEX",
            "exchange_name": "Hong Kong Exchanges and Clearing",
            "timezone_name": "Asia/Hong_Kong",
            "country_code": "HK",
        },
        {
            "market_id": market_map["US"],
            "exchange_code": "NYSE",
            "exchange_name": "New York Stock Exchange",
            "timezone_name": "America/New_York",
            "country_code": "US",
        },
        {
            "market_id": market_map["US"],
            "exchange_code": "NASDAQ",
            "exchange_name": "NASDAQ",
            "timezone_name": "America/New_York",
            "country_code": "US",
        },
    ]
    with SessionLocal.begin() as session:
        stmt = pg_insert(MetaExchange).values(rows)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["exchange_code"],
        )
        session.execute(stmt)


def seed_vendors() -> None:
    rows = [
        {
            "vendor_code": "manual",
            "vendor_name": "Manual Input",
            "vendor_type": "manual",
            "is_active": True,
        },
        {
            "vendor_code": "tushare",
            "vendor_name": "TuShare",
            "vendor_type": "api",
            "is_active": True,
        },
        {
            "vendor_code": "akshare",
            "vendor_name": "AKShare",
            "vendor_type": "api",
            "is_active": True,
        },
        {
            "vendor_code": "baostock",
            "vendor_name": "BaoStock",
            "vendor_type": "api",
            "is_active": True,
        },
    ]
    with SessionLocal.begin() as session:
        stmt = pg_insert(MetaDataVendor).values(rows)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["vendor_code"],
        )
        session.execute(stmt)


def seed_datasets() -> None:
    rows = [
        {
            "dataset_code": "daily_bar",
            "dataset_name": "Daily Bar",
            "layer_code": "core",
            "grain": "instrument_trade_date",
            "description": "Canonical daily OHLCV market data",
            "is_active": True,
        },
        {
            "dataset_code": "adjust_factor",
            "dataset_name": "Adjust Factor",
            "layer_code": "core",
            "grain": "instrument_trade_date",
            "description": "Forward/backward adjustment factors",
            "is_active": True,
        },
        {
            "dataset_code": "price_limit_daily",
            "dataset_name": "Price Limit Daily",
            "layer_code": "core",
            "grain": "instrument_trade_date",
            "description": "Daily upper/lower price limits",
            "is_active": True,
        },
        {
            "dataset_code": "instrument_status_daily",
            "dataset_name": "Instrument Status Daily",
            "layer_code": "core",
            "grain": "instrument_trade_date",
            "description": "Daily instrument trading status flags",
            "is_active": True,
        },
    ]
    with SessionLocal.begin() as session:
        stmt = pg_insert(MetaDataset).values(rows)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["dataset_code"],
        )
        session.execute(stmt)


def main() -> int:
    load_all_models()
    seed_markets()
    seed_exchanges()
    seed_vendors()
    seed_datasets()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())