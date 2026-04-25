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


class TradingPaperFill(Base):
    __tablename__ = "trading_paper_fill"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    run_id = Column(
        BigInteger,
        ForeignKey("ops_run.id", name="fk_tpf_run"),
        nullable=False,
    )

    portfolio_id = Column(
        BigInteger,
        ForeignKey("trading_paper_portfolio.id", name="fk_tpf_portfolio"),
        nullable=False,
    )

    order_id = Column(
        BigInteger,
        ForeignKey("trading_paper_order.id", name="fk_tpf_order"),
        nullable=False,
    )

    instrument_id = Column(
        BigInteger,
        ForeignKey("meta_instrument.id", name="fk_tpf_instrument"),
        nullable=False,
    )

    fill_date = Column(Date, nullable=False)

    fill_price = Column(Numeric(24, 8), nullable=False)
    fill_quantity = Column(Numeric(24, 8), nullable=False)

    gross_amount = Column(Numeric(24, 8), nullable=False)
    commission_amount = Column(Numeric(24, 8), nullable=False, server_default="0")
    stamp_duty_amount = Column(Numeric(24, 8), nullable=False, server_default="0")
    transfer_fee_amount = Column(Numeric(24, 8), nullable=False, server_default="0")
    slippage_amount = Column(Numeric(24, 8), nullable=False, server_default="0")
    total_fee_amount = Column(Numeric(24, 8), nullable=False, server_default="0")

    net_amount = Column(Numeric(24, 8), nullable=False)
    cash_delta = Column(Numeric(24, 8), nullable=False)

    price_source = Column(String(64), nullable=False)
    fill_rule = Column(String(32), nullable=False, server_default="NEXT_OPEN")
    fill_status = Column(String(32), nullable=False, server_default="COMPLETED")

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        Index("idx_tpf_run_id", "run_id"),
        Index("idx_tpf_portfolio_date", "portfolio_id", "fill_date"),
        Index("idx_tpf_order_id", "order_id"),
    )