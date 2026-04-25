from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from stock_quant_v2.strategy_domain.constants import (
    FEATURE_SET_CODE,
    FEATURE_SET_VERSION,
    REQUIRED_FEATURE_CODES_ALPHA_SELECTION,
)
from stock_quant_v2.strategy_domain.repositories import StrategySignalRepository
from stock_quant_v2.strategy_domain.services import (
    ParameterValidationService,
    RuleSelectionService,
    SignalPublishService,
)


def build_alpha_selection_signal(
    session: Session,
    *,
    run_id: int,
    strategy_version_id: int,
    as_of_date: date,
    effective_date: date,
    runtime_params: dict,
) -> dict:
    ParameterValidationService.validate_alpha_selection_params(runtime_params)

    signal_repo = StrategySignalRepository(session)
    feature_rows = signal_repo.load_feature_rows(
        trade_date=as_of_date,
        feature_set_code=FEATURE_SET_CODE,
        feature_set_version=FEATURE_SET_VERSION,
        feature_codes=REQUIRED_FEATURE_CODES_ALPHA_SELECTION,
    )

    feature_df = RuleSelectionService.build_feature_matrix(
        feature_rows=feature_rows,
        required_feature_codes=REQUIRED_FEATURE_CODES_ALPHA_SELECTION,
    )
    selected_df = RuleSelectionService.compute_alpha_selection(
        feature_df=feature_df,
        runtime_params=runtime_params,
    )

    publish_service = SignalPublishService()
    signal_rows = publish_service.build_alpha_selection_signal_rows(
        run_id=run_id,
        strategy_version_id=strategy_version_id,
        as_of_date=as_of_date,
        effective_date=effective_date,
        selected_df=selected_df,
        feature_set_code=FEATURE_SET_CODE,
        feature_set_version=FEATURE_SET_VERSION,
        runtime_params=runtime_params,
    )
    signal_repo.create_many(signal_rows)

    return {
        "selected_count": len(signal_rows),
        "eligible_universe_size": int(selected_df["universe_size"].iloc[0]) if not selected_df.empty else 0,
        "score_min": round(float(selected_df["raw_score"].min()), 8) if not selected_df.empty else None,
        "score_max": round(float(selected_df["raw_score"].max()), 8) if not selected_df.empty else None,
        "score_avg": round(float(selected_df["raw_score"].mean()), 8) if not selected_df.empty else None,
    }