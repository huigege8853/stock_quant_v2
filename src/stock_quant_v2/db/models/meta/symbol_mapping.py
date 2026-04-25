from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, String, text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base
from stock_quant_v2.db.mixins import IdMixin, TimestampMixin


class MetaSymbolMapping(IdMixin, TimestampMixin, Base):
    __tablename__ = "meta_symbol_mapping"
    __table_args__ = (
        UniqueConstraint(
            "vendor_id",
            "instrument_id",
            name="uq_meta_symbol_mapping__vendor_id_instrument_id",
        ),
        UniqueConstraint(
            "vendor_id",
            "vendor_symbol",
            name="uq_meta_symbol_mapping__vendor_id_vendor_symbol",
        ),
        Index(
            "ix_meta_symbol_mapping__instrument_id",
            "instrument_id",
        ),
        Index(
            "ix_meta_symbol_mapping__vendor_id",
            "vendor_id",
        ),
    )

    vendor_id: Mapped[int] = mapped_column(
        ForeignKey("meta_data_vendor.id", ondelete="RESTRICT"),
        nullable=False,
    )
    instrument_id: Mapped[int] = mapped_column(
        ForeignKey("meta_instrument.id", ondelete="CASCADE"),
        nullable=False,
    )
    vendor_symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )