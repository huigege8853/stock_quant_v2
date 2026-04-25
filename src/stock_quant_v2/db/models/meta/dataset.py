from __future__ import annotations

from sqlalchemy import Boolean, Index, String, Text, text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base
from stock_quant_v2.db.mixins import IdMixin, TimestampMixin


class MetaDataset(IdMixin, TimestampMixin, Base):
    __tablename__ = "meta_dataset"
    __table_args__ = (
        UniqueConstraint(
            "dataset_code",
            name="uq_meta_dataset__dataset_code",
        ),
        Index(
            "ix_meta_dataset__layer_code_is_active",
            "layer_code",
            "is_active",
        ),
    )

    dataset_code: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_name: Mapped[str] = mapped_column(String(128), nullable=False)
    layer_code: Mapped[str] = mapped_column(String(32), nullable=False)
    grain: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )