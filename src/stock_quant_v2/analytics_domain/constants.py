INDICATOR_VERSION_V1 = "v1"
FACTOR_VERSION_V1 = "v1"
FEATURE_VERSION_V1 = "v1"
LABEL_VERSION_V1 = "v1"

INDICATOR_CODES = {
    "ADJ_CLOSE": "adj_close",
    "RET_1D": "ret_1d",
    "RET_20D": "ret_20d",
    "MA_20": "ma_20",
    "VOLATILITY_20": "volatility_20",
    "TRADABLE_FLAG": "tradable_flag",
}

FACTOR_CODES = {
    "MOM_20": "mom_20",
    "TREND_STRENGTH_20": "trend_strength_20",
    "VOLATILITY_RANK_20": "volatility_rank_20",
    "TRADABILITY_SCORE": "tradability_score",
}

FEATURE_CODES = {
    "FEAT_MOM_20": "feat_mom_20",
    "FEAT_TREND_STRENGTH_20": "feat_trend_strength_20",
    "FEAT_VOLATILITY_RANK_20": "feat_volatility_rank_20",
    "FEAT_TRADABILITY_SCORE": "feat_tradability_score",
    "FEAT_TRADABLE_FLAG": "feat_tradable_flag",
    "FEAT_INDUSTRY_STRENGTH_20": "feat_industry_strength_20",
    "FEAT_INDUSTRY_RET_20": "feat_industry_ret_20",
    "FEAT_INDUSTRY_BREADTH_20": "feat_industry_breadth_20",
}

FEATURE_SET_CODES = {
    "FS_DAILY_ALPHA_V1": "fs_daily_alpha_v1",
}

LABEL_CODES = {
    "LABEL_FWD_RET_5D": "label_fwd_ret_5d",
    "LABEL_FWD_RET_10D": "label_fwd_ret_10d",
    "LABEL_UP_5D_GE_3PCT": "label_up_5d_ge_3pct",
    "LABEL_DOWN_5D_LE_M3PCT": "label_down_5d_le_m3pct",
}