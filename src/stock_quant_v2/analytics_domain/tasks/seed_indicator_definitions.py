from __future__ import annotations

from sqlalchemy.orm import Session

from stock_quant_v2.analytics_domain.constants import INDICATOR_CODES
from stock_quant_v2.analytics_domain.enums import IndicatorCategory
from stock_quant_v2.analytics_domain.repositories.analytics_definition_repository import AnalyticsDefinitionRepository


SEED_INDICATORS: list[dict] = [
    {
        "indicator_code": INDICATOR_CODES["ADJ_CLOSE"],
        "indicator_name": "Adjusted Close",
        "category": IndicatorCategory.PRICE.value,
        "input_topic": "core_daily_bar+core_adjust_factor",
        "input_fields_json": ["close", "adjust_factor"],
        "formula_expr": "close * adjust_factor",
        "window_size": 1,
        "warmup_bars": 1,
        "price_adjust_type": "forward_adj",
        "publish_lag_days": 1,
        "null_policy": "keep_null",
        "value_type": "numeric",
        "version": "v1",
        "is_active": True,
        "description": "前复权收盘价",
    },
    {
        "indicator_code": INDICATOR_CODES["RET_1D"],
        "indicator_name": "1D Return",
        "category": IndicatorCategory.RETURN.value,
        "input_topic": "analytics_instrument_indicator_snapshot",
        "input_fields_json": ["adj_close"],
        "formula_expr": "adj_close[t] / adj_close[t-1] - 1",
        "window_size": 2,
        "warmup_bars": 2,
        "price_adjust_type": "forward_adj",
        "publish_lag_days": 1,
        "null_policy": "keep_null",
        "value_type": "numeric",
        "version": "v1",
        "is_active": True,
        "description": "1日收益率",
    },
    {
        "indicator_code": INDICATOR_CODES["RET_20D"],
        "indicator_name": "20D Return",
        "category": IndicatorCategory.RETURN.value,
        "input_topic": "analytics_instrument_indicator_snapshot",
        "input_fields_json": ["adj_close"],
        "formula_expr": "adj_close[t] / adj_close[t-20] - 1",
        "window_size": 21,
        "warmup_bars": 21,
        "price_adjust_type": "forward_adj",
        "publish_lag_days": 1,
        "null_policy": "keep_null",
        "value_type": "numeric",
        "version": "v1",
        "is_active": True,
        "description": "20日收益率",
    },
    {
        "indicator_code": INDICATOR_CODES["MA_20"],
        "indicator_name": "MA 20",
        "category": IndicatorCategory.TREND.value,
        "input_topic": "analytics_instrument_indicator_snapshot",
        "input_fields_json": ["adj_close"],
        "formula_expr": "rolling_mean(adj_close, 20)",
        "window_size": 20,
        "warmup_bars": 20,
        "price_adjust_type": "forward_adj",
        "publish_lag_days": 1,
        "null_policy": "keep_null",
        "value_type": "numeric",
        "version": "v1",
        "is_active": True,
        "description": "20日均线",
    },
    {
        "indicator_code": INDICATOR_CODES["VOLATILITY_20"],
        "indicator_name": "Volatility 20",
        "category": IndicatorCategory.VOLATILITY.value,
        "input_topic": "analytics_instrument_indicator_snapshot",
        "input_fields_json": ["ret_1d"],
        "formula_expr": "rolling_std(ret_1d, 20)",
        "window_size": 20,
        "warmup_bars": 20,
        "price_adjust_type": "forward_adj",
        "publish_lag_days": 1,
        "null_policy": "keep_null",
        "value_type": "numeric",
        "version": "v1",
        "is_active": True,
        "description": "20日波动率",
    },
    {
        "indicator_code": INDICATOR_CODES["TRADABLE_FLAG"],
        "indicator_name": "Tradable Flag",
        "category": IndicatorCategory.TRADABILITY.value,
        "input_topic": "core_instrument_status_daily+core_price_limit_daily",
        "input_fields_json": ["trading_status", "up_limit_price", "close"],
        "formula_expr": "trading_status == TRADING and close < up_limit_price",
        "window_size": 1,
        "warmup_bars": 1,
        "price_adjust_type": "raw",
        "publish_lag_days": 1,
        "null_policy": "keep_null",
        "value_type": "numeric",
        "version": "v1",
        "is_active": True,
        "description": "首版可交易标记",
    },
]


def run(session: Session) -> int:
    repo = AnalyticsDefinitionRepository(session=session)
    count = 0
    for item in SEED_INDICATORS:
        repo.upsert_indicator_definition(item)
        count += 1
    session.commit()
    return count