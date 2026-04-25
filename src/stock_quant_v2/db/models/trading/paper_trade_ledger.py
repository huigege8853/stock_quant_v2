from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    Numeric,
    String,
    Text,
    text,
)

from stock_quant_v2.db.base import Base


class TradingPaperTradeLedger(Base):
    __tablename__ = "trading_paper_trade_ledger"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    run_id = Column(
        BigInteger,
        ForeignKey("ops_run.id", name="fk_tptl_run"),
        nullable=False,
    )

    portfolio_id = Column(
        BigInteger,
        ForeignKey("trading_paper_portfolio.id", name="fk_tptl_portfolio"),
        nullable=False,
    )

    event_date = Column(Date, nullable=False)
    event_type = Column(String(64), nullable=False)

    instrument_id = Column(
        BigInteger,
        ForeignKey("meta_instrument.id", name="fk_tptl_instrument"),
        nullable=True,
    )

    target_position_id = Column(
        BigInteger,
        ForeignKey("trading_paper_target_position.id", name="fk_tptl_target_position"),
        nullable=True,
    )

    order_id = Column(
        BigInteger,
        ForeignKey("trading_paper_order.id", name="fk_tptl_order"),
        nullable=True,
    )

    fill_id = Column(
        BigInteger,
        ForeignKey("trading_paper_fill.id", name="fk_tptl_fill"),
        nullable=True,
    )

    position_id = Column(
        BigInteger,
        ForeignKey("trading_paper_position.id", name="fk_tptl_position"),
        nullable=True,
    )

    portfolio_snapshot_id = Column(
        BigInteger,
        ForeignKey("trading_paper_portfolio_snapshot.id", name="fk_tptl_snapshot"),
        nullable=True,
    )

    quantity_delta = Column(Numeric(24, 8), nullable=True)
    cash_delta = Column(Numeric(24, 8), nullable=True)
    amount_delta = Column(Numeric(24, 8), nullable=True)

    reason_code = Column(String(128), nullable=True)
    message = Column(Text, nullable=True)
    payload_json = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        Index("idx_tptl_run_id", "run_id"),
        Index("idx_tptl_portfolio_date", "portfolio_id", "event_date"),
        Index("idx_tptl_event_type", "event_type"),
    )