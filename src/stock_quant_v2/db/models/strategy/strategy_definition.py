from __future__ import annotations

from sqlalchemy import Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base
from stock_quant_v2.db.mixins import IdMixin, TimestampMixin


class StrategyDefinition(IdMixin, TimestampMixin, Base):
    __tablename__ = "strategy_definition"
    __table_args__ = (
        UniqueConstraint(
            "strategy_code",
            name="uq_strategy_definition__strategy_code",
        ),
        Index(
            "ix_strategy_definition__strategy_type_lifecycle_status",
            "strategy_type",
            "lifecycle_status",
        ),
    )

    strategy_code: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_name: Mapped[str] = mapped_column(String(128), nullable=False)
    strategy_type: Mapped[str] = mapped_column(String(32), nullable=False)
    engine_type: Mapped[str] = mapped_column(String(32), nullable=False)
    market_scope: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="CN_A",
        server_default=text("'CN_A'"),
    )
    bar_frequency: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="1d",
        server_default=text("'1d'"),
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    lifecycle_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="draft",
        server_default=text("'draft'"),
    )
    owner: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="system",
        server_default=text("'system'"),
    )
    tags_json: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )