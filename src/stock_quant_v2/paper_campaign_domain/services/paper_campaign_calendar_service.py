from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from stock_quant_v2.paper_campaign_domain.dto.paper_campaign_models import CampaignSignalSource


class PaperCampaignCalendarService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def latest_completed_trade_date(self) -> date:
        value = self.session.execute(text("select max(trade_date) from core_daily_bar")).scalar_one_or_none()
        coerced = self._coerce_date(value)
        if coerced is None:
            raise RuntimeError("core_daily_bar is empty; cannot resolve latest completed trade date")
        return coerced

    def is_open_trade_date(self, trade_date: date) -> bool:
        value = self.session.execute(
            text(
                """
                select 1
                from meta_trading_calendar
                where trade_date = :trade_date
                  and is_open = true
                limit 1
                """
            ),
            {"trade_date": trade_date},
        ).scalar_one_or_none()
        if value is not None:
            return True

        # Fallback: if market calendar is incomplete but bars exist for the date,
        # treat it as tradable for campaign replay purposes.
        return self.has_daily_bar(trade_date)

    def has_daily_bar(self, trade_date: date) -> bool:
        value = self.session.execute(
            text("select 1 from core_daily_bar where trade_date = :trade_date limit 1"),
            {"trade_date": trade_date},
        ).scalar_one_or_none()
        return value is not None

    def resolve_strategy_version_id(self, strategy_code: str, version_code: str) -> int:
        value = self.session.execute(
            text(
                """
                select sv.id
                from strategy_version sv
                join strategy_definition sd on sd.id = sv.strategy_definition_id
                where sd.strategy_code = :strategy_code
                  and sv.version_code = :version_code
                order by sv.id desc
                limit 1
                """
            ),
            {"strategy_code": strategy_code, "version_code": version_code},
        ).scalar_one_or_none()
        if value is None:
            raise RuntimeError(f"strategy version not found: {strategy_code}:{version_code}")
        return int(value)

    def resolve_signal_source(
        self,
        *,
        strategy_version_id: int,
        trade_date: date,
    ) -> CampaignSignalSource:
        row = self.session.execute(
            text(
                """
                select
                    run_id,
                    max(as_of_date) as as_of_date,
                    max(effective_date) as effective_date
                from strategy_signal
                where strategy_version_id = :strategy_version_id
                  and effective_date <= :trade_date
                group by run_id
                order by max(effective_date) desc, run_id desc
                limit 1
                """
            ),
            {"strategy_version_id": strategy_version_id, "trade_date": trade_date},
        ).mappings().one_or_none()
        if row is None:
            raise RuntimeError(
                "cannot resolve strategy signal for campaign: "
                f"strategy_version_id={strategy_version_id}, trade_date={trade_date}"
            )

        signal_run_id = int(row["run_id"])
        screen_request_id = self.resolve_screen_request_id(signal_run_id=signal_run_id)
        return CampaignSignalSource(
            strategy_version_id=strategy_version_id,
            signal_run_id=signal_run_id,
            screen_request_id=screen_request_id,
            as_of_date=self._require_date(row["as_of_date"], "as_of_date"),
            effective_date=self._require_date(row["effective_date"], "effective_date"),
        )

    def resolve_screen_request_id(self, *, signal_run_id: int) -> int | None:
        row = self.session.execute(
            text(
                """
                select screen_request_id
                from research_screen_result
                where signal_run_id = :signal_run_id
                  and result_status = 'SUCCESS'
                order by effective_date desc nulls last, id desc
                limit 1
                """
            ),
            {"signal_run_id": signal_run_id},
        ).scalar_one_or_none()
        if row is not None:
            return int(row)

        row = self.session.execute(
            text(
                """
                select id
                from research_screen_request
                where source_signal_run_id = :signal_run_id
                order by effective_date desc nulls last, id desc
                limit 1
                """
            ),
            {"signal_run_id": signal_run_id},
        ).scalar_one_or_none()
        return int(row) if row is not None else None

    def resolve_portfolio_id(self, *, portfolio_id: int | None, portfolio_code: str) -> int | None:
        if portfolio_id is not None:
            exists = self.session.execute(
                text("select 1 from trading_paper_portfolio where id = :id"),
                {"id": portfolio_id},
            ).scalar_one_or_none()
            if exists is None:
                raise RuntimeError(f"portfolio_id does not exist: {portfolio_id}")
            return int(portfolio_id)

        value = self.session.execute(
            text(
                """
                select id
                from trading_paper_portfolio
                where portfolio_code = :portfolio_code
                order by id desc
                limit 1
                """
            ),
            {"portfolio_code": portfolio_code},
        ).scalar_one_or_none()
        return int(value) if value is not None else None

    def has_previous_snapshot(self, *, portfolio_id: int, trade_date: date) -> bool:
        value = self.session.execute(
            text(
                """
                select 1
                from trading_paper_portfolio_snapshot
                where portfolio_id = :portfolio_id
                  and snapshot_date < :trade_date
                limit 1
                """
            ),
            {"portfolio_id": portfolio_id, "trade_date": trade_date},
        ).scalar_one_or_none()
        return value is not None

    def read_snapshots(self, *, portfolio_id: int, start_date: date | None, end_date: date | None) -> list[dict[str, Any]]:
        where = ["portfolio_id = :portfolio_id"]
        params: dict[str, Any] = {"portfolio_id": portfolio_id}
        if start_date is not None:
            where.append("snapshot_date >= :start_date")
            params["start_date"] = start_date
        if end_date is not None:
            where.append("snapshot_date <= :end_date")
            params["end_date"] = end_date

        rows = self.session.execute(
            text(
                f"""
                select
                    run_id,
                    snapshot_date,
                    cash_balance,
                    market_value,
                    total_equity,
                    total_cost,
                    unrealized_pnl,
                    realized_pnl,
                    open_position_count,
                    closed_position_count
                from trading_paper_portfolio_snapshot
                where {' and '.join(where)}
                order by snapshot_date asc, run_id asc
                """
            ),
            params,
        ).mappings().all()
        return [dict(r) for r in rows]

    @staticmethod
    def _coerce_date(value: Any) -> date | None:
        if value is None:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            return date.fromisoformat(value[:10])
        return None

    @classmethod
    def _require_date(cls, value: Any, name: str) -> date:
        coerced = cls._coerce_date(value)
        if coerced is None:
            raise RuntimeError(f"cannot coerce {name} to date: {value!r}")
        return coerced


def decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))
