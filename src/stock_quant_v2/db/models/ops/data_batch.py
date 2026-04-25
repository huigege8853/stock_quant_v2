from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import BigInteger, Date, DateTime, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base


class DataBatch(Base):
    __tablename__ = "data_batch"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    data_sync_run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    batch_no: Mapped[int] = mapped_column(Integer, nullable=False)
    batch_key: Mapped[str] = mapped_column(String(128), nullable=False)
    batch_type: Mapped[str] = mapped_column(String(32), nullable=False)

    partition_date: Mapped[date | None] = mapped_column(Date)
    partition_symbol: Mapped[str | None] = mapped_column(String(64))
    page_no: Mapped[int | None] = mapped_column(Integer)

    status: Mapped[str] = mapped_column(String(32), nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    input_rows: Mapped[int | None] = mapped_column(Integer)
    raw_rows: Mapped[int | None] = mapped_column(Integer)
    staging_rows: Mapped[int | None] = mapped_column(Integer)
    core_upsert_rows: Mapped[int | None] = mapped_column(Integer)
    error_rows: Mapped[int | None] = mapped_column(Integer)

    checkpoint_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(String(1000))

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))

    __table_args__ = (
        Index("ix_data_batch_run_id", "data_sync_run_id"),
        Index("ix_data_batch_status", "status"),
    )