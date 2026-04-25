from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base


class FundamentalSnapshotRaw(Base):
    __tablename__ = "raw_fundamental_snapshot"

    __table_args__ = (
        UniqueConstraint(
            "provider_name",
            "dataset_code",
            "provider_record_key",
            name="uq_raw_fundamental_snapshot_key",
        ),
        Index("ix_raw_fundamental_snapshot_symbol_date", "symbol", "trade_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    provider_name: Mapped[str] = mapped_column(String(50), nullable=False)
    dataset_code: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_record_key: Mapped[str] = mapped_column(String(255), nullable=False)

    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    trade_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    batch_id: Mapped[int | None] = mapped_column(nullable=True)
    sync_run_id: Mapped[int | None] = mapped_column(nullable=True)

    request_params: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    provider_update_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)