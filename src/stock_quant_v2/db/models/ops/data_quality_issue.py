from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import BigInteger, Date, DateTime, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base


class DataQualityIssue(Base):
    __tablename__ = "data_quality_issue"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    data_sync_run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    batch_id: Mapped[int | None] = mapped_column(BigInteger)

    theme_code: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_code: Mapped[str] = mapped_column(String(64), nullable=False)
    layer_code: Mapped[str] = mapped_column(String(16), nullable=False)
    issue_code: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)

    business_key: Mapped[str | None] = mapped_column(String(256))
    provider_name: Mapped[str | None] = mapped_column(String(32))
    trade_date: Mapped[date | None] = mapped_column(Date)
    symbol: Mapped[str | None] = mapped_column(String(64))

    record_ref: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    issue_detail: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)

    __table_args__ = (
        Index("ix_data_quality_issue_run_id", "data_sync_run_id"),
        Index("ix_data_quality_issue_theme_code", "theme_code"),
        Index("ix_data_quality_issue_issue_code", "issue_code"),
    )