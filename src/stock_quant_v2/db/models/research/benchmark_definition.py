from sqlalchemy import BigInteger, Boolean, Column, DateTime, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB

from stock_quant_v2.db.base import Base


class ResearchBenchmarkDefinition(Base):
    __tablename__ = "research_benchmark_definition"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    benchmark_code = Column(String(128), nullable=False)
    version_code = Column(
        String(64),
        nullable=False,
        server_default="v1",
    )
    benchmark_name = Column(String(255), nullable=False)
    benchmark_type = Column(String(64), nullable=False)

    market_code = Column(String(32), nullable=True)

    # M5.1 暂不加 FK，避免强依赖 core_market_index 是否存在。
    # 后续确认 benchmark 真实主表后，再单独补 FK migration。
    market_index_id = Column(BigInteger, nullable=True)

    currency = Column(String(16), nullable=True)
    rebalance_rule = Column(String(64), nullable=True)

    config_payload = Column(
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
            "benchmark_code",
            "version_code",
            name="uq_re_benchmark__code_ver",
        ),
        Index(
            "ix_re_benchmark__type_market",
            "benchmark_type",
            "market_code",
        ),
    )