from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base
from stock_quant_v2.db.mixins import IdMixin, TimestampMixin


class OpsLock(IdMixin, TimestampMixin, Base):
    __tablename__ = "ops_lock"
    __table_args__ = (
        UniqueConstraint(
            "lock_key",
            name="uq_ops_lock__lock_key",
        ),
        Index(
            "ix_ops_lock__locked_until",
            "locked_until",
        ),
        Index(
            "ix_ops_lock__owner_run_id",
            "owner_run_id",
        ),
    )

    lock_key: Mapped[str] = mapped_column(String(128), nullable=False)
    owner_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("ops_run.id", ondelete="SET NULL"),
        nullable=True,
    )
    locked_until: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    payload_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )