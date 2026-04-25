from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, Date, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base


class MarketIndexBar(Base):
    __tablename__ = "market_index_bar"
    __table_args__ = (
        UniqueConstraint("market_index_id", "trade_date", name="uq_market_index_bar_idx_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    market_index_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)

    open: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    high: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    low: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    close: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)

    volume: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    turnover: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))

    source_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    data_version_id: Mapped[int | None] = mapped_column(BigInteger)
