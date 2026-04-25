from sqlalchemy import BigInteger, Boolean, Column, DateTime, Index, Integer, Numeric, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB

from stock_quant_v2.db.base import Base


class ResearchExecutionAssumptionProfile(Base):
    __tablename__ = "research_execution_assumption_profile"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    profile_code = Column(String(128), nullable=False)
    version_code = Column(String(64), nullable=False)
    profile_name = Column(String(255), nullable=False)

    market_code = Column(String(32), nullable=False)
    asset_class = Column(String(32), nullable=False)
    frequency = Column(String(32), nullable=False)

    commission_model = Column(String(64), nullable=True)
    commission_rate = Column(Numeric(20, 8), nullable=True)
    min_commission = Column(Numeric(20, 8), nullable=True)
    stamp_duty_rate = Column(Numeric(20, 8), nullable=True)
    transfer_fee_rate = Column(Numeric(20, 8), nullable=True)

    slippage_model = Column(String(64), nullable=True)
    slippage_bps = Column(Numeric(20, 8), nullable=True)

    price_fill_rule = Column(String(64), nullable=True)
    volume_fill_rule = Column(String(64), nullable=True)
    t_plus_rule = Column(String(32), nullable=True)
    lot_size = Column(Integer, nullable=True)
    allow_fractional_share = Column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )

    limit_up_down_rule = Column(String(64), nullable=True)
    suspend_rule = Column(String(64), nullable=True)
    cash_rule = Column(String(64), nullable=True)

    assumption_payload = Column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    is_active = Column(
        Boolean,
        nullable=False,
        server_default=text("true"),
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
        UniqueConstraint(
            "profile_code",
            "version_code",
            name="uq_re_exec_profile__code_ver",
        ),
        Index(
            "ix_re_exec_profile__market",
            "market_code",
            "asset_class",
            "frequency",
        ),
    )