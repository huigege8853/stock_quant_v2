from __future__ import annotations

from sqlalchemy.orm import Session

from stock_quant_v2.analytics_domain.constants import FEATURE_CODES, FEATURE_SET_CODES
from stock_quant_v2.analytics_domain.repositories.analytics_definition_repository import AnalyticsDefinitionRepository


SEED_FEATURES: list[dict] = [
    {
        "feature_code": FEATURE_CODES["FEAT_MOM_20"],
        "feature_name": "Feature Momentum 20D",
        "source_type": "factor",
        "source_ref_code": "mom_20",
        "dtype": "float64",
        "fillna_policy": "none",
        "scaling_policy": "none",
        "winsorize_policy": "none",
        "availability_rule_json": {"require_ready_factor": True},
        "version": "v1",
        "is_active": True,
        "description": "来自 factor: mom_20",
    },
    {
        "feature_code": FEATURE_CODES["FEAT_TREND_STRENGTH_20"],
        "feature_name": "Feature Trend Strength 20D",
        "source_type": "factor",
        "source_ref_code": "trend_strength_20",
        "dtype": "float64",
        "fillna_policy": "none",
        "scaling_policy": "none",
        "winsorize_policy": "none",
        "availability_rule_json": {"require_ready_factor": True},
        "version": "v1",
        "is_active": True,
        "description": "来自 factor: trend_strength_20",
    },
    {
        "feature_code": FEATURE_CODES["FEAT_VOLATILITY_RANK_20"],
        "feature_name": "Feature Volatility Rank 20D",
        "source_type": "factor",
        "source_ref_code": "volatility_rank_20",
        "dtype": "float64",
        "fillna_policy": "none",
        "scaling_policy": "none",
        "winsorize_policy": "none",
        "availability_rule_json": {"require_ready_factor": True},
        "version": "v1",
        "is_active": True,
        "description": "来自 factor: volatility_rank_20",
    },
    {
        "feature_code": FEATURE_CODES["FEAT_TRADABILITY_SCORE"],
        "feature_name": "Feature Tradability Score",
        "source_type": "factor",
        "source_ref_code": "tradability_score",
        "dtype": "float64",
        "fillna_policy": "none",
        "scaling_policy": "none",
        "winsorize_policy": "none",
        "availability_rule_json": {"require_ready_factor": True},
        "version": "v1",
        "is_active": True,
        "description": "来自 factor: tradability_score",
    },
    {
        "feature_code": FEATURE_CODES["FEAT_TRADABLE_FLAG"],
        "feature_name": "Feature Tradable Flag",
        "source_type": "indicator",
        "source_ref_code": "tradable_flag",
        "dtype": "float64",
        "fillna_policy": "none",
        "scaling_policy": "none",
        "winsorize_policy": "none",
        "availability_rule_json": {"require_ready_indicator": True},
        "version": "v1",
        "is_active": True,
        "description": "来自 indicator: tradable_flag",
    },
]

SEED_FEATURE_SET: dict = {
    "feature_set_code": FEATURE_SET_CODES["FS_DAILY_ALPHA_V1"],
    "feature_set_name": "Daily Alpha Feature Set V1",
    "universe_rule_json": {"scope": "all_a_share"},
    "feature_codes_json": [
        FEATURE_CODES["FEAT_MOM_20"],
        FEATURE_CODES["FEAT_TREND_STRENGTH_20"],
        FEATURE_CODES["FEAT_VOLATILITY_RANK_20"],
        FEATURE_CODES["FEAT_TRADABILITY_SCORE"],
        FEATURE_CODES["FEAT_TRADABLE_FLAG"],
    ],
    "join_keys_json": ["trade_date", "instrument_id"],
    "sample_filter_rule_json": {"require_trade_date": True},
    "standardization_rule_json": {"mode": "none"},
    "label_codes_json": [],
    "train_serving_contract_json": {"strict_mode": True},
    "version": "v1",
    "is_active": True,
    "description": "M3 首版 feature set",
}


def run(session: Session) -> int:
    repo = AnalyticsDefinitionRepository(session=session)
    count = 0

    for item in SEED_FEATURES:
        repo.upsert_feature_definition(item)
        count += 1

    repo.upsert_feature_set_definition(SEED_FEATURE_SET)
    count += 1

    session.commit()
    return count