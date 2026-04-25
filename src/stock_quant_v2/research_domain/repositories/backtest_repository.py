from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_quant_v2.db.models.research import (
    ResearchBacktestRequest,
    ResearchBacktestResult,
)
from stock_quant_v2.research_domain.dto.backtest import BacktestRequestDTO
from stock_quant_v2.research_domain.enums import ResultStatus


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


class BacktestRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_request(
        self,
        *,
        run_id: int,
        strategy_version_id: int,
        execution_assumption_profile_id: int,
        benchmark_definition_id: int | None,
        dto: BacktestRequestDTO,
    ) -> ResearchBacktestRequest:
        payload = _json_safe(asdict(dto))

        obj = ResearchBacktestRequest(
            run_id=run_id,
            request_code=(
                f"backtest_{dto.strategy_code}_{dto.version_code}_"
                f"{dto.start_date}_{dto.end_date}"
            ),
            request_name=(
                f"Backtest {dto.strategy_code}:{dto.version_code} "
                f"{dto.start_date} ~ {dto.end_date}"
            ),
            strategy_version_id=strategy_version_id,
            screen_request_id=dto.screen_request_id,
            source_signal_run_id=dto.source_signal_run_id,
            execution_assumption_profile_id=execution_assumption_profile_id,
            benchmark_definition_id=benchmark_definition_id,
            start_date=dto.start_date,
            end_date=dto.end_date,
            initial_cash=dto.initial_cash,
            rebalance_frequency=dto.rebalance_frequency,
            signal_effective_mode=dto.signal_effective_mode,
            portfolio_construction_mode=dto.portfolio_construction_mode,
            portfolio_construction_payload=dto.portfolio_construction_payload,
            data_feed_payload=dto.data_feed_payload,
            engine_code=dto.engine_code,
            engine_payload=dto.engine_payload,
            request_payload=payload,
        )

        self.session.add(obj)
        self.session.flush()
        return obj

    def get_request_by_id(self, backtest_request_id: int) -> ResearchBacktestRequest:
        obj = self.session.get(ResearchBacktestRequest, backtest_request_id)
        if obj is None:
            raise RuntimeError(f"backtest_request not found: id={backtest_request_id}")
        return obj

    def get_latest_request_without_result(self) -> ResearchBacktestRequest | None:
        stmt = (
            select(ResearchBacktestRequest)
            .outerjoin(
                ResearchBacktestResult,
                ResearchBacktestRequest.run_id == ResearchBacktestResult.run_id,
            )
            .where(ResearchBacktestResult.id.is_(None))
            .order_by(ResearchBacktestRequest.id.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def get_latest_request(self) -> ResearchBacktestRequest | None:
        stmt = (
            select(ResearchBacktestRequest)
            .order_by(ResearchBacktestRequest.id.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def get_or_create_placeholder_result(
        self,
        *,
        request: ResearchBacktestRequest,
    ) -> ResearchBacktestResult:
        stmt = select(ResearchBacktestResult).where(
            ResearchBacktestResult.run_id == request.run_id
        )
        obj = self.session.execute(stmt).scalar_one_or_none()

        result_summary = {
            "execution_enabled": False,
            "stage": "M5.5_BACKTEST_RESULT_SKELETON",
            "note": "placeholder result only; backtrader execution not started",
            "backtest_request_id": request.id,
            "source_signal_run_id": request.source_signal_run_id,
            "screen_request_id": request.screen_request_id,
            "engine_code": request.engine_code,
        }

        if obj is None:
            obj = ResearchBacktestResult(
                run_id=request.run_id,
                backtest_request_id=request.id,
                result_status=ResultStatus.EMPTY.value,
                start_date=request.start_date,
                end_date=request.end_date,
                trading_days=None,
                initial_cash=request.initial_cash,
                final_equity=None,
                total_return=None,
                annual_return=None,
                benchmark_return=None,
                excess_return=None,
                max_drawdown=None,
                sharpe_ratio=None,
                volatility=None,
                win_rate=None,
                turnover_avg=None,
                order_count=0,
                trade_count=0,
                result_summary=result_summary,
                completed_at=datetime.now(timezone.utc),
            )
            self.session.add(obj)
        else:
            obj.backtest_request_id = request.id
            obj.result_status = ResultStatus.EMPTY.value
            obj.start_date = request.start_date
            obj.end_date = request.end_date
            obj.trading_days = None
            obj.initial_cash = request.initial_cash
            obj.final_equity = None
            obj.total_return = None
            obj.annual_return = None
            obj.benchmark_return = None
            obj.excess_return = None
            obj.max_drawdown = None
            obj.sharpe_ratio = None
            obj.volatility = None
            obj.win_rate = None
            obj.turnover_avg = None
            obj.order_count = 0
            obj.trade_count = 0
            obj.result_summary = result_summary
            obj.completed_at = datetime.now(timezone.utc)

        self.session.flush()
        return obj