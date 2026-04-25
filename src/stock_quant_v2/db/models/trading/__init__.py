from importlib import import_module

# Ensure referenced tables are registered in Base.metadata before trading models
# resolve string-based ForeignKey targets.
#
# M6 trading models reference:
# - ops_run
# - meta_instrument
# - strategy_version
# - strategy_signal
# - research_execution_assumption_profile
# - research_screen_request
_REFERENCED_MODEL_MODULES = [
    "stock_quant_v2.db.models.ops.run",
    "stock_quant_v2.db.models.meta.instrument",
    "stock_quant_v2.db.models.strategy.strategy_version",
    "stock_quant_v2.db.models.strategy.strategy_signal",
    "stock_quant_v2.db.models.research.execution_assumption_profile",
    "stock_quant_v2.db.models.research.screen_request",
]

for _module_path in _REFERENCED_MODEL_MODULES:
    import_module(_module_path)


from stock_quant_v2.db.models.trading.paper_account import TradingPaperAccount
from stock_quant_v2.db.models.trading.paper_fill import TradingPaperFill
from stock_quant_v2.db.models.trading.paper_order import TradingPaperOrder
from stock_quant_v2.db.models.trading.paper_portfolio import TradingPaperPortfolio
from stock_quant_v2.db.models.trading.paper_portfolio_snapshot import (
    TradingPaperPortfolioSnapshot,
)
from stock_quant_v2.db.models.trading.paper_position import TradingPaperPosition
from stock_quant_v2.db.models.trading.paper_target_position import (
    TradingPaperTargetPosition,
)
from stock_quant_v2.db.models.trading.paper_trade_ledger import TradingPaperTradeLedger

__all__ = [
    "TradingPaperAccount",
    "TradingPaperPortfolio",
    "TradingPaperTargetPosition",
    "TradingPaperOrder",
    "TradingPaperFill",
    "TradingPaperPosition",
    "TradingPaperPortfolioSnapshot",
    "TradingPaperTradeLedger",
]