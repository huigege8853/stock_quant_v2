from __future__ import annotations

from dataclasses import asdict
from typing import Any

from sqlalchemy.orm import Session

from stock_quant_v2.research_domain.dto.backtest import BacktestRequestDTO
from stock_quant_v2.research_domain.repositories import (
    BacktestRepository,
    BenchmarkRepository,
    ExecutionAssumptionRepository,
    OpsRunRepository,
)
from stock_quant_v2.research_domain.services.signal_resolver_service import (
    SignalResolverService,
)


class BacktestRequestService:
    def __init__(self, session: Session):
        self.session = session
        self.ops_run_repo = OpsRunRepository(session)
        self.backtest_repo = BacktestRepository(session)
        self.execution_repo = ExecutionAssumptionRepository(session)
        self.benchmark_repo = BenchmarkRepository(session)
        self.signal_resolver = SignalResolverService(session)

    def create_backtest_request(self, dto: BacktestRequestDTO) -> dict[str, Any]:
        run_id = self.ops_run_repo.create_run(
            run_type="backtest",
            run_name="M5 Backtest Request Skeleton",
            payload=asdict(dto),
        )

        try:
            strategy_version_id = self.signal_resolver.resolve_strategy_version_id(
                strategy_code=dto.strategy_code,
                version_code=dto.version_code,
            )

            execution_profile = self.execution_repo.get_by_code_version(
                profile_code=dto.execution_assumption_profile_code,
                version_code=dto.execution_assumption_profile_version,
            )

            benchmark = self.benchmark_repo.get_optional_by_code_version(
                benchmark_code=dto.benchmark_code,
                version_code=dto.benchmark_version,
            )

            request = self.backtest_repo.create_request(
                run_id=run_id,
                strategy_version_id=strategy_version_id,
                execution_assumption_profile_id=execution_profile.id,
                benchmark_definition_id=benchmark.id if benchmark else None,
                dto=dto,
            )

            self.ops_run_repo.mark_success(run_id)
            self.session.commit()

            return {
                "run_id": run_id,
                "backtest_request_id": request.id,
                "strategy_version_id": strategy_version_id,
                "source_signal_run_id": request.source_signal_run_id,
                "screen_request_id": request.screen_request_id,
                "execution_assumption_profile_id": execution_profile.id,
                "execution_assumption_profile": (
                    f"{execution_profile.profile_code}:"
                    f"{execution_profile.version_code}"
                ),
                "benchmark_definition_id": benchmark.id if benchmark else None,
                "benchmark": (
                    f"{benchmark.benchmark_code}:{benchmark.version_code}"
                    if benchmark
                    else None
                ),
                "start_date": str(request.start_date),
                "end_date": str(request.end_date),
                "initial_cash": str(request.initial_cash),
                "rebalance_frequency": request.rebalance_frequency,
                "signal_effective_mode": request.signal_effective_mode,
                "portfolio_construction_mode": request.portfolio_construction_mode,
                "engine_code": request.engine_code,
                "status": "SUCCESS",
                "note": "backtest_request created only; backtrader execution not started",
            }

        except Exception as exc:
            self.session.rollback()
            self.ops_run_repo.mark_failed(run_id, str(exc))
            self.session.commit()
            raise