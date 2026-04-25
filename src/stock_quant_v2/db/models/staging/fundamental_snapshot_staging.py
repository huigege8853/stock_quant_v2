from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base


class FundamentalSnapshotStaging(Base):
    __tablename__ = "stg_fundamental_snapshot"

    __table_args__ = (
        UniqueConstraint(
            "provider_name",
            "ticker",
            "trade_date",
            "snapshot_type",
            name="uq_stg_fundamental_snapshot_key",
        ),
        Index("ix_stg_fundamental_snapshot_ticker_date", "ticker", "trade_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    sync_run_id: Mapped[int | None] = mapped_column(nullable=True)
    batch_id: Mapped[int | None] = mapped_column(nullable=True)

    provider_name: Mapped[str] = mapped_column(String(50), nullable=False)
    dataset_code: Mapped[str] = mapped_column(String(100), nullable=False)

    market_code: Mapped[str] = mapped_column(String(32), nullable=False)
    exchange_code: Mapped[str] = mapped_column(String(16), nullable=False)
    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    vendor_symbol: Mapped[str | None] = mapped_column(String(64), nullable=True)

    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    snapshot_type: Mapped[str] = mapped_column(String(64), nullable=False)

    pe_ttm: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    pb: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    ps_ttm: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    total_mv: Mapped[float | None] = mapped_column(Numeric(24, 8), nullable=True)
    circ_mv: Mapped[float | None] = mapped_column(Numeric(24, 8), nullable=True)

    provider_record_key: Mapped[str] = mapped_column(String(255), nullable=False)

    raw_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_fundamental_snapshot.id"),
        nullable=True,
    )