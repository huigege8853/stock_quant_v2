from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from stock_quant_v2.db.models.research import (
    ResearchScreenRequest,
    ResearchScreenResult,
)
from stock_quant_v2.research_domain.dto.screen import ScreenRequestDTO


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


class ScreenRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_request(
        self,
        *,
        run_id: int,
        strategy_version_id: int,
        dto: ScreenRequestDTO,
    ) -> ResearchScreenRequest:
        payload = _json_safe(asdict(dto))

        obj = ResearchScreenRequest(
            run_id=run_id,
            request_code=f"screen_{dto.strategy_code}_{dto.version_code}_{dto.as_of_date}",
            request_name=f"Screen {dto.strategy_code}:{dto.version_code} {dto.as_of_date}",
            strategy_version_id=strategy_version_id,
            signal_lookup_mode=dto.signal_lookup_mode,
            source_signal_run_id=dto.source_signal_run_id,
            as_of_date=dto.as_of_date,
            effective_date=dto.effective_date,
            max_count=dto.max_count,
            min_score=dto.min_score,
            include_reason_codes=dto.include_reason_codes,
            exclude_reason_codes=dto.exclude_reason_codes,
            universe_filter=dto.universe_filter,
            signal_filter=dto.signal_filter,
            parameter_values=dto.parameter_values,
            request_payload=payload,
        )

        self.session.add(obj)
        self.session.flush()
        return obj

    def create_result(
        self,
        *,
        run_id: int,
        screen_request_id: int,
        signal_run_id: int,
        as_of_date,
        effective_date,
        eligible_universe_size: int | None,
        selected_count: int,
        score_min,
        score_max,
        score_avg,
        result_status: str,
        result_summary: dict[str, Any] | None = None,
    ) -> ResearchScreenResult:
        obj = ResearchScreenResult(
            run_id=run_id,
            screen_request_id=screen_request_id,
            signal_run_id=signal_run_id,
            as_of_date=as_of_date,
            effective_date=effective_date,
            eligible_universe_size=eligible_universe_size,
            selected_count=selected_count,
            score_min=score_min,
            score_max=score_max,
            score_avg=score_avg,
            result_status=result_status,
            result_summary=result_summary or {},
            artifact_run_id=run_id,
            completed_at=datetime.now(timezone.utc),
        )

        self.session.add(obj)
        self.session.flush()
        return obj