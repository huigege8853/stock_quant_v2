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
from sqlalchemy import Integer

class TradingPaperTargetPosition(Base):
    __tablename__ = "trading_paper_target_position"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    run_id = Column(
        BigInteger,
        ForeignKey("ops_run.id", name="fk_tpt_run"),
        nullable=False,
    )

    portfolio_id = Column(
        BigInteger,
        ForeignKey("trading_paper_portfolio.id", name="fk_tpt_portfolio"),
        nullable=False,
    )

    source_signal_run_id = Column(
        BigInteger,
        ForeignKey("ops_run.id", name="fk_tpt_signal_run"),
        nullable=False,
    )

    source_screen_request_id = Column(
        BigInteger,
        ForeignKey("research_screen_request.id", name="fk_tpt_screen_request"),
        nullable=True,
    )

    strategy_signal_id = Column(
        BigInteger,
        ForeignKey("strategy_signal.id", name="fk_tpt_strategy_signal"),
        nullable=True,
    )

    as_of_date = Column(Date, nullable=False)
    effective_date = Column(Date, nullable=False)

    instrument_id = Column(
        BigInteger,
        ForeignKey("meta_instrument.id", name="fk_tpt_instrument"),
        nullable=False,
    )

    target_side = Column(String(16), nullable=False)
    target_weight = Column(Numeric(18, 10), nullable=False)
    target_amount = Column(Numeric(24, 8), nullable=True)
    target_quantity = Column(Numeric(24, 8), nullable=True)

    rank_no = Column(Integer, nullable=True)
    score = Column(Numeric(18, 10), nullable=True)
    reason_code = Column(String(128), nullable=True)

    target_source = Column(String(64), nullable=False, server_default="SCREEN_RESULT")
    construction_mode = Column(String(64), nullable=False)

    status = Column(String(32), nullable=False, server_default="PENDING")
    status_reason = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "portfolio_id",
            "effective_date",
            "instrument_id",
            name="uq_tpt_run_portfolio_date_inst",
        ),
        Index("idx_tpt_portfolio_date", "portfolio_id", "effective_date"),
        Index("idx_tpt_signal_run_id", "source_signal_run_id"),
        Index("idx_tpt_screen_request_id", "source_screen_request_id"),
    )