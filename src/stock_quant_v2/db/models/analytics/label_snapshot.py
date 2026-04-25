from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base


class AnalyticsLabelSnapshot(Base):
    __tablename__ = "analytics_label_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "anchor_date",
            "instrument_id",
            "label_code",
            "definition_version",
            name="uq_als__date_instr_code_ver",
        ),
        Index("ix_als__anchor_date_label_code", "anchor_date", "label_code"),
        Index("ix_als__instrument_id_anchor_date", "instrument_id", "anchor_date"),
        Index("ix_als__run_id", "run_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    anchor_date: Mapped[date] = mapped_column(Date, nullable=False)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("meta_instrument.id"), nullable=False)
    label_code: Mapped[str] = mapped_column(String(64), nullable=False)
    definition_version: Mapped[str] = mapped_column(String(32), nullable=False)
    label_value_numeric: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    label_value_class: Mapped[str | None] = mapped_column(String(32), nullable=True)
    horizon_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_censored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    leakage_checked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    run_id: Mapped[int] = mapped_column(ForeignKey("ops_run.id"), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())