from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    UniqueConstraint,
    text,
)

from stock_quant_v2.db.base import Base


class TradingPaperPortfolioSnapshot(Base):
    __tablename__ = "trading_paper_portfolio_snapshot"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    run_id = Column(
        BigInteger,
        ForeignKey("ops_run.id", name="fk_tps_run"),
        nullable=False,
    )

    portfolio_id = Column(
        BigInteger,
        ForeignKey("trading_paper_portfolio.id", name="fk_tps_portfolio"),
        nullable=False,
    )

    snapshot_date = Column(Date, nullable=False)

    cash_balance = Column(Numeric(24, 8), nullable=False)
    market_value = Column(Numeric(24, 8), nullable=False)
    total_equity = Column(Numeric(24, 8), nullable=False)

    gross_exposure = Column(Numeric(24, 8), nullable=False)
    net_exposure = Column(Numeric(24, 8), nullable=False)

    holding_count = Column(Integer, nullable=False)

    daily_pnl = Column(Numeric(24, 8), nullable=True)
    cumulative_pnl = Column(Numeric(24, 8), nullable=True)
    daily_return = Column(Numeric(18, 10), nullable=True)
    cumulative_return = Column(Numeric(18, 10), nullable=True)

    turnover_amount = Column(Numeric(24, 8), nullable=True)
    turnover_rate = Column(Numeric(18, 10), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "portfolio_id",
            "snapshot_date",
            name="uq_tps_run_portfolio_date",
        ),
        Index("idx_tps_portfolio_date", "portfolio_id", "snapshot_date"),
    )