from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base


class CoreDailyBar(Base):
    __tablename__ = "core_daily_bar"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    instrument_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    price_adjust_type: Mapped[str] = mapped_column(String(16), nullable=False, default="RAW")

    open: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    high: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    low: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    close: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    pre_close: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))

    volume: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    turnover_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    is_suspended: Mapped[bool | None] = mapped_column()

    source_provider: Mapped[str | None] = mapped_column(String(32))
    data_version_id: Mapped[int | None] = mapped_column(BigInteger)

    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))

    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "trade_date",
            "price_adjust_type",
            name="uq_daily_bar_instrument_date_adj",
        ),
        Index("ix_daily_bar_trade_date", "trade_date"),
        Index("ix_daily_bar_source_provider", "source_provider"),
    )