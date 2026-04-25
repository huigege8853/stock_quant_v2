from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from stock_quant_v2.db.base import Base


class ResearchBacktestResult(Base):
    __tablename__ = "research_backtest_result"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    run_id = Column(BigInteger, nullable=False)
    backtest_request_id = Column(BigInteger, nullable=False)

    result_status = Column(String(32), nullable=False)

    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    trading_days = Column(Integer, nullable=True)

    initial_cash = Column(Numeric(24, 6), nullable=True)
    final_equity = Column(Numeric(24, 6), nullable=True)

    total_return = Column(Numeric(20, 8), nullable=True)
    annual_return = Column(Numeric(20, 8), nullable=True)
    benchmark_return = Column(Numeric(20, 8), nullable=True)
    excess_return = Column(Numeric(20, 8), nullable=True)

    max_drawdown = Column(Numeric(20, 8), nullable=True)
    sharpe_ratio = Column(Numeric(20, 8), nullable=True)
    volatility = Column(Numeric(20, 8), nullable=True)
    win_rate = Column(Numeric(20, 8), nullable=True)
    turnover_avg = Column(Numeric(20, 8), nullable=True)

    order_count = Column(Integer, nullable=True)
    trade_count = Column(Integer, nullable=True)

    result_summary = Column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    completed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        UniqueConstraint("run_id", name="uq_re_backtest_result__run"),
        Index(
            "ix_re_backtest_result__request",
            "backtest_request_id",
        ),
        Index(
            "ix_re_backtest_result__dates",
            "start_date",
            "end_date",
        ),
    )