from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base


class MetaIndicatorDefinition(Base):
    __tablename__ = "meta_indicator_definition"
    __table_args__ = (
        UniqueConstraint("indicator_code", "version", name="uq_meta_indicator_definition__code_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    indicator_code: Mapped[str] = mapped_column(String(64), nullable=False)
    indicator_name: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    input_topic: Mapped[str] = mapped_column(String(64), nullable=False)
    input_fields_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    formula_expr: Mapped[str | None] = mapped_column(Text, nullable=True)
    window_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    warmup_bars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    price_adjust_type: Mapped[str] = mapped_column(String(32), nullable=False, default="forward_adj")
    publish_lag_days: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    null_policy: Mapped[str] = mapped_column(String(32), nullable=False, default="keep_null")
    value_type: Mapped[str] = mapped_column(String(32), nullable=False, default="numeric")
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)