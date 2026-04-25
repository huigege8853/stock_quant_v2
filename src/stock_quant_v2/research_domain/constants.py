from decimal import Decimal

from stock_quant_v2.research_domain.enums import (
    AssetClass,
    CashRule,
    CommissionModel,
    EngineCode,
    Frequency,
    LimitUpDownRule,
    MarketCode,
    PortfolioConstructionMode,
    PriceFillRule,
    RebalanceFrequency,
    SignalEffectiveMode,
    SlippageModel,
    SuspendRule,
    TPlusRule,
    VolumeFillRule,
)

DEFAULT_INITIAL_CASH = Decimal("10000000")

DEFAULT_EXECUTION_PROFILE_CODE = "cn_a_daily_default"
DEFAULT_EXECUTION_PROFILE_VERSION = "v1"
DEFAULT_EXECUTION_PROFILE_NAME = "CN A Daily Default Execution Assumption v1"

DEFAULT_EXECUTION_ASSUMPTION = {
    "profile_code": DEFAULT_EXECUTION_PROFILE_CODE,
    "version_code": DEFAULT_EXECUTION_PROFILE_VERSION,
    "profile_name": DEFAULT_EXECUTION_PROFILE_NAME,
    "market_code": MarketCode.CN_A.value,
    "asset_class": AssetClass.EQUITY.value,
    "frequency": Frequency.DAILY.value,
    "commission_model": CommissionModel.RATE.value,
    "commission_rate": Decimal("0.0003"),
    "min_commission": Decimal("5"),
    "stamp_duty_rate": Decimal("0.001"),
    "transfer_fee_rate": Decimal("0.00001"),
    "slippage_model": SlippageModel.BPS.value,
    "slippage_bps": Decimal("5"),
    "price_fill_rule": PriceFillRule.NEXT_OPEN.value,
    "volume_fill_rule": VolumeFillRule.NO_LIMIT.value,
    "t_plus_rule": TPlusRule.T_PLUS_1.value,
    "lot_size": 100,
    "allow_fractional_share": False,
    "limit_up_down_rule": LimitUpDownRule.BLOCK_IF_LIMIT.value,
    "suspend_rule": SuspendRule.BLOCK_IF_SUSPENDED.value,
    "cash_rule": CashRule.STRICT_CASH.value,
    "is_active": True,
}

DEFAULT_BACKTEST_ENGINE_CODE = EngineCode.BACKTRADER.value
DEFAULT_SIGNAL_EFFECTIVE_MODE = SignalEffectiveMode.EFFECTIVE_DATE.value
DEFAULT_REBALANCE_FREQUENCY = RebalanceFrequency.DAILY.value
DEFAULT_PORTFOLIO_CONSTRUCTION_MODE = PortfolioConstructionMode.EQUAL_WEIGHT_TOP_N.value

DEFAULT_PORTFOLIO_CONSTRUCTION_PAYLOAD = {
    "top_n": 30,
    "max_weight_per_instrument": None,
    "cash_buffer_pct": None,
}