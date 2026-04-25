from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base


class MetaLabelDefinition(Base):
    __tablename__ = "meta_label_definition"
    __table_args__ = (
        UniqueConstraint("label_code", "version", name="uq_meta_label_definition__code_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    label_code: Mapped[str] = mapped_column(String(64), nullable=False)
    label_name: Mapped[str] = mapped_column(String(128), nullable=False)
    label_type: Mapped[str] = mapped_column(String(32), nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    target_expr: Mapped[str] = mapped_column(Text, nullable=False)
    price_basis: Mapped[str] = mapped_column(String(32), nullable=False, default="adj_close")
    barrier_rule_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    publish_lag_days: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    leakage_guard_rule_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)