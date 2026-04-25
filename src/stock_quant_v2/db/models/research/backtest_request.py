from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from stock_quant_v2.db.base import Base


class ResearchBacktestRequest(Base):
    __tablename__ = "research_backtest_request"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    run_id = Column(BigInteger, nullable=False)

    request_code = Column(String(128), nullable=True)
    request_name = Column(String(255), nullable=True)

    strategy_version_id = Column(BigInteger, nullable=False)

    screen_request_id = Column(BigInteger, nullable=True)
    source_signal_run_id = Column(BigInteger, nullable=True)

    execution_assumption_profile_id = Column(BigInteger, nullable=False)
    benchmark_definition_id = Column(BigInteger, nullable=True)

    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)

    initial_cash = Column(
        Numeric(24, 6),
        nullable=False,
        server_default=text("10000000"),
    )

    rebalance_frequency = Column(String(32), nullable=True)
    signal_effective_mode = Column(String(64), nullable=True)

    portfolio_construction_mode = Column(String(64), nullable=True)
    portfolio_construction_payload = Column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    data_feed_payload = Column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    engine_code = Column(
        String(64),
        nullable=False,
        server_default="backtrader",
    )

    engine_payload = Column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    request_payload = Column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

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
        UniqueConstraint("run_id", name="uq_re_backtest_req__run"),
        Index(
            "ix_re_backtest_req__strategy_dates",
            "strategy_version_id",
            "start_date",
            "end_date",
        ),
        Index(
            "ix_re_backtest_req__screen_req",
            "screen_request_id",
        ),
        Index(
            "ix_re_backtest_req__signal_run",
            "source_signal_run_id",
        ),
        Index(
            "ix_re_backtest_req__exec_profile",
            "execution_assumption_profile_id",
        ),
        Index(
            "ix_re_backtest_req__benchmark",
            "benchmark_definition_id",
        ),
    )