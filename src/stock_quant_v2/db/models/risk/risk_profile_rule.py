from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, text

from stock_quant_v2.db.base import Base


class RiskProfileRule(Base):
    __tablename__ = "risk_profile_rule"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    profile_id = Column(BigInteger, ForeignKey("risk_profile.id", name="fk_risk_profile_rule_profile"), nullable=False)
    rule_id = Column(BigInteger, ForeignKey("risk_rule.id", name="fk_risk_profile_rule_rule"), nullable=False)
    priority = Column(Integer, nullable=False, server_default="100")
    action = Column(String(32), nullable=False, server_default="WARN")
    params_json = Column(JSON, nullable=True)
    enabled = Column(Boolean, nullable=False, server_default=text("true"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint("profile_id", "rule_id", name="uq_risk_profile_rule_profile_rule"),
        Index("idx_risk_profile_rule_profile_priority", "profile_id", "priority"),
    )
