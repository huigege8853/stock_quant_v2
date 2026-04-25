from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base
from stock_quant_v2.db.mixins import IdMixin, TimestampMixin


class OpsRun(IdMixin, TimestampMixin, Base):
    __tablename__ = "ops_run"
    __table_args__ = (
        UniqueConstraint(
            "run_uid",
            name="uq_ops_run__run_uid",
        ),
        Index(
            "ix_ops_run__parent_run_id",
            "parent_run_id",
        ),
        Index(
            "ix_ops_run__run_type_status",
            "run_type",
            "status",
        ),
        Index(
            "ix_ops_run__requested_at",
            "requested_at",
        ),
    )

    run_uid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        default=uuid.uuid4,
    )
    run_type: Mapped[str] = mapped_column(String(32), nullable=False)
    run_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False)
    parent_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("ops_run.id", ondelete="SET NULL"),
        nullable=True,
    )
    requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    context_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)