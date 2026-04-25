from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from stock_quant_v2.db.base import Base


class OpsRunArtifact(Base):
    __tablename__ = "ops_run_artifact"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    run_id = Column(BigInteger, nullable=False)

    artifact_type = Column(String(64), nullable=False)
    artifact_code = Column(String(128), nullable=False)
    artifact_name = Column(String(255), nullable=True)

    storage_backend = Column(String(64), nullable=False)
    uri = Column(Text, nullable=False)

    mime_type = Column(String(128), nullable=True)
    file_size_bytes = Column(BigInteger, nullable=True)
    checksum_sha256 = Column(String(128), nullable=True)

    payload_schema = Column(JSONB, nullable=True)

    artifact_metadata = Column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "artifact_code",
            name="uq_ops_run_artifact__code",
        ),
        Index(
            "ix_ops_run_artifact__run",
            "run_id",
        ),
        Index(
            "ix_ops_run_artifact__type",
            "artifact_type",
        ),
    )