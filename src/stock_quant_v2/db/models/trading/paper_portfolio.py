from sqlalchemy import (
    BigInteger,
    Boolean,
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
from sqlalchemy import Integer

class TradingPaperPortfolio(Base):
    __tablename__ = "trading_paper_portfolio"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    account_id = Column(
        BigInteger,
        ForeignKey("trading_paper_account.id", name="fk_tpp_account"),
        nullable=False,
    )

    portfolio_code = Column(String(64), nullable=False, unique=True)
    portfolio_name = Column(String(255), nullable=False)

    strategy_version_id = Column(
        BigInteger,
        ForeignKey("strategy_version.id", name="fk_tpp_strategy_version"),
        nullable=False,
    )

    execution_assumption_profile_id = Column(
        BigInteger,
        ForeignKey(
            "research_execution_assumption_profile.id",
            name="fk_tpp_exec_profile",
        ),
        nullable=False,
    )

    source_signal_run_id = Column(
        BigInteger,
        ForeignKey("ops_run.id", name="fk_tpp_signal_run"),
        nullable=True,
    )

    source_screen_request_id = Column(
        BigInteger,
        ForeignKey("research_screen_request.id", name="fk_tpp_screen_request"),
        nullable=True,
    )

    portfolio_construction_mode = Column(String(64), nullable=False)
    rebalance_frequency = Column(String(32), nullable=False, server_default="DAILY")
    max_position_count = Column(Integer, nullable=False, server_default="30")
    long_only = Column(Boolean, nullable=False, server_default=text("true"))

    initial_cash = Column(Numeric(24, 8), nullable=False)

    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)

    status = Column(String(32), nullable=False, server_default="CREATED")

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


Index("idx_tpp_account_id", TradingPaperPortfolio.account_id)
Index("idx_tpp_strategy_version_id", TradingPaperPortfolio.strategy_version_id)
Index("idx_tpp_signal_run_id", TradingPaperPortfolio.source_signal_run_id)