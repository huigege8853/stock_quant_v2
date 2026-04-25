from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from stock_quant_v2.db.models.analytics.instrument_factor_snapshot import AnalyticsInstrumentFactorSnapshot


class FactorSnapshotRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def delete_by_trade_date_and_codes(self, trade_date: date, factor_codes: list[str]) -> int:
        stmt = delete(AnalyticsInstrumentFactorSnapshot).where(
            AnalyticsInstrumentFactorSnapshot.trade_date == trade_date,
            AnalyticsInstrumentFactorSnapshot.factor_code.in_(factor_codes),
        )
        result = self.session.execute(stmt)
        return int(result.rowcount or 0)

    def bulk_insert(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        self.session.bulk_insert_mappings(AnalyticsInstrumentFactorSnapshot, rows)

    def list_by_trade_date(self, trade_date: date) -> list[AnalyticsInstrumentFactorSnapshot]:
        stmt = select(AnalyticsInstrumentFactorSnapshot).where(
            AnalyticsInstrumentFactorSnapshot.trade_date == trade_date
        )
        return list(self.session.execute(stmt).scalars().all())