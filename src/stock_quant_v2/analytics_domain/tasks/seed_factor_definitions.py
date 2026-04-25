from __future__ import annotations

from sqlalchemy.orm import Session

from stock_quant_v2.analytics_domain.constants import FACTOR_CODES
from stock_quant_v2.analytics_domain.repositories.analytics_definition_repository import AnalyticsDefinitionRepository


SEED_FACTORS: list[dict] = [
    {
        "factor_code": FACTOR_CODES["MOM_20"],
        "factor_name": "Momentum 20D",
        "factor_family": "momentum",
        "base_indicator_codes_json": ["ret_20d"],
        "transform_pipeline_json": ["identity"],
        "cross_sectional_scope": "all_a_share",
        "winsorize_method": None,
        "standardize_method": "zscore",
        "neutralize_method": None,
        "warmup_bars": 21,
        "publish_lag_days": 1,
        "value_type": "numeric",
        "version": "v1",
        "is_active": True,
        "description": "20日动量因子，直接复用 ret_20d",
    },
    {
        "factor_code": FACTOR_CODES["TREND_STRENGTH_20"],
        "factor_name": "Trend Strength 20D",
        "factor_family": "trend",
        "base_indicator_codes_json": ["adj_close", "ma_20"],
        "transform_pipeline_json": ["adj_close / ma_20 - 1"],
        "cross_sectional_scope": "all_a_share",
        "winsorize_method": None,
        "standardize_method": "zscore",
        "neutralize_method": None,
        "warmup_bars": 20,
        "publish_lag_days": 1,
        "value_type": "numeric",
        "version": "v1",
        "is_active": True,
        "description": "价格相对 20 日均线强弱",
    },
    {
        "factor_code": FACTOR_CODES["VOLATILITY_RANK_20"],
        "factor_name": "Volatility Rank 20D",
        "factor_family": "risk",
        "base_indicator_codes_json": ["volatility_20"],
        "transform_pipeline_json": ["cross_section_rank(volatility_20)"],
        "cross_sectional_scope": "all_a_share",
        "winsorize_method": None,
        "standardize_method": "zscore",
        "neutralize_method": None,
        "warmup_bars": 20,
        "publish_lag_days": 1,
        "value_type": "numeric",
        "version": "v1",
        "is_active": True,
        "description": "20日波动率横截面排名",
    },
    {
        "factor_code": FACTOR_CODES["TRADABILITY_SCORE"],
        "factor_name": "Tradability Score",
        "factor_family": "tradability",
        "base_indicator_codes_json": ["tradable_flag"],
        "transform_pipeline_json": ["identity"],
        "cross_sectional_scope": "all_a_share",
        "winsorize_method": None,
        "standardize_method": "zscore",
        "neutralize_method": None,
        "warmup_bars": 1,
        "publish_lag_days": 1,
        "value_type": "numeric",
        "version": "v1",
        "is_active": True,
        "description": "可交易性分数，当前首版直接复用 tradable_flag",
    },
]


def run(session: Session) -> int:
    repo = AnalyticsDefinitionRepository(session=session)
    count = 0
    for item in SEED_FACTORS:
        repo.upsert_factor_definition(item)
        count += 1
    session.commit()
    return count