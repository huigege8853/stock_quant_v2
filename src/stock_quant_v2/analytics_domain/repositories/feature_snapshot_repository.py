from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import delete, select, text
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


    def delete_by_trade_date_feature_set_and_codes(
        self,
        trade_date: date,
        feature_set_code: str,
        feature_set_version: str,
        feature_codes: list[str],
    ) -> int:
        if not feature_codes:
            return 0
        stmt = delete(AnalyticsFeatureSnapshot).where(
            AnalyticsFeatureSnapshot.trade_date == trade_date,
            AnalyticsFeatureSnapshot.feature_set_code == feature_set_code,
            AnalyticsFeatureSnapshot.feature_set_version == feature_set_version,
            AnalyticsFeatureSnapshot.feature_code.in_(feature_codes),
        )
        result = self.session.execute(stmt)
        return int(result.rowcount or 0)

    def bulk_insert(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        self.session.execute(
            text(
                """
                insert into analytics_feature_snapshot (
                    trade_date,
                    instrument_id,
                    feature_code,
                    feature_set_code,
                    feature_set_version,
                    feature_value_numeric,
                    feature_value_text,
                    is_imputed,
                    impute_method,
                    scaling_applied,
                    sample_status,
                    run_id
                ) values (
                    :trade_date,
                    :instrument_id,
                    :feature_code,
                    :feature_set_code,
                    :feature_set_version,
                    :feature_value_numeric,
                    :feature_value_text,
                    :is_imputed,
                    :impute_method,
                    :scaling_applied,
                    :sample_status,
                    :run_id
                )
                """
            ),
            rows,
        )

    def list_by_trade_date(self, trade_date: date) -> list[AnalyticsFeatureSnapshot]:
        stmt = select(AnalyticsFeatureSnapshot).where(AnalyticsFeatureSnapshot.trade_date == trade_date)
        return list(self.session.execute(stmt).scalars().all())