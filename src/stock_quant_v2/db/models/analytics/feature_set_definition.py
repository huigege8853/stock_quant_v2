from __future__ import annotations

from sqlalchemy import Boolean, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base


class MetaFeatureSetDefinition(Base):
    __tablename__ = "meta_feature_set_definition"
    __table_args__ = (
        UniqueConstraint("feature_set_code", "version", name="uq_meta_feature_set_definition__code_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    feature_set_code: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_set_name: Mapped[str] = mapped_column(String(128), nullable=False)
    universe_rule_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    feature_codes_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    join_keys_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=lambda: ["trade_date", "instrument_id"])
    sample_filter_rule_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    standardization_rule_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    label_codes_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    train_serving_contract_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)