from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base
from stock_quant_v2.db.mixins import IdMixin, TimestampMixin


class CoreAdjustFactor(IdMixin, TimestampMixin, Base):
    __tablename__ = "core_adjust_factor"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "trade_date",
            name="uq_core_adjust_factor__instrument_id_trade_date",
        ),
        Index(
            "ix_core_adjust_factor__instrument_id",
            "instrument_id",
        ),
        Index(
            "ix_core_adjust_factor__data_version_id",
            "data_version_id",
        ),
        Index(
            "ix_core_adjust_factor__trade_date",
            "trade_date",
        ),
    )

    instrument_id: Mapped[int] = mapped_column(
        ForeignKey("meta_instrument.id", ondelete="RESTRICT"),
        nullable=False,
    )
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    forward_factor: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    backward_factor: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    data_version_id: Mapped[int] = mapped_column(
        ForeignKey("meta_data_version.id", ondelete="RESTRICT"),
        nullable=False,
    )