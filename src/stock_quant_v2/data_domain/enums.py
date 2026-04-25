from __future__ import annotations

from enum import StrEnum


class ThemeCode(StrEnum):
    DAILY_BAR = "DailyBar"


class DatasetCode(StrEnum):
    DAILY_BAR = "daily_bar"


class ProviderName(StrEnum):
    BAOSTOCK = "baostock"
    TUSHARE = "tushare"
    AKSHARE = "akshare"
    SINA = "sina"
    FUTURE_PAID_VENDOR = "future_paid_vendor"


class SyncMode(StrEnum):
    FULL = "FULL"
    INCREMENTAL = "INCREMENTAL"
    BACKFILL = "BACKFILL"
    REPAIR = "REPAIR"


class SyncGranularity(StrEnum):
    DATE = "DATE"
    SYMBOL = "SYMBOL"
    DATE_SYMBOL = "DATE_SYMBOL"
    EXCHANGE = "EXCHANGE"


class BatchType(StrEnum):
    DATE = "DATE"
    SYMBOL = "SYMBOL"
    DATE_RANGE = "DATE_RANGE"
    PAGE = "PAGE"


class LayerCode(StrEnum):
    RAW = "RAW"
    STAGING = "STAGING"
    CORE = "CORE"


class QualitySeverity(StrEnum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    FATAL = "FATAL"


class AdjustType(StrEnum):
    RAW = "RAW"
    FORWARD = "FORWARD"
    BACKWARD = "BACKWARD"


class SyncStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"