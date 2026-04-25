from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Index, text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base
from stock_quant_v2.db.mixins import IdMixin, TimestampMixin


class MetaTradingCalendar(IdMixin, TimestampMixin, Base):
    __tablename__ = "meta_trading_calendar"
    __table_args__ = (
        UniqueConstraint(
            "exchange_id",
            "trade_date",
            name="uq_meta_trading_calendar__exchange_id_trade_date",
        ),
        Index(
            "ix_meta_trading_calendar__trade_date",
            "trade_date",
        ),
        Index(
            "ix_meta_trading_calendar__exchange_id",
            "exchange_id",
        ),
    )

    exchange_id: Mapped[int] = mapped_column(
        ForeignKey("meta_exchange.id", ondelete="RESTRICT"),
        nullable=False,
    )
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_open: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    previous_trade_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_trade_date: Mapped[date | None] = mapped_column(Date, nullable=True)