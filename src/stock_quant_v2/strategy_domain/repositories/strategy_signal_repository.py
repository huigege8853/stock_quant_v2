from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_quant_v2.db.models.analytics.feature_snapshot import AnalyticsFeatureSnapshot
from stock_quant_v2.db.models.strategy.strategy_signal import StrategySignal


class StrategySignalRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def load_feature_rows(
        self,
        *,
        trade_date: date,
        feature_set_code: str,
        feature_set_version: str,
        feature_codes: list[str],
    ) -> list[tuple[int, str, Decimal | None]]:
        return list(
            self._session.execute(
                select(
                    AnalyticsFeatureSnapshot.instrument_id,
                    AnalyticsFeatureSnapshot.feature_code,
                    AnalyticsFeatureSnapshot.feature_value_numeric,
                ).where(
                    AnalyticsFeatureSnapshot.trade_date == trade_date,
                    AnalyticsFeatureSnapshot.feature_set_code == feature_set_code,
                    AnalyticsFeatureSnapshot.feature_set_version == feature_set_version,
                    AnalyticsFeatureSnapshot.feature_code.in_(feature_codes),
                    AnalyticsFeatureSnapshot.sample_status == "ready",
                )
            ).all()
        )

    def create_many(self, rows: list[StrategySignal]) -> None:
        self._session.add_all(rows)
        self._session.flush()