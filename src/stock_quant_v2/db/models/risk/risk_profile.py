from sqlalchemy import BigInteger, Boolean, Column, DateTime, Index, String, Text, UniqueConstraint, text

from stock_quant_v2.db.base import Base


class RiskProfile(Base):
    __tablename__ = "risk_profile"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    profile_code = Column(String(64), nullable=False)
    profile_name = Column(String(255), nullable=False)
    profile_type = Column(String(64), nullable=False, server_default="PAPER_TRADING")
    market_code = Column(String(32), nullable=False, server_default="CN_A")
    enabled = Column(Boolean, nullable=False, server_default=text("true"))
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint("profile_code", name="uq_risk_profile_code"),
        Index("idx_risk_profile_type", "profile_type"),
    )
