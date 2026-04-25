from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, String, text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from stock_quant_v2.db.base import Base
from stock_quant_v2.db.mixins import IdMixin, TimestampMixin


class MetaDataVersion(IdMixin, TimestampMixin, Base):
    __tablename__ = "meta_data_version"
    __table_args__ = (
        UniqueConstraint(
            "dataset_id",
            "version",
            name="uq_meta_data_version__dataset_id_version",
        ),
        Index(
            "ix_meta_data_version__dataset_id",
            "dataset_id",
        ),
        Index(
            "ix_meta_data_version__vendor_id",
            "vendor_id",
        ),
        Index(
            "ix_meta_data_version__run_id",
            "run_id",
        ),
        Index(
            "ix_meta_data_version__dataset_id_published_at",
            "dataset_id",
            "published_at",
        ),
    )

    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("meta_dataset.id", ondelete="RESTRICT"),
        nullable=False,
    )
    vendor_id: Mapped[int] = mapped_column(
        ForeignKey("meta_data_vendor.id", ondelete="RESTRICT"),
        nullable=False,
    )
    run_id: Mapped[int] = mapped_column(
        ForeignKey("ops_run.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    as_of_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    row_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )