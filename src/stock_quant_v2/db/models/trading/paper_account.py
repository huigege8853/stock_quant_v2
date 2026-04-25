from sqlalchemy import BigInteger, Column, DateTime, Numeric, String, text

from stock_quant_v2.db.base import Base


class TradingPaperAccount(Base):
    __tablename__ = "trading_paper_account"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    account_code = Column(String(64), nullable=False, unique=True)
    account_name = Column(String(255), nullable=False)

    account_type = Column(String(32), nullable=False, server_default="PAPER")
    market_code = Column(String(32), nullable=False, server_default="CN_A")
    base_currency = Column(String(16), nullable=False, server_default="CNY")

    initial_cash = Column(Numeric(24, 8), nullable=False)

    status = Column(String(32), nullable=False, server_default="ACTIVE")

    opened_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))