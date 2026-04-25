from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base


class AnalyticsFeatureSnapshot(Base):
    __tablename__ = "analytics_feature_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "trade_date",
            "instrument_id",
            "feature_code",
            "feature_set_code",
            "feature_set_version",
            name="uq_afs__date_instr_feature_set_ver",
        ),
        Index("ix_afs__trade_date_feature_set_code", "trade_date", "feature_set_code"),
        Index("ix_afs__instrument_id_trade_date", "instrument_id", "trade_date"),
        Index("ix_afs__run_id", "run_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("meta_instrument.id"), nullable=False)
    feature_code: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_set_code: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_set_version: Mapped[str] = mapped_column(String(32), nullable=False)
    feature_value_numeric: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    feature_value_text: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_imputed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    impute_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    scaling_applied: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sample_status: Mapped[str] = mapped_column(String(32), nullable=False, default="ready")
    run_id: Mapped[int] = mapped_column(ForeignKey("ops_run.id"), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())