from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base


class DataLineage(Base):
    __tablename__ = "data_lineage"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    data_sync_run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    batch_id: Mapped[int | None] = mapped_column(BigInteger)

    theme_code: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_code: Mapped[str] = mapped_column(String(64), nullable=False)

    source_layer: Mapped[str] = mapped_column(String(16), nullable=False)
    source_table: Mapped[str] = mapped_column(String(128), nullable=False)
    source_record_ref: Mapped[str] = mapped_column(String(256), nullable=False)

    target_layer: Mapped[str] = mapped_column(String(16), nullable=False)
    target_table: Mapped[str] = mapped_column(String(128), nullable=False)
    target_record_ref: Mapped[str] = mapped_column(String(256), nullable=False)

    transform_code: Mapped[str] = mapped_column(String(64), nullable=False)
    transform_version: Mapped[str] = mapped_column(String(64), nullable=False)
    lineage_meta: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)

    __table_args__ = (
        Index("ix_data_lineage_run_id", "data_sync_run_id"),
        Index("ix_data_lineage_source", "source_table", "source_record_ref"),
        Index("ix_data_lineage_target", "target_table", "target_record_ref"),
    )