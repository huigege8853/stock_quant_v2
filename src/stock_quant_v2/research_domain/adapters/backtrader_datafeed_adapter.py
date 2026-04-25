from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from stock_quant_v2.db.models.research import ResearchBacktestRequest


class BacktraderDataFeedAdapter:
    """生成 backtrader data feed 的数据覆盖计划。

    M5.6 只检查 core_daily_bar 覆盖情况，不创建 backtrader feed。
    """

    def __init__(self, session: Session):
        self.session = session

    def _table_exists(self, table_name: str) -> bool:
        row = self.session.execute(
            text(
                """
                select 1
                from information_schema.tables
                where table_schema = 'public'
                  and table_name = :table_name
                limit 1
                """
            ),
            {"table_name": table_name},
        ).first()
        return row is not None

    def _columns(self, table_name: str) -> set[str]:
        rows = self.session.execute(
            text(
                """
                select column_name
                from information_schema.columns
                where table_schema = 'public'
                  and table_name = :table_name
                """
            ),
            {"table_name": table_name},
        ).scalars().all()
        return set(rows)

    def build_data_feed_plan(
        self,
        *,
        request: ResearchBacktestRequest,
        instrument_ids: list[int],
    ) -> dict[str, Any]:
        table_name = "core_daily_bar"

        if not self._table_exists(table_name):
            return {
                "adapter": "BacktraderDataFeedAdapter",
                "execution_enabled": False,
                "table_name": table_name,
                "table_exists": False,
                "status": "SKIPPED",
                "reason": "core_daily_bar table not found",
            }

        cols = self._columns(table_name)

        required_cols = {
            "instrument_id",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "volume",
        }

        available_required_cols = sorted(required_cols.intersection(cols))
        missing_required_cols = sorted(required_cols.difference(cols))

        unique_instrument_ids = sorted(set(instrument_ids))

        if not unique_instrument_ids:
            return {
                "adapter": "BacktraderDataFeedAdapter",
                "execution_enabled": False,
                "table_name": table_name,
                "table_exists": True,
                "status": "EMPTY",
                "instrument_count": 0,
                "bar_rows": 0,
                "missing_required_cols": missing_required_cols,
            }

        row = self.session.execute(
            text(
                """
                select
                    count(*) as bar_rows,
                    count(distinct instrument_id) as instrument_count,
                    count(distinct trade_date) as trade_day_count,
                    min(trade_date) as min_trade_date,
                    max(trade_date) as max_trade_date
                from core_daily_bar
                where trade_date >= :start_date
                  and trade_date <= :end_date
                  and instrument_id = any(:instrument_ids)
                """
            ),
            {
                "start_date": request.start_date,
                "end_date": request.end_date,
                "instrument_ids": unique_instrument_ids,
            },
        ).mappings().one()

        return {
            "adapter": "BacktraderDataFeedAdapter",
            "execution_enabled": False,
            "table_name": table_name,
            "table_exists": True,
            "status": "READY_FOR_ADAPTER"
            if row["bar_rows"] and not missing_required_cols
            else "NEEDS_REVIEW",
            "start_date": str(request.start_date),
            "end_date": str(request.end_date),
            "requested_instrument_count": len(unique_instrument_ids),
            "covered_instrument_count": int(row["instrument_count"] or 0),
            "bar_rows": int(row["bar_rows"] or 0),
            "trade_day_count": int(row["trade_day_count"] or 0),
            "min_trade_date": str(row["min_trade_date"])
            if row["min_trade_date"] is not None
            else None,
            "max_trade_date": str(row["max_trade_date"])
            if row["max_trade_date"] is not None
            else None,
            "available_required_cols": available_required_cols,
            "missing_required_cols": missing_required_cols,
            "note": "M5.6 plan only; no backtrader feed object created",
        }