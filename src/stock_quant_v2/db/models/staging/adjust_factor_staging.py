from __future__ import annotations

from datetime import date

from sqlalchemy import BigInteger, Date, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base


class AdjustFactorStaging(Base):
    __tablename__ = "stg_adjust_factor"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    sync_run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    batch_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    provider_name: Mapped[str] = mapped_column(String(32), nullable=False)
    dataset_code: Mapped[str] = mapped_column(String(64), nullable=False)

    market_code: Mapped[str] = mapped_column(String(16), nullable=False)
    exchange_code: Mapped[str] = mapped_column(String(16), nullable=False)
    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    vendor_symbol: Mapped[str | None] = mapped_column(String(64))

    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    adjust_factor: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)

    provider_record_key: Mapped[str] = mapped_column(String(256), nullable=False)
    raw_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_adjust_factor.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "provider_name",
            "ticker",
            "trade_date",
            name="uq_stg_adjust_factor_provider_ticker_date",
        ),
        Index("ix_stg_adjust_factor_trade_date", "trade_date"),
        Index("ix_stg_adjust_factor_batch_id", "batch_id"),
        Index("ix_stg_adjust_factor_sync_run_id", "sync_run_id"),
    )