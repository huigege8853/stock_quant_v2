from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base
from stock_quant_v2.db.mixins import IdMixin, TimestampMixin


class MetaExchange(IdMixin, TimestampMixin, Base):
    __tablename__ = "meta_exchange"
    __table_args__ = (
        UniqueConstraint(
            "exchange_code",
            name="uq_meta_exchange__exchange_code",
        ),
        Index(
            "ix_meta_exchange__market_id",
            "market_id",
        ),
    )

    market_id: Mapped[int] = mapped_column(
        ForeignKey("meta_market.id", ondelete="RESTRICT"),
        nullable=False,
    )
    exchange_code: Mapped[str] = mapped_column(String(16), nullable=False)
    exchange_name: Mapped[str] = mapped_column(String(64), nullable=False)
    timezone_name: Mapped[str] = mapped_column(String(64), nullable=False)
    country_code: Mapped[str] = mapped_column(String(8), nullable=False)