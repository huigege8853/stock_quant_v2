from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from stock_quant_v2.research_domain.repositories import (
    BacktestRepository,
    OpsRunRepository,
    RunResultRepository,
)


class BacktestResultService:
    def __init__(self, session: Session):
        self.session = session
        self.backtest_repo = BacktestRepository(session)
        self.run_result_repo = RunResultRepository(session)
        self.ops_run_repo = OpsRunRepository(session)

    def create_placeholder_result(
        self,
        *,
        backtest_request_id: int | None = None,
    ) -> dict[str, Any]:
        try:
            if backtest_request_id is not None:
                request = self.backtest_repo.get_request_by_id(backtest_request_id)
            else:
                request = self.backtest_repo.get_latest_request_without_result()
                if request is None:
                    request = self.backtest_repo.get_latest_request()

            if request is None:
                raise RuntimeError("no backtest_request found")

            result = self.backtest_repo.get_or_create_placeholder_result(
                request=request
            )

            self.run_result_repo.replace_backtest_metrics(
                run_id=request.run_id,
                metrics={
                    "backtest_request_id": request.id,
                    "strategy_version_id": request.strategy_version_id,
                    "source_signal_run_id": request.source_signal_run_id,
                    "screen_request_id": request.screen_request_id,
                    "execution_assumption_profile_id": (
                        request.execution_assumption_profile_id
                    ),
                    "benchmark_definition_id": request.benchmark_definition_id,
                    "initial_cash": request.initial_cash,
                    "order_count": 0,
                    "trade_count": 0,
                    "result_status": result.result_status,
                    "execution_enabled": False,
                },
            )

            self.ops_run_repo.mark_success(request.run_id)
            self.session.commit()

            return {
                "run_id": request.run_id,
                "backtest_request_id": request.id,
                "backtest_result_id": result.id,
                "result_status": result.result_status,
                "start_date": str(result.start_date),
                "end_date": str(result.end_date),
                "initial_cash": str(result.initial_cash)
                if result.initial_cash is not None
                else None,
                "final_equity": str(result.final_equity)
                if result.final_equity is not None
                else None,
                "order_count": result.order_count,
                "trade_count": result.trade_count,
                "metrics_namespace": "backtest",
                "note": "placeholder result only; backtrader execution not started",
            }

        except Exception:
            self.session.rollback()
            raise