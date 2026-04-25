from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from stock_quant_v2.db.models.analytics.label_snapshot import AnalyticsLabelSnapshot


class LabelSnapshotRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def delete_by_anchor_date_and_codes(self, anchor_date: date, label_codes: list[str]) -> int:
        stmt = delete(AnalyticsLabelSnapshot).where(
            AnalyticsLabelSnapshot.anchor_date == anchor_date,
            AnalyticsLabelSnapshot.label_code.in_(label_codes),
        )
        result = self.session.execute(stmt)
        return int(result.rowcount or 0)

    def bulk_insert(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        self.session.bulk_insert_mappings(AnalyticsLabelSnapshot, rows)

    def list_by_anchor_date(self, anchor_date: date) -> list[AnalyticsLabelSnapshot]:
        stmt = select(AnalyticsLabelSnapshot).where(AnalyticsLabelSnapshot.anchor_date == anchor_date)
        return list(self.session.execute(stmt).scalars().all())