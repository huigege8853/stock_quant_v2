from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from stock_quant_v2.db.models.analytics.feature_snapshot import AnalyticsFeatureSnapshot


class FeatureSnapshotRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def delete_by_trade_date_and_feature_set(self, trade_date: date, feature_set_code: str, feature_set_version: str) -> int:
        stmt = delete(AnalyticsFeatureSnapshot).where(
            AnalyticsFeatureSnapshot.trade_date == trade_date,
            AnalyticsFeatureSnapshot.feature_set_code == feature_set_code,
            AnalyticsFeatureSnapshot.feature_set_version == feature_set_version,
        )
        result = self.session.execute(stmt)
        return int(result.rowcount or 0)

    def bulk_insert(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        self.session.bulk_insert_mappings(AnalyticsFeatureSnapshot, rows)

    def list_by_trade_date(self, trade_date: date) -> list[AnalyticsFeatureSnapshot]:
        stmt = select(AnalyticsFeatureSnapshot).where(AnalyticsFeatureSnapshot.trade_date == trade_date)
        return list(self.session.execute(stmt).scalars().all())