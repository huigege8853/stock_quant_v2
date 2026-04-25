from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from stock_quant_v2.db.models.meta.data_vendor import MetaDataVendor
from stock_quant_v2.db.models.meta.data_version import MetaDataVersion
from stock_quant_v2.db.models.meta.dataset import MetaDataset


class DataVersionRepository:
    def get_dataset_id(self, session: Session, dataset_code: str) -> int | None:
        stmt = select(MetaDataset.id).where(MetaDataset.dataset_code == dataset_code)
        return session.execute(stmt).scalar_one_or_none()

    def get_vendor_id(self, session: Session, vendor_code: str) -> int | None:
        stmt = select(MetaDataVendor.id).where(MetaDataVendor.vendor_code == vendor_code)
        return session.execute(stmt).scalar_one_or_none()

    def get_latest_published_version_id(
        self,
        session: Session,
        dataset_code: str,
        vendor_code: str | None = None,
    ) -> int | None:
        dataset_id = self.get_dataset_id(session, dataset_code)
        if dataset_id is None:
            return None

        stmt = select(MetaDataVersion.id).where(
            MetaDataVersion.dataset_id == dataset_id,
            MetaDataVersion.status == "PUBLISHED",
        )

        if vendor_code is not None:
            vendor_id = self.get_vendor_id(session, vendor_code)
            if vendor_id is None:
                return None
            stmt = stmt.where(MetaDataVersion.vendor_id == vendor_id)

        stmt = stmt.order_by(desc(MetaDataVersion.published_at), desc(MetaDataVersion.id))
        return session.execute(stmt).scalar_one_or_none()

    def create_data_version(
        self,
        session: Session,
        dataset_code: str,
        vendor_code: str,
        run_id: int,
        version: str,
        as_of_date: date | None = None,
        content_hash: str | None = None,
        row_count: int | None = None,
        status: str = "DRAFT",
        published: bool = False,
    ) -> MetaDataVersion:
        dataset_id = self.get_dataset_id(session, dataset_code)
        if dataset_id is None:
            raise ValueError(f"dataset_code not found: {dataset_code}")

        vendor_id = self.get_vendor_id(session, vendor_code)
        if vendor_id is None:
            raise ValueError(f"vendor_code not found: {vendor_code}")

        obj = MetaDataVersion(
            dataset_id=dataset_id,
            vendor_id=vendor_id,
            run_id=run_id,
            version=version,
            as_of_date=as_of_date,
            content_hash=content_hash,
            row_count=row_count,
            status=status,
            published_at=datetime.now(timezone.utc) if published else None,
        )
        session.add(obj)
        session.flush()
        return obj

    def mark_published(
        self,
        session: Session,
        data_version: MetaDataVersion,
        row_count: int | None = None,
        content_hash: str | None = None,
    ) -> None:
        data_version.status = "PUBLISHED"
        data_version.row_count = row_count
        data_version.content_hash = content_hash
        data_version.published_at = datetime.now(timezone.utc)
        session.flush()