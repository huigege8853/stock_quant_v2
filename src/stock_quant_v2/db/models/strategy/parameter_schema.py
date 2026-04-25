from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base
from stock_quant_v2.db.mixins import IdMixin, TimestampMixin


class StrategyParameterSchema(IdMixin, TimestampMixin, Base):
    __tablename__ = "strategy_parameter_schema"
    __table_args__ = (
        UniqueConstraint(
            "strategy_version_id",
            name="uq_strategy_parameter_schema__strategy_version_id",
        ),
        Index(
            "ix_strategy_parameter_schema__strategy_version_id",
            "strategy_version_id",
        ),
    )

    strategy_version_id: Mapped[int] = mapped_column(
        ForeignKey("strategy_version.id", ondelete="CASCADE"),
        nullable=False,
    )
    schema_version_code: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="jsonschema_v1",
        server_default=text("'jsonschema_v1'"),
    )
    parameter_schema_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    example_payload_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    validation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)