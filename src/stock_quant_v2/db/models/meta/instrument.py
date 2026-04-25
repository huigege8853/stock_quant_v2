from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Index, String, text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base
from stock_quant_v2.db.mixins import IdMixin, TimestampMixin


class MetaInstrument(IdMixin, TimestampMixin, Base):
    __tablename__ = "meta_instrument"
    __table_args__ = (
        UniqueConstraint(
            "instrument_code",
            name="uq_meta_instrument__instrument_code",
        ),
        UniqueConstraint(
            "exchange_id",
            "symbol",
            name="uq_meta_instrument__exchange_id_symbol",
        ),
        Index(
            "ix_meta_instrument__market_id",
            "market_id",
        ),
        Index(
            "ix_meta_instrument__exchange_id",
            "exchange_id",
        ),
        Index(
            "ix_meta_instrument__instrument_type_is_active",
            "instrument_type",
            "is_active",
        ),
    )

    market_id: Mapped[int] = mapped_column(
        ForeignKey("meta_market.id", ondelete="RESTRICT"),
        nullable=False,
    )
    exchange_id: Mapped[int] = mapped_column(
        ForeignKey("meta_exchange.id", ondelete="RESTRICT"),
        nullable=False,
    )
    instrument_type: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    instrument_code: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default="CNY",
        server_default=text("'CNY'"),
    )
    list_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delist_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )