from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from stock_quant_v2.db.base import Base


class OpsRunSeriesSnapshot(Base):
    __tablename__ = "ops_run_series_snapshot"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    run_id = Column(BigInteger, nullable=False)

    series_namespace = Column(String(64), nullable=False)
    series_code = Column(String(128), nullable=False)
    trade_date = Column(Date, nullable=False)

    instrument_id = Column(BigInteger, nullable=True)

    dimension_type = Column(
        String(64),
        nullable=False,
        server_default="PORTFOLIO",
    )
    dimension_key = Column(
        String(128),
        nullable=False,
        server_default="ALL",
    )

    value_numeric = Column(Numeric(30, 10), nullable=True)
    value_text = Column(Text, nullable=True)
    value_json = Column(JSONB, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "series_namespace",
            "series_code",
            "trade_date",
            "dimension_type",
            "dimension_key",
            name="uq_ops_run_series__key",
        ),
        Index(
            "ix_ops_run_series__run_ns",
            "run_id",
            "series_namespace",
        ),
        Index(
            "ix_ops_run_series__code_date",
            "series_code",
            "trade_date",
        ),
        Index(
            "ix_ops_run_series__instrument",
            "instrument_id",
        ),
    )