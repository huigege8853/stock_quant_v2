from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base


class FundamentalSnapshot(Base):
    __tablename__ = "fundamental_snapshot"

    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "trade_date",
            "snapshot_type",
            name="uq_fundamental_snapshot_inst_date_type",
        ),
        Index("ix_fundamental_snapshot_trade_date", "trade_date"),
        Index("ix_fundamental_snapshot_snapshot_type", "snapshot_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    instrument_id: Mapped[int] = mapped_column(
        ForeignKey("meta_instrument.id"),
        nullable=False,
    )
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    snapshot_type: Mapped[str] = mapped_column(String(32), nullable=False)

    pe_ttm: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    pb: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    ps_ttm: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    dv_ttm: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    total_mv: Mapped[float | None] = mapped_column(Numeric(24, 6), nullable=True)
    circ_mv: Mapped[float | None] = mapped_column(Numeric(24, 6), nullable=True)

    roe: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    roa: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    gross_margin: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    net_profit_yoy: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)

    report_period: Mapped[date | None] = mapped_column(Date, nullable=True)
    announcement_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    source_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    data_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("meta_data_version.id"),
        nullable=True,
    )