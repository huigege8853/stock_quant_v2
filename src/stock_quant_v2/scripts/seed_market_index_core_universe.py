from __future__ import annotations

from sqlalchemy import select

from stock_quant_v2.db.models.core.market_index import MarketIndex
from stock_quant_v2.db.session import SessionLocal


CORE_INDEXES = [
    {"index_code": "000001.SH", "index_name": "上证综指", "exchange_code": "SSE", "index_type": "BROAD", "is_active": True},
    {"index_code": "399001.SZ", "index_name": "深证成指", "exchange_code": "SZSE", "index_type": "BROAD", "is_active": True},
    {"index_code": "399006.SZ", "index_name": "创业板指", "exchange_code": "SZSE", "index_type": "BROAD", "is_active": True},
    {"index_code": "000300.SH", "index_name": "沪深300", "exchange_code": "SSE", "index_type": "CROSS_MARKET", "is_active": True},
]


def main() -> None:
    session = SessionLocal()
    try:
        inserted = 0
        updated = 0
        for row in CORE_INDEXES:
            stmt = select(MarketIndex).where(MarketIndex.index_code == row["index_code"])
            obj = session.execute(stmt).scalar_one_or_none()
            if obj is None:
                session.add(MarketIndex(**row))
                inserted += 1
            else:
                obj.index_name = row["index_name"]
                obj.exchange_code = row["exchange_code"]
                obj.index_type = row["index_type"]
                obj.is_active = row["is_active"]
                updated += 1
        session.commit()
        print({
            "inserted": inserted,
            "updated": updated,
            "total_after_seed": session.query(MarketIndex).count(),
        })
    finally:
        session.close()


if __name__ == "__main__":
    main()
