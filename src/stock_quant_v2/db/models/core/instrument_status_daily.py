from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Index, String, text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base
from stock_quant_v2.db.mixins import IdMixin, TimestampMixin


class CoreInstrumentStatusDaily(IdMixin, TimestampMixin, Base):
    __tablename__ = "core_instrument_status_daily"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "trade_date",
            name="uq_core_instrument_status_daily__instrument_id_trade_date",
        ),
        Index(
            "ix_core_instrument_status_daily__instrument_id",
            "instrument_id",
        ),
        Index(
            "ix_core_instrument_status_daily__data_version_id",
            "data_version_id",
        ),
        Index(
            "ix_core_instrument_status_daily__trade_date",
            "trade_date",
        ),
    )

    instrument_id: Mapped[int] = mapped_column(
        ForeignKey("meta_instrument.id", ondelete="RESTRICT"),
        nullable=False,
    )
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    trading_status: Mapped[str] = mapped_column(String(32), nullable=False)
    is_st: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    is_suspended: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    data_version_id: Mapped[int] = mapped_column(
        ForeignKey("meta_data_version.id", ondelete="RESTRICT"),
        nullable=False,
    )