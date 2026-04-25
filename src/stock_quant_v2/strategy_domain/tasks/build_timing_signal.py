from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from stock_quant_v2.strategy_domain.constants import (
    DEFAULT_PARAMETER_VALUES_MARKET_TIMING,
    MARKET_SUBJECT_KEY_CN_A,
)
from stock_quant_v2.strategy_domain.repositories import StrategySignalRepository
from stock_quant_v2.strategy_domain.services import TimingSignalService


def build_market_timing_signal_from_state(
    session: Session,
    *,
    run_id: int,
    strategy_version_id: int,
    as_of_date: date,
    effective_date: date,
    market_state_payload: dict,
    runtime_params: dict | None = None,
) -> dict:
    params = DEFAULT_PARAMETER_VALUES_MARKET_TIMING.copy()
    if runtime_params:
        params.update(runtime_params)

    state_field = params["state_field"]
    threshold = float(params["risk_on_threshold"])

    if state_field not in market_state_payload:
        raise ValueError(
            f"market_state_payload 缺少字段: {state_field}"
        )

    state_score = float(market_state_payload[state_field])

    service = TimingSignalService()
    row = service.build_market_timing_signal_row(
        run_id=run_id,
        strategy_version_id=strategy_version_id,
        as_of_date=as_of_date,
        effective_date=effective_date,
        state_score=state_score,
        threshold=threshold,
        market_state_payload=market_state_payload,
        runtime_params=params,
        market_subject_key=MARKET_SUBJECT_KEY_CN_A,
    )

    repo = StrategySignalRepository(session)
    repo.create_many([row])

    return {
        "selected_count": 1,
        "market_subject_key": MARKET_SUBJECT_KEY_CN_A,
        "state_score": state_score,
        "threshold": threshold,
        "signal_action": row.signal_action,
        "reason_code": row.reason_code,
    }