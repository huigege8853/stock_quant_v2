from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from stock_quant_v2.db.models.core.instrument_tag import InstrumentTag
from stock_quant_v2.db.models.core.tag import Tag


class TagRepository:
    def validate_data_version_id(self, session: Session, data_version_id: int) -> None:
        exists = session.execute(
            text("SELECT 1 FROM meta_data_version WHERE id = :id"),
            {"id": data_version_id},
        ).scalar_one_or_none()
        if exists is None:
            raise ValueError(
                f"data_version_id={data_version_id} does not exist in meta_data_version"
            )

    def upsert_tag(self, session: Session, payload: dict) -> Tag:
        stmt = insert(Tag).values(**payload)

        update_columns = {
            "tag_name": stmt.excluded.tag_name,
            "taxonomy_source": stmt.excluded.taxonomy_source,
            "is_active": stmt.excluded.is_active,
        }

        stmt = stmt.on_conflict_do_update(
            constraint="uq_tag_type_code",
            set_=update_columns,
        ).returning(Tag)

        return session.execute(stmt).scalar_one()

    def get_tag_id(self, session: Session, tag_type: str, tag_code: str) -> int | None:
        stmt = select(Tag.id).where(
            Tag.tag_type == tag_type,
            Tag.tag_code == tag_code,
        )
        return session.execute(stmt).scalar_one_or_none()

    def upsert_instrument_tag(self, session: Session, payload: dict) -> InstrumentTag:
        stmt = insert(InstrumentTag).values(**payload)

        update_columns = {
            "effective_to": stmt.excluded.effective_to,
            "source_provider": stmt.excluded.source_provider,
            "confidence": stmt.excluded.confidence,
        }

        stmt = stmt.on_conflict_do_update(
            constraint="uq_instrument_tag_inst_tag_from",
            set_=update_columns,
        ).returning(InstrumentTag)

        return session.execute(stmt).scalar_one()