from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base


class DailyBarStaging(Base):
    __tablename__ = "stg_daily_bar"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    sync_run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    batch_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    provider_name: Mapped[str] = mapped_column(String(32), nullable=False)
    dataset_code: Mapped[str] = mapped_column(String(64), nullable=False)

    market_code: Mapped[str] = mapped_column(String(16), nullable=False)
    exchange_code: Mapped[str] = mapped_column(String(16), nullable=False)
    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    vendor_symbol: Mapped[str | None] = mapped_column(String(64))

    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    price_adjust_type: Mapped[str] = mapped_column(String(16), nullable=False)

    open: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    high: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    low: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    close: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    pre_close: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))

    volume: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    turnover: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    amplitude: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    pct_change: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    price_change: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    turnover_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))

    suspended_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    provider_record_key: Mapped[str] = mapped_column(String(256), nullable=False)
    raw_record_id: Mapped[int | None] = mapped_column(BigInteger)

    __table_args__ = (
        UniqueConstraint(
            "provider_name",
            "ticker",
            "trade_date",
            "price_adjust_type",
            name="uq_stg_daily_bar_provider_ticker_date_adj",
        ),
        Index("ix_stg_daily_bar_ticker_trade_date", "ticker", "trade_date"),
        Index("ix_stg_daily_bar_batch_id", "batch_id"),
    )