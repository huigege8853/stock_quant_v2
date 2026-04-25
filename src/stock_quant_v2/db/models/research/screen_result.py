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


class ResearchScreenResult(Base):
    __tablename__ = "research_screen_result"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    run_id = Column(BigInteger, nullable=False)
    screen_request_id = Column(BigInteger, nullable=False)
    signal_run_id = Column(BigInteger, nullable=True)

    as_of_date = Column(Date, nullable=False)
    effective_date = Column(Date, nullable=True)

    eligible_universe_size = Column(Integer, nullable=True)
    selected_count = Column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

    score_min = Column(Numeric(20, 8), nullable=True)
    score_max = Column(Numeric(20, 8), nullable=True)
    score_avg = Column(Numeric(20, 8), nullable=True)

    result_status = Column(String(32), nullable=False)

    result_summary = Column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    artifact_run_id = Column(BigInteger, nullable=True)

    completed_at = Column(DateTime(timezone=True), nullable=True)

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
        UniqueConstraint("run_id", name="uq_re_screen_result__run"),
        Index(
            "ix_re_screen_result__request",
            "screen_request_id",
        ),
        Index(
            "ix_re_screen_result__signal_run",
            "signal_run_id",
        ),
        Index(
            "ix_re_screen_result__dates",
            "as_of_date",
            "effective_date",
        ),
    )