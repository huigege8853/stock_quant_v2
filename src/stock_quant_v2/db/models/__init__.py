from __future__ import annotations


def load_all_models() -> None:
    from stock_quant_v2.db.models.meta.market import MetaMarket  # noqa: F401
    from stock_quant_v2.db.models.meta.exchange import MetaExchange  # noqa: F401
    from stock_quant_v2.db.models.meta.data_vendor import MetaDataVendor  # noqa: F401
    from stock_quant_v2.db.models.meta.dataset import MetaDataset  # noqa: F401
    from stock_quant_v2.db.models.meta.instrument import MetaInstrument  # noqa: F401
    from stock_quant_v2.db.models.meta.symbol_mapping import MetaSymbolMapping  # noqa: F401
    from stock_quant_v2.db.models.meta.trading_calendar import MetaTradingCalendar  # noqa: F401
    from stock_quant_v2.db.models.meta.definition_version import MetaDefinitionVersion  # noqa: F401
    from stock_quant_v2.db.models.meta.data_version import MetaDataVersion  # noqa: F401

    from stock_quant_v2.db.models.ops.run import OpsRun  # noqa: F401
    from stock_quant_v2.db.models.ops.run_step import OpsRunStep  # noqa: F401
    from stock_quant_v2.db.models.ops.event_log import OpsEventLog  # noqa: F401
    from stock_quant_v2.db.models.ops.lock import OpsLock  # noqa: F401

    from stock_quant_v2.db.models.core.daily_bar import CoreDailyBar  # noqa: F401
    from stock_quant_v2.db.models.core.adjust_factor import CoreAdjustFactor  # noqa: F401
    from stock_quant_v2.db.models.core.price_limit_daily import CorePriceLimitDaily  # noqa: F401
    from stock_quant_v2.db.models.core.instrument_status_daily import CoreInstrumentStatusDaily  # noqa: F401

    import stock_quant_v2.db.models.analytics  # noqa: F401
    from stock_quant_v2.db.models import research  # noqa: F401
    from stock_quant_v2.db.models.research import (  # noqa: F401
        ResearchExecutionAssumptionProfile,
        ResearchBenchmarkDefinition,
        ResearchScreenRequest,
        ResearchScreenResult,
        ResearchBacktestRequest,
        ResearchBacktestResult,
    )

    from stock_quant_v2.db.models.ops import (  # noqa: F401
        OpsRunMetricSnapshot,
        OpsRunSeriesSnapshot,
        OpsRunArtifact,
    )

    from stock_quant_v2.db.models.trading import (  # noqa: F401
        TradingPaperAccount,
        TradingPaperFill,
        TradingPaperOrder,
        TradingPaperPortfolio,
        TradingPaperPortfolioSnapshot,
        TradingPaperPosition,
        TradingPaperTargetPosition,
        TradingPaperTradeLedger,
    )

    from stock_quant_v2.db.models.risk import (  # noqa: F401
        RiskRule,
        RiskProfile,
        RiskProfileRule,
        RiskDecision,
    )
