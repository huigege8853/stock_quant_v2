from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session


class AnalyticsUniverseService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_trade_date_instruments(self, trade_date: date) -> list[int]:
        sql = text(
            """
            SELECT DISTINCT instrument_id
            FROM core_daily_bar
            WHERE trade_date = :trade_date
            ORDER BY instrument_id
            """
        )
        rows = self.session.execute(sql, {"trade_date": trade_date}).mappings().all()
        return [int(row["instrument_id"]) for row in rows]