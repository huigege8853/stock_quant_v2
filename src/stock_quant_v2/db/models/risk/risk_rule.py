from sqlalchemy import BigInteger, Boolean, Column, DateTime, Index, JSON, String, Text, UniqueConstraint, text

from stock_quant_v2.db.base import Base


class RiskRule(Base):
    __tablename__ = "risk_rule"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    rule_code = Column(String(64), nullable=False)
    rule_name = Column(String(255), nullable=False)
    rule_type = Column(String(64), nullable=False)
    default_action = Column(String(32), nullable=False, server_default="WARN")
    default_params_json = Column(JSON, nullable=True)
    enabled = Column(Boolean, nullable=False, server_default=text("true"))
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint("rule_code", name="uq_risk_rule_code"),
        Index("idx_risk_rule_type", "rule_type"),
    )
