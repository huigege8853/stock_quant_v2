from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base


class MetaFactorDefinition(Base):
    __tablename__ = "meta_factor_definition"
    __table_args__ = (
        UniqueConstraint("factor_code", "version", name="uq_meta_factor_definition__code_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    factor_code: Mapped[str] = mapped_column(String(64), nullable=False)
    factor_name: Mapped[str] = mapped_column(String(128), nullable=False)
    factor_family: Mapped[str] = mapped_column(String(64), nullable=False)
    base_indicator_codes_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    transform_pipeline_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    cross_sectional_scope: Mapped[str] = mapped_column(String(64), nullable=False, default="all_a_share")
    winsorize_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    standardize_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    neutralize_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    warmup_bars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    publish_lag_days: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    value_type: Mapped[str] = mapped_column(String(32), nullable=False, default="numeric")
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)