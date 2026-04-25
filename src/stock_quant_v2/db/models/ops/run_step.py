from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base
from stock_quant_v2.db.mixins import IdMixin, TimestampMixin


class OpsRunStep(IdMixin, TimestampMixin, Base):
    __tablename__ = "ops_run_step"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "step_code",
            name="uq_ops_run_step__run_id_step_code",
        ),
        Index(
            "ix_ops_run_step__run_id",
            "run_id",
        ),
        Index(
            "ix_ops_run_step__run_id_sequence_no",
            "run_id",
            "sequence_no",
        ),
    )

    run_id: Mapped[int] = mapped_column(
        ForeignKey("ops_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_code: Mapped[str] = mapped_column(String(64), nullable=False)
    step_name: Mapped[str] = mapped_column(String(128), nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    payload_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)