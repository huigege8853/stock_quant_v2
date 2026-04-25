from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import BigInteger, Date, DateTime, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base


class DataSyncRun(Base):
    __tablename__ = "data_sync_run"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    sync_job_code: Mapped[str] = mapped_column(String(64), nullable=False)
    theme_code: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_code: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(32), nullable=False)

    sync_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    sync_granularity: Mapped[str] = mapped_column(String(32), nullable=False)

    partition_from: Mapped[date | None] = mapped_column(Date)
    partition_to: Mapped[date | None] = mapped_column(Date)

    status: Mapped[str] = mapped_column(String(32), nullable=False)

    cursor_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    request_params: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    stats_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))

    __table_args__ = (
        Index("ix_data_sync_run_run_id", "run_id"),
        Index("ix_data_sync_run_job_status", "sync_job_code", "status"),
        Index("ix_data_sync_run_theme_provider", "theme_code", "provider_name"),
    )