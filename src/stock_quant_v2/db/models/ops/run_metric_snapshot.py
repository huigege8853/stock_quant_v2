from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from stock_quant_v2.db.base import Base


class OpsRunMetricSnapshot(Base):
    __tablename__ = "ops_run_metric_snapshot"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    run_id = Column(BigInteger, nullable=False)

    metric_namespace = Column(String(64), nullable=False)
    metric_code = Column(String(128), nullable=False)
    metric_name = Column(String(255), nullable=True)

    metric_value_numeric = Column(Numeric(30, 10), nullable=True)
    metric_value_text = Column(Text, nullable=True)
    metric_value_json = Column(JSONB, nullable=True)

    unit = Column(String(32), nullable=True)

    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)

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

    sequence_no = Column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "metric_namespace",
            "metric_code",
            "dimension_type",
            "dimension_key",
            "sequence_no",
            name="uq_ops_run_metric__key",
        ),
        Index(
            "ix_ops_run_metric__run_ns",
            "run_id",
            "metric_namespace",
        ),
        Index(
            "ix_ops_run_metric__code",
            "metric_code",
        ),
        Index(
            "ix_ops_run_metric__period",
            "period_start",
            "period_end",
        ),
    )