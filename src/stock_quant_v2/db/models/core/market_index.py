from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base


class MarketIndex(Base):
    __tablename__ = "market_index"
    __table_args__ = (
        UniqueConstraint("index_code", name="uq_market_index_code"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    index_code: Mapped[str] = mapped_column(String(64), nullable=False)
    index_name: Mapped[str] = mapped_column(String(128), nullable=False)
    exchange_code: Mapped[str] = mapped_column(String(16), nullable=False)
    index_type: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
