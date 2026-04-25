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


class ResearchScreenRequest(Base):
    __tablename__ = "research_screen_request"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    run_id = Column(BigInteger, nullable=False)

    request_code = Column(String(128), nullable=True)
    request_name = Column(String(255), nullable=True)

    strategy_version_id = Column(BigInteger, nullable=False)

    signal_lookup_mode = Column(String(32), nullable=False)
    source_signal_run_id = Column(BigInteger, nullable=True)

    as_of_date = Column(Date, nullable=False)
    effective_date = Column(Date, nullable=True)

    max_count = Column(Integer, nullable=True)
    min_score = Column(Numeric(20, 8), nullable=True)

    include_reason_codes = Column(JSONB, nullable=True)
    exclude_reason_codes = Column(JSONB, nullable=True)
    universe_filter = Column(JSONB, nullable=True)
    signal_filter = Column(JSONB, nullable=True)
    parameter_values = Column(JSONB, nullable=True)

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
        UniqueConstraint("run_id", name="uq_re_screen_req__run"),
        Index(
            "ix_re_screen_req__strategy_date",
            "strategy_version_id",
            "as_of_date",
        ),
        Index(
            "ix_re_screen_req__signal_run",
            "source_signal_run_id",
        ),
        Index(
            "ix_re_screen_req__effective_date",
            "effective_date",
        ),
    )