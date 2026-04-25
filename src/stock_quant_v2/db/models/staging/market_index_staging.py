from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, Date, Numeric, String, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base


class MarketIndexStaging(Base):
    __tablename__ = "stg_market_index"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    sync_run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    batch_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    provider_name: Mapped[str] = mapped_column(String(32), nullable=False)
    dataset_code: Mapped[str] = mapped_column(String(64), nullable=False)

    index_code: Mapped[str] = mapped_column(String(64), nullable=False)
    exchange_code: Mapped[str] = mapped_column(String(16), nullable=False)
    index_name: Mapped[str | None] = mapped_column(String(128))
    index_type: Mapped[str | None] = mapped_column(String(32))

    trade_date: Mapped[date] = mapped_column(Date, nullable=False)

    open: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    high: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    low: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    close: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    volume: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    turnover: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))

    provider_record_key: Mapped[str] = mapped_column(String(256), nullable=False)
    raw_record_id: Mapped[int | None] = mapped_column(BigInteger)

    __table_args__ = (
        UniqueConstraint(
            "provider_name",
            "index_code",
            "trade_date",
            name="uq_stg_market_index_provider_code_date",
        ),
        Index("ix_stg_market_index_code_trade_date", "index_code", "trade_date"),
        Index("ix_stg_market_index_batch_id", "batch_id"),
    )
