from __future__ import annotations

from sqlalchemy import select

from stock_quant_v2.db.models.meta.data_vendor import MetaDataVendor
from stock_quant_v2.db.models.meta.dataset import MetaDataset
from stock_quant_v2.db.models.meta.exchange import MetaExchange
from stock_quant_v2.db.models.meta.market import MetaMarket
from stock_quant_v2.db.session import SessionLocal


def upsert_market(session, market_code: str, market_name: str) -> MetaMarket:
    stmt = select(MetaMarket).where(MetaMarket.market_code == market_code)
    obj = session.execute(stmt).scalar_one_or_none()

    if obj is None:
        obj = MetaMarket(
            market_code=market_code,
            market_name=market_name,
        )
        session.add(obj)
        print(f"[OK] created market: {market_code} - {market_name}")
    else:
        obj.market_name = market_name
        print(f"[OK] updated market: {market_code} - {market_name}")

    session.flush()
    return obj


def upsert_exchange(
    session,
    market_code: str,
    exchange_code: str,
    exchange_name: str,
    timezone_name: str,
    country_code: str,
) -> MetaExchange:
    market_stmt = select(MetaMarket).where(MetaMarket.market_code == market_code)
    market = session.execute(market_stmt).scalar_one_or_none()
    if market is None:
        raise ValueError(f"market_code not found: {market_code}")

    stmt = select(MetaExchange).where(MetaExchange.exchange_code == exchange_code)
    obj = session.execute(stmt).scalar_one_or_none()

    if obj is None:
        obj = MetaExchange(
            market_id=market.id,
            exchange_code=exchange_code,
            exchange_name=exchange_name,
            timezone_name=timezone_name,
            country_code=country_code,
        )
        session.add(obj)
        print(f"[OK] created exchange: {exchange_code} - {exchange_name}")
    else:
        obj.market_id = market.id
        obj.exchange_name = exchange_name
        obj.timezone_name = timezone_name
        obj.country_code = country_code
        print(f"[OK] updated exchange: {exchange_code} - {exchange_name}")

    session.flush()
    return obj


def upsert_vendor(session, vendor_code: str, vendor_name: str, vendor_type: str) -> MetaDataVendor:
    stmt = select(MetaDataVendor).where(MetaDataVendor.vendor_code == vendor_code)
    obj = session.execute(stmt).scalar_one_or_none()

    if obj is None:
        obj = MetaDataVendor(
            vendor_code=vendor_code,
            vendor_name=vendor_name,
            vendor_type=vendor_type,
            is_active=True,
        )
        session.add(obj)
        print(f"[OK] created vendor: {vendor_code} - {vendor_name}")
    else:
        obj.vendor_name = vendor_name
        obj.vendor_type = vendor_type
        obj.is_active = True
        print(f"[OK] updated vendor: {vendor_code} - {vendor_name}")

    session.flush()
    return obj


def upsert_dataset(
    session,
    dataset_code: str,
    dataset_name: str,
    layer_code: str,
    grain: str,
    description: str | None,
) -> MetaDataset:
    stmt = select(MetaDataset).where(MetaDataset.dataset_code == dataset_code)
    obj = session.execute(stmt).scalar_one_or_none()

    if obj is None:
        obj = MetaDataset(
            dataset_code=dataset_code,
            dataset_name=dataset_name,
            layer_code=layer_code,
            grain=grain,
            description=description,
            is_active=True,
        )
        session.add(obj)
        print(f"[OK] created dataset: {dataset_code} - {dataset_name}")
    else:
        obj.dataset_name = dataset_name
        obj.layer_code = layer_code
        obj.grain = grain
        obj.description = description
        obj.is_active = True
        print(f"[OK] updated dataset: {dataset_code} - {dataset_name}")

    session.flush()
    return obj


def main() -> None:
    print("[START] bootstrap_meta_data_domain")

    with SessionLocal() as session:
        try:
            # market
            upsert_market(session, market_code="CN_A", market_name="China A Share")
            print("[STEP] market done")

            # exchange
            upsert_exchange(
                session,
                market_code="CN_A",
                exchange_code="SSE",
                exchange_name="Shanghai Stock Exchange",
                timezone_name="Asia/Shanghai",
                country_code="CN",
            )
            upsert_exchange(
                session,
                market_code="CN_A",
                exchange_code="SZSE",
                exchange_name="Shenzhen Stock Exchange",
                timezone_name="Asia/Shanghai",
                country_code="CN",
            )
            upsert_exchange(
                session,
                market_code="CN_A",
                exchange_code="BSE",
                exchange_name="Beijing Stock Exchange",
                timezone_name="Asia/Shanghai",
                country_code="CN",
            )
            print("[STEP] exchange done")

            # vendor
            upsert_vendor(session, "baostock", "BaoStock", "PUBLIC_API")
            upsert_vendor(session, "tushare", "Tushare", "PUBLIC_API")
            upsert_vendor(session, "akshare", "AKShare", "PUBLIC_API")
            upsert_vendor(session, "sina", "Sina", "PUBLIC_API")
            upsert_vendor(session, "future_paid_vendor", "Future Paid Vendor", "PAID_API")
            print("[STEP] vendor done")

            # dataset
            upsert_dataset(
                session,
                dataset_code="instrument",
                dataset_name="Instrument Master",
                layer_code="META",
                grain="instrument",
                description="Instrument master for A-share universe",
            )
            upsert_dataset(
                session,
                dataset_code="trading_calendar",
                dataset_name="Trading Calendar",
                layer_code="META",
                grain="exchange_id+trade_date",
                description="Trading calendar by exchange",
            )
            upsert_dataset(
                session,
                dataset_code="daily_bar",
                dataset_name="Daily Bar",
                layer_code="CORE",
                grain="instrument_id+trade_date+price_adjust_type",
                description="A-share daily OHLCV core fact table",
            )
            upsert_dataset(
                session,
                dataset_code="fundamental_snapshot",
                dataset_name="Fundamental Snapshot",
                layer_code="CORE",
                grain="instrument_id+trade_date+snapshot_type",
                description="Valuation and financial snapshot fact table",
            )
            upsert_dataset(
                session,
                dataset_code="market_index",
                dataset_name="Market Index",
                layer_code="CORE",
                grain="index_code",
                description="Index master data",
            )
            upsert_dataset(
                session,
                dataset_code="market_index_bar",
                dataset_name="Market Index Bar",
                layer_code="CORE",
                grain="market_index_id+trade_date",
                description="Index daily bar fact table",
            )
            upsert_dataset(
                session,
                dataset_code="market_breadth",
                dataset_name="Market Breadth",
                layer_code="CORE",
                grain="trade_date+exchange_code+universe_code",
                description="Market breadth snapshot",
            )
            print("[STEP] dataset done")

            session.commit()
            print("[SUCCESS] bootstrap_meta_data_domain committed successfully")

        except Exception as e:
            session.rollback()
            print(f"[ERROR] bootstrap_meta_data_domain failed: {e}")
            raise
        finally:
            print("[END] session closed")


if __name__ == "__main__":
    main()