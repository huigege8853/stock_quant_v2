from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    text,
)

from stock_quant_v2.db.base import Base


class TradingPaperOrder(Base):
    __tablename__ = "trading_paper_order"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    run_id = Column(
        BigInteger,
        ForeignKey("ops_run.id", name="fk_tpo_run"),
        nullable=False,
    )

    portfolio_id = Column(
        BigInteger,
        ForeignKey("trading_paper_portfolio.id", name="fk_tpo_portfolio"),
        nullable=False,
    )

    target_position_id = Column(
        BigInteger,
        ForeignKey("trading_paper_target_position.id", name="fk_tpo_target_position"),
        nullable=True,
    )

    instrument_id = Column(
        BigInteger,
        ForeignKey("meta_instrument.id", name="fk_tpo_instrument"),
        nullable=False,
    )

    order_date = Column(Date, nullable=False)
    effective_date = Column(Date, nullable=False)

    order_side = Column(String(16), nullable=False)
    order_type = Column(String(32), nullable=False, server_default="MARKET")
    price_fill_rule = Column(String(32), nullable=False, server_default="NEXT_OPEN")
    time_in_force = Column(String(16), nullable=False, server_default="DAY")

    target_quantity = Column(Numeric(24, 8), nullable=True)
    order_quantity = Column(Numeric(24, 8), nullable=False)

    estimated_price = Column(Numeric(24, 8), nullable=False)
    estimated_gross_amount = Column(Numeric(24, 8), nullable=False)
    estimated_fee = Column(Numeric(24, 8), nullable=False)
    estimated_net_amount = Column(Numeric(24, 8), nullable=False)

    status = Column(String(32), nullable=False, server_default="NEW")
    reject_reason = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        Index("idx_tpo_run_id", "run_id"),
        Index("idx_tpo_portfolio_date", "portfolio_id", "effective_date"),
        Index("idx_tpo_target_position_id", "target_position_id"),
    )