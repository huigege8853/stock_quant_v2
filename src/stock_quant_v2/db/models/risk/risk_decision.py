from sqlalchemy import BigInteger, Column, Date, DateTime, ForeignKey, Index, JSON, Numeric, String, Text, text

from stock_quant_v2.db.base import Base


class RiskDecision(Base):
    __tablename__ = "risk_decision"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(BigInteger, ForeignKey("ops_run.id", name="fk_risk_decision_run"), nullable=False)
    portfolio_id = Column(BigInteger, ForeignKey("trading_paper_portfolio.id", name="fk_risk_decision_portfolio"), nullable=False)
    source_target_run_id = Column(BigInteger, ForeignKey("ops_run.id", name="fk_risk_decision_source_target_run"), nullable=False)
    adjusted_target_run_id = Column(BigInteger, ForeignKey("ops_run.id", name="fk_risk_decision_adjusted_target_run"), nullable=False)
    risk_profile_id = Column(BigInteger, ForeignKey("risk_profile.id", name="fk_risk_decision_profile"), nullable=False)
    risk_rule_id = Column(BigInteger, ForeignKey("risk_rule.id", name="fk_risk_decision_rule"), nullable=True)
    source_target_position_id = Column(BigInteger, ForeignKey("trading_paper_target_position.id", name="fk_risk_decision_source_target_position"), nullable=True)
    adjusted_target_position_id = Column(BigInteger, ForeignKey("trading_paper_target_position.id", name="fk_risk_decision_adjusted_target_position"), nullable=True)
    instrument_id = Column(BigInteger, ForeignKey("meta_instrument.id", name="fk_risk_decision_instrument"), nullable=True)
    decision_date = Column(Date, nullable=False)
    decision_type = Column(String(32), nullable=False)
    reason_code = Column(String(128), nullable=False)
    action_taken = Column(String(64), nullable=False)
    before_target_weight = Column(Numeric(18, 10), nullable=True)
    after_target_weight = Column(Numeric(18, 10), nullable=True)
    before_target_quantity = Column(Numeric(24, 8), nullable=True)
    after_target_quantity = Column(Numeric(24, 8), nullable=True)
    before_target_amount = Column(Numeric(24, 8), nullable=True)
    after_target_amount = Column(Numeric(24, 8), nullable=True)
    message = Column(Text, nullable=True)
    payload_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        Index("idx_risk_decision_run_id", "run_id"),
        Index("idx_risk_decision_portfolio_date", "portfolio_id", "decision_date"),
        Index("idx_risk_decision_source_target_run", "source_target_run_id"),
        Index("idx_risk_decision_adjusted_target_run", "adjusted_target_run_id"),
        Index("idx_risk_decision_decision_type", "decision_type"),
        Index("idx_risk_decision_reason_code", "reason_code"),
    )
