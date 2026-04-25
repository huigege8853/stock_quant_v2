from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base
from stock_quant_v2.db.mixins import IdMixin, TimestampMixin


class CoreMarketBreadth(IdMixin, TimestampMixin, Base):
    __tablename__ = "core_market_breadth"
    __table_args__ = (
        UniqueConstraint(
            "market_scope",
            "trade_date",
            name="uq_core_market_breadth__market_scope_trade_date",
        ),
        Index(
            "ix_core_market_breadth__trade_date",
            "trade_date",
        ),
        Index(
            "ix_core_market_breadth__market_scope",
            "market_scope",
        ),
        Index(
            "ix_core_market_breadth__data_version_id",
            "data_version_id",
        ),
    )

    market_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)

    universe_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bar_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    advancers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    decliners: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unchanged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    suspended_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    total_turnover_amount_cny: Mapped[Decimal | None] = mapped_column(Numeric(24, 6), nullable=True)
    mean_return: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    median_return: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)

    data_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("meta_data_version.id", ondelete="RESTRICT"),
        nullable=True,
    )