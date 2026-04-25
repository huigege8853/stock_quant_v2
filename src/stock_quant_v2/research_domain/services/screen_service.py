from __future__ import annotations

from dataclasses import asdict

from sqlalchemy.orm import Session

from stock_quant_v2.research_domain.dto.screen import ScreenRequestDTO, ScreenResultDTO
from stock_quant_v2.research_domain.enums import ResultStatus
from stock_quant_v2.research_domain.repositories import (
    OpsRunRepository,
    RunResultRepository,
    ScreenRepository,
)
from stock_quant_v2.research_domain.services.signal_resolver_service import (
    SignalResolverService,
)


class ScreenService:
    def __init__(self, session: Session):
        self.session = session
        self.ops_run_repo = OpsRunRepository(session)
        self.screen_repo = ScreenRepository(session)
        self.result_repo = RunResultRepository(session)
        self.signal_resolver = SignalResolverService(session)

    def run_screen(self, dto: ScreenRequestDTO) -> ScreenResultDTO:
        run_id = self.ops_run_repo.create_run(
            run_type="screen",
            run_name="M5 Screen First Chain",
            payload=asdict(dto),
        )

        try:
            strategy_version_id = self.signal_resolver.resolve_strategy_version_id(
                strategy_code=dto.strategy_code,
                version_code=dto.version_code,
            )

            signal_run_id = self.signal_resolver.resolve_signal_run_id(
                strategy_version_id=strategy_version_id,
                as_of_date=dto.as_of_date,
                effective_date=dto.effective_date,
                source_signal_run_id=dto.source_signal_run_id,
            )

            request = self.screen_repo.create_request(
                run_id=run_id,
                strategy_version_id=strategy_version_id,
                dto=dto,
            )

            summary = self.signal_resolver.load_signal_summary(
                signal_run_id=signal_run_id,
                strategy_version_id=strategy_version_id,
                as_of_date=dto.as_of_date,
                effective_date=dto.effective_date,
                include_reason_codes=dto.include_reason_codes,
                exclude_reason_codes=dto.exclude_reason_codes,
            )

            status = (
                ResultStatus.SUCCESS.value
                if summary.selected_count > 0
                else ResultStatus.EMPTY.value
            )

            result = self.screen_repo.create_result(
                run_id=run_id,
                screen_request_id=request.id,
                signal_run_id=signal_run_id,
                as_of_date=dto.as_of_date,
                effective_date=dto.effective_date,
                eligible_universe_size=summary.eligible_universe_size,
                selected_count=summary.selected_count,
                score_min=summary.score_min,
                score_max=summary.score_max,
                score_avg=summary.score_avg,
                result_status=status,
                result_summary={
                    "strategy_code": dto.strategy_code,
                    "version_code": dto.version_code,
                    "signal_run_id": signal_run_id,
                    "include_reason_codes": dto.include_reason_codes,
                    "exclude_reason_codes": dto.exclude_reason_codes,
                },
            )

            self.result_repo.replace_screen_metrics(
                run_id=run_id,
                metrics={
                    "selected_count": summary.selected_count,
                    "eligible_universe_size": summary.eligible_universe_size,
                    "score_min": summary.score_min,
                    "score_max": summary.score_max,
                    "score_avg": summary.score_avg,
                },
            )

            self.ops_run_repo.mark_success(run_id)
            self.session.commit()

            return ScreenResultDTO(
                run_id=run_id,
                screen_request_id=request.id,
                signal_run_id=signal_run_id,
                as_of_date=result.as_of_date,
                effective_date=result.effective_date,
                eligible_universe_size=result.eligible_universe_size,
                selected_count=result.selected_count,
                score_min=result.score_min,
                score_max=result.score_max,
                score_avg=result.score_avg,
                result_status=result.result_status,
                artifact_codes=[],
            )

        except Exception as exc:
            self.session.rollback()

            # rollback 后重新标记 run 失败。
            self.ops_run_repo.mark_failed(run_id, str(exc))
            self.session.commit()

            raise