from __future__ import annotations

from sqlalchemy import Boolean, Index, String, text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base
from stock_quant_v2.db.mixins import IdMixin, TimestampMixin


class MetaDataVendor(IdMixin, TimestampMixin, Base):
    __tablename__ = "meta_data_vendor"
    __table_args__ = (
        UniqueConstraint(
            "vendor_code",
            name="uq_meta_data_vendor__vendor_code",
        ),
        Index(
            "ix_meta_data_vendor__vendor_type_is_active",
            "vendor_type",
            "is_active",
        ),
    )

    vendor_code: Mapped[str] = mapped_column(String(32), nullable=False)
    vendor_name: Mapped[str] = mapped_column(String(128), nullable=False)
    vendor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )