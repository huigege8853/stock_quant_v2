from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class MarketCode(StrEnum):
    CN_A = "CN_A"


class AssetClass(StrEnum):
    EQUITY = "EQUITY"


class Frequency(StrEnum):
    DAILY = "DAILY"


class CommissionModel(StrEnum):
    RATE = "RATE"


class SlippageModel(StrEnum):
    BPS = "BPS"
    FIXED_AMOUNT = "FIXED_AMOUNT"
    NONE = "NONE"


class PriceFillRule(StrEnum):
    NEXT_OPEN = "NEXT_OPEN"
    SAME_DAY_CLOSE = "SAME_DAY_CLOSE"
    NEXT_VWAP = "NEXT_VWAP"


class VolumeFillRule(StrEnum):
    NO_LIMIT = "NO_LIMIT"
    BY_VOLUME_CAP = "BY_VOLUME_CAP"


class TPlusRule(StrEnum):
    T_PLUS_0 = "T_PLUS_0"
    T_PLUS_1 = "T_PLUS_1"


class LimitUpDownRule(StrEnum):
    BLOCK_IF_LIMIT = "BLOCK_IF_LIMIT"
    ALLOW_WITH_SLIPPAGE = "ALLOW_WITH_SLIPPAGE"
    IGNORE = "IGNORE"


class SuspendRule(StrEnum):
    BLOCK_IF_SUSPENDED = "BLOCK_IF_SUSPENDED"
    IGNORE = "IGNORE"


class CashRule(StrEnum):
    STRICT_CASH = "STRICT_CASH"
    ALLOW_MARGIN = "ALLOW_MARGIN"


class SignalLookupMode(StrEnum):
    EXISTING_SIGNAL = "EXISTING_SIGNAL"
    BUILD_THEN_READ = "BUILD_THEN_READ"


class ResultStatus(StrEnum):
    SUCCESS = "SUCCESS"
    EMPTY = "EMPTY"
    FAILED = "FAILED"


class BenchmarkType(StrEnum):
    MARKET_INDEX = "MARKET_INDEX"
    STATIC_RATE = "STATIC_RATE"
    CUSTOM_PORTFOLIO = "CUSTOM_PORTFOLIO"


class EngineCode(StrEnum):
    BACKTRADER = "backtrader"


class SignalEffectiveMode(StrEnum):
    EFFECTIVE_DATE = "EFFECTIVE_DATE"


class RebalanceFrequency(StrEnum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"


class PortfolioConstructionMode(StrEnum):
    EQUAL_WEIGHT_TOP_N = "EQUAL_WEIGHT_TOP_N"
    SCORE_WEIGHTED_TOP_N = "SCORE_WEIGHTED_TOP_N"


class MetricNamespace(StrEnum):
    SCREEN = "screen"
    BACKTEST = "backtest"
    BENCHMARK = "benchmark"
    RISK = "risk"
    REPORT = "report"


class SeriesNamespace(StrEnum):
    BACKTEST = "backtest"
    BENCHMARK = "benchmark"
    SCREEN = "screen"


class DimensionType(StrEnum):
    PORTFOLIO = "PORTFOLIO"
    BENCHMARK = "BENCHMARK"
    INSTRUMENT = "INSTRUMENT"
    INDUSTRY = "INDUSTRY"


class StorageBackend(StrEnum):
    LOCAL = "LOCAL"
    DB = "DB"
    S3_COMPATIBLE = "S3_COMPATIBLE"


class ArtifactType(StrEnum):
    CSV = "CSV"
    JSON = "JSON"
    HTML = "HTML"
    MARKDOWN = "MARKDOWN"
    PNG = "PNG"
    PARQUET = "PARQUET"