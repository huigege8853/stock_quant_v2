from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base
from stock_quant_v2.db.mixins import IdMixin, TimestampMixin


class MetaDefinitionVersion(IdMixin, TimestampMixin, Base):
    __tablename__ = "meta_definition_version"
    __table_args__ = (
        UniqueConstraint(
            "definition_type",
            "definition_key",
            "version",
            name="uq_meta_definition_version__definition_type_definition_key_version",
        ),
        Index(
            "ix_meta_definition_version__definition_type_definition_key",
            "definition_type",
            "definition_key",
        ),
        Index(
            "ix_meta_definition_version__status_effective_from",
            "status",
            "effective_from",
        ),
    )

    definition_type: Mapped[str] = mapped_column(String(64), nullable=False)
    definition_key: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    definition_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    effective_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    effective_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )