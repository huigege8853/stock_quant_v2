from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base
from stock_quant_v2.db.mixins import IdMixin


class StrategySignal(IdMixin, Base):
    __tablename__ = "strategy_signal"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "strategy_version_id",
            "as_of_date",
            "subject_key",
            "signal_action",
            name="uq_strategy_signal__run_ver_asof_subject_action",
        ),
        Index(
            "ix_strategy_signal__strategy_version_id_as_of_date",
            "strategy_version_id",
            "as_of_date",
        ),
        Index(
            "ix_strategy_signal__effective_date",
            "effective_date",
        ),
        Index(
            "ix_strategy_signal__instrument_id_effective_date",
            "instrument_id",
            "effective_date",
        ),
        Index(
            "ix_strategy_signal__subject_type_subject_key_effective_date",
            "subject_type",
            "subject_key",
            "effective_date",
        ),
        Index(
            "ix_strategy_signal__run_id",
            "run_id",
        ),
    )

    run_id: Mapped[int] = mapped_column(
        ForeignKey("ops_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    strategy_version_id: Mapped[int] = mapped_column(
        ForeignKey("strategy_version.id", ondelete="CASCADE"),
        nullable=False,
    )
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    subject_type: Mapped[str] = mapped_column(String(16), nullable=False)
    subject_key: Mapped[str] = mapped_column(String(128), nullable=False)
    instrument_id: Mapped[int | None] = mapped_column(
        ForeignKey("meta_instrument.id", ondelete="SET NULL"),
        nullable=True,
    )
    signal_role: Mapped[str] = mapped_column(String(32), nullable=False)
    signal_side: Mapped[str] = mapped_column(String(16), nullable=False)
    signal_action: Mapped[str] = mapped_column(String(32), nullable=False)
    raw_score: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    normalized_score: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    rank_in_batch: Mapped[int | None] = mapped_column(Integer, nullable=True)
    universe_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    reason_payload_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    parameter_payload_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )