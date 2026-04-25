from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import BigInteger, Date, DateTime, JSON, String, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base


class MarketIndexRaw(Base):
    __tablename__ = "raw_market_index"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    provider_name: Mapped[str] = mapped_column(String(32), nullable=False)
    dataset_code: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_record_key: Mapped[str] = mapped_column(String(256), nullable=False)

    symbol: Mapped[str | None] = mapped_column(String(64))
    trade_date: Mapped[date | None] = mapped_column(Date)

    batch_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sync_run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    request_params: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    provider_update_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "provider_name",
            "dataset_code",
            "provider_record_key",
            name="uq_raw_market_index_provider_key",
        ),
        Index("ix_raw_market_index_symbol_trade_date", "symbol", "trade_date"),
        Index("ix_raw_market_index_batch_id", "batch_id"),
        Index("ix_raw_market_index_sync_run_id", "sync_run_id"),
    )
