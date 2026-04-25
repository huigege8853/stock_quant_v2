from __future__ import annotations

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base
from stock_quant_v2.db.mixins import IdMixin, TimestampMixin


class MetaMarket(IdMixin, TimestampMixin, Base):
    __tablename__ = "meta_market"
    __table_args__ = (
        UniqueConstraint(
            "market_code",
            name="uq_meta_market__market_code",
        ),
    )

    market_code: Mapped[str] = mapped_column(String(16), nullable=False)
    market_name: Mapped[str] = mapped_column(String(64), nullable=False)