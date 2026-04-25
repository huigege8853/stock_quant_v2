from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base
from stock_quant_v2.db.mixins import IdMixin


class InstrumentTag(IdMixin, Base):
    __tablename__ = "instrument_tag"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "tag_id",
            "effective_from",
            name="uq_instrument_tag_inst_tag_from",
        ),
    )

    instrument_id: Mapped[int] = mapped_column(
        ForeignKey("meta_instrument.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tag.id", ondelete="RESTRICT"),
        nullable=False,
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)