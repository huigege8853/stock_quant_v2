from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base


class AnalyticsInstrumentIndicatorSnapshot(Base):
    __tablename__ = "analytics_instrument_indicator_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "trade_date",
            "instrument_id",
            "indicator_code",
            "definition_version",
            name="uq_aiis__date_instr_code_ver",
        ),
        Index("ix_aiis__trade_date_indicator_code", "trade_date", "indicator_code"),
        Index("ix_aiis__instrument_id_trade_date", "instrument_id", "trade_date"),
        Index("ix_aiis__run_id", "run_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("meta_instrument.id"), nullable=False)
    indicator_code: Mapped[str] = mapped_column(String(64), nullable=False)
    definition_version: Mapped[str] = mapped_column(String(32), nullable=False)
    value_numeric: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    value_text: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    warmup_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    data_version_id: Mapped[int | None] = mapped_column(nullable=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("ops_run.id"), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())