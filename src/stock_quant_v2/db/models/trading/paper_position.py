from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)

from stock_quant_v2.db.base import Base


class TradingPaperPosition(Base):
    __tablename__ = "trading_paper_position"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    run_id = Column(
        BigInteger,
        ForeignKey("ops_run.id", name="fk_tppos_run"),
        nullable=False,
    )

    portfolio_id = Column(
        BigInteger,
        ForeignKey("trading_paper_portfolio.id", name="fk_tppos_portfolio"),
        nullable=False,
    )

    instrument_id = Column(
        BigInteger,
        ForeignKey("meta_instrument.id", name="fk_tppos_instrument"),
        nullable=False,
    )

    position_date = Column(Date, nullable=False)

    quantity = Column(Numeric(24, 8), nullable=False)
    available_quantity = Column(Numeric(24, 8), nullable=False, server_default="0")
    frozen_quantity = Column(Numeric(24, 8), nullable=False, server_default="0")

    avg_cost = Column(Numeric(24, 8), nullable=False)
    cost_amount = Column(Numeric(24, 8), nullable=False)

    market_price = Column(Numeric(24, 8), nullable=False)
    market_value = Column(Numeric(24, 8), nullable=False)

    unrealized_pnl = Column(Numeric(24, 8), nullable=False, server_default="0")
    realized_pnl = Column(Numeric(24, 8), nullable=False, server_default="0")
    total_pnl = Column(Numeric(24, 8), nullable=False, server_default="0")

    position_status = Column(String(32), nullable=False, server_default="OPEN")

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "portfolio_id",
            "position_date",
            "instrument_id",
            name="uq_tppos_run_portfolio_date_inst",
        ),
        Index("idx_tppos_portfolio_date", "portfolio_id", "position_date"),
        Index("idx_tppos_instrument_id", "instrument_id"),
    )