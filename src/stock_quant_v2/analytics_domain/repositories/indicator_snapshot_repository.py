from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from stock_quant_v2.db.models.analytics.instrument_indicator_snapshot import AnalyticsInstrumentIndicatorSnapshot


class IndicatorSnapshotRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def delete_by_trade_date_and_codes(self, trade_date: date, indicator_codes: list[str]) -> int:
        stmt = delete(AnalyticsInstrumentIndicatorSnapshot).where(
            AnalyticsInstrumentIndicatorSnapshot.trade_date == trade_date,
            AnalyticsInstrumentIndicatorSnapshot.indicator_code.in_(indicator_codes),
        )
        result = self.session.execute(stmt)
        return int(result.rowcount or 0)

    def bulk_insert(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        self.session.bulk_insert_mappings(AnalyticsInstrumentIndicatorSnapshot, rows)

    def list_by_trade_date(self, trade_date: date) -> list[AnalyticsInstrumentIndicatorSnapshot]:
        stmt = select(AnalyticsInstrumentIndicatorSnapshot).where(
            AnalyticsInstrumentIndicatorSnapshot.trade_date == trade_date
        )
        return list(self.session.execute(stmt).scalars().all())