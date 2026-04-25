from __future__ import annotations

from sqlalchemy import Boolean, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base
from stock_quant_v2.db.mixins import IdMixin


class Tag(IdMixin, Base):
    __tablename__ = "tag"
    __table_args__ = (
        UniqueConstraint(
            "tag_type",
            "tag_code",
            name="uq_tag_type_code",
        ),
    )

    tag_type: Mapped[str] = mapped_column(String(32), nullable=False)
    tag_code: Mapped[str] = mapped_column(String(64), nullable=False)
    tag_name: Mapped[str] = mapped_column(String(128), nullable=False)
    taxonomy_source: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )