from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base
from stock_quant_v2.db.mixins import IdMixin, TimestampMixin


class StrategyVersion(IdMixin, TimestampMixin, Base):
    __tablename__ = "strategy_version"
    __table_args__ = (
        UniqueConstraint(
            "strategy_definition_id",
            "version_code",
            name="uq_strategy_version__definition_id_version_code",
        ),
        UniqueConstraint(
            "strategy_definition_id",
            "version_no",
            name="uq_strategy_version__definition_id_version_no",
        ),
        Index(
            "ix_strategy_version__strategy_definition_id_is_current",
            "strategy_definition_id",
            "is_current",
        ),
        Index(
            "ix_strategy_version__lifecycle_status",
            "lifecycle_status",
        ),
    )

    strategy_definition_id: Mapped[int] = mapped_column(
        ForeignKey("strategy_definition.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_code: Mapped[str] = mapped_column(String(32), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    lifecycle_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="draft",
        server_default=text("'draft'"),
    )
    implementation_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    dependency_spec_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    output_contract_version: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="signal_v1",
        server_default=text("'signal_v1'"),
    )
    default_parameter_values_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    logic_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    retired_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)