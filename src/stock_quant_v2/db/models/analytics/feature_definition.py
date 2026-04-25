from __future__ import annotations

from sqlalchemy import Boolean, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base


class MetaFeatureDefinition(Base):
    __tablename__ = "meta_feature_definition"
    __table_args__ = (
        UniqueConstraint("feature_code", "version", name="uq_meta_feature_definition__code_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    feature_code: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_name: Mapped[str] = mapped_column(String(128), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_ref_code: Mapped[str] = mapped_column(String(64), nullable=False)
    dtype: Mapped[str] = mapped_column(String(32), nullable=False, default="float64")
    fillna_policy: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    scaling_policy: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    winsorize_policy: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    availability_rule_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)