from __future__ import annotations

FEATURE_SET_CODE = "fs_daily_alpha_v1"
FEATURE_SET_VERSION = "v1"

STRATEGY_CODE_ALPHA_SELECTION = "alpha_selection"
STRATEGY_NAME_ALPHA_SELECTION = "Alpha Selection"
STRATEGY_VERSION_CODE_V1 = "v1"
STRATEGY_VERSION_NO_V1 = 1
OUTPUT_CONTRACT_VERSION_SIGNAL_V1 = "signal_v1"

IMPLEMENTATION_REF_ALPHA_SELECTION = (
    "stock_quant_v2.strategy_domain.tasks.build_strategy_signal:build_alpha_selection_signal"
)

REQUIRED_FEATURE_CODES_ALPHA_SELECTION = [
    "feat_mom_20",
    "feat_trend_strength_20",
    "feat_volatility_rank_20",
    "feat_tradability_score",
    "feat_tradable_flag",
]

DEFAULT_PARAMETER_VALUES_ALPHA_SELECTION = {
    "top_n": 30,
    "min_score": 0.60,
    "require_tradable_flag": False,
    "tradable_flag_pass_values": None,
    "weights": {
        "mom": 0.35,
        "trend": 0.25,
        "low_vol": 0.20,
        "tradability": 0.20,
    },
}

PARAMETER_SCHEMA_JSON_ALPHA_SELECTION = {
    "type": "object",
    "additionalProperties": False,
    "required": ["top_n", "min_score", "require_tradable_flag", "weights"],
    "properties": {
        "top_n": {"type": "integer", "minimum": 1, "maximum": 500, "default": 30},
        "min_score": {"type": "number", "minimum": 0.0, "maximum": 1.0, "default": 0.60},
        "require_tradable_flag": {"type": "boolean", "default": False},
        "tradable_flag_pass_values": {
            "type": ["array", "null"],
            "items": {"type": "number"},
            "default": None,
        },
        "weights": {
            "type": "object",
            "additionalProperties": False,
            "required": ["mom", "trend", "low_vol", "tradability"],
            "properties": {
                "mom": {"type": "number", "minimum": 0.0, "maximum": 1.0, "default": 0.35},
                "trend": {"type": "number", "minimum": 0.0, "maximum": 1.0, "default": 0.25},
                "low_vol": {"type": "number", "minimum": 0.0, "maximum": 1.0, "default": 0.20},
                "tradability": {"type": "number", "minimum": 0.0, "maximum": 1.0, "default": 0.20},
            },
        },
    },
}

DEPENDENCY_SPEC_JSON_ALPHA_SELECTION = {
    "market_scope": "CN_A",
    "bar_frequency": "1d",
    "price_basis": "adj_strict",
    "signal_effective_lag_trading_days": 1,
    "feature_set": {
        "code": FEATURE_SET_CODE,
        "version": FEATURE_SET_VERSION,
    },
    "required_features": REQUIRED_FEATURE_CODES_ALPHA_SELECTION,
    "forbidden_inputs": ["label_*"],
}

# -----------------------------------------
# timing skeleton v1
# -----------------------------------------

STRATEGY_CODE_MARKET_TIMING = "market_timing"
STRATEGY_NAME_MARKET_TIMING = "Market Timing"
MARKET_SUBJECT_KEY_CN_A = "market:CN_A"

DEFAULT_PARAMETER_VALUES_MARKET_TIMING = {
    "state_field": "regime_score",
    "risk_on_threshold": 0.50,
}

PARAMETER_SCHEMA_JSON_MARKET_TIMING = {
    "type": "object",
    "additionalProperties": False,
    "required": ["state_field", "risk_on_threshold"],
    "properties": {
        "state_field": {
            "type": "string",
            "default": "regime_score",
        },
        "risk_on_threshold": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "default": 0.50,
        },
    },
}

DEPENDENCY_SPEC_JSON_MARKET_TIMING = {
    "market_scope": "CN_A",
    "bar_frequency": "1d",
    "state_source": "to_be_bound_later",
    "required_market_state_fields": ["regime_score"],
    "forbidden_inputs": ["label_*"],
}

IMPLEMENTATION_REF_MARKET_TIMING = (
    "stock_quant_v2.strategy_domain.tasks.build_timing_signal:build_market_timing_signal_from_state"
)