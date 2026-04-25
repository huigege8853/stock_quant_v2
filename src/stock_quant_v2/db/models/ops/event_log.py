from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base
from stock_quant_v2.db.mixins import IdMixin


class OpsEventLog(IdMixin, Base):
    __tablename__ = "ops_event_log"
    __table_args__ = (
        Index(
            "ix_ops_event_log__run_id_created_at",
            "run_id",
            "created_at",
        ),
        Index(
            "ix_ops_event_log__run_step_id",
            "run_step_id",
        ),
    )

    run_id: Mapped[int] = mapped_column(
        ForeignKey("ops_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_step_id: Mapped[int | None] = mapped_column(
        ForeignKey("ops_run_step.id", ondelete="SET NULL"),
        nullable=True,
    )
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )