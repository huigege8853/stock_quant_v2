from __future__ import annotations

DEFAULT_PROVIDER_PRIORITY = [
    "baostock",
    "sina",
    "akshare",
    "pytdx",
    "tushare",
    "paid",
    "skip",
]

MARKET_DATA_PROVIDER_PRIORITY = [
    "baostock",
    "sina",
    "akshare",
    "pytdx",
    "tushare",
    "paid",
    "skip",
]

DAILY_BAR_PROVIDER_PRIORITY = [
    "baostock",
    "sina",
    "akshare",
    "pytdx",
    "tushare",
    "paid",
    "skip",
]

MARKET_INDEX_BAR_PROVIDER_PRIORITY = [
    "baostock",
    "sina",
    "akshare",
    "pytdx",
    "tushare",
    "paid",
    "skip",
]

TRADING_CALENDAR_PROVIDER_PRIORITY = [
    "baostock",
    "tushare",
    "akshare",
    "paid",
    "skip",
]

ADJUST_FACTOR_PROVIDER_PRIORITY = [
    "baostock",
    "akshare",
    "tushare",
    "paid",
    "skip",
]

MARKET_INDEX_PROVIDER_PRIORITY = [
    "baostock",
    "sina",
    "akshare",
    "pytdx",
    "tushare",
    "paid",
    "skip",
]

FUNDAMENTAL_SNAPSHOT_PROVIDER_PRIORITY = [
    "akshare",
    "baostock",
    "sina",
    "pytdx",
    "tushare",
    "paid",
    "skip",
]

INSTRUMENT_PROVIDER_PRIORITY = [
    "akshare",
    "tushare",
    "baostock",
    "paid",
    "skip",
]

TOPIC_PROVIDER_PRIORITY: dict[str, list[str]] = {
    "market_data": MARKET_DATA_PROVIDER_PRIORITY,
    "daily_bar": DAILY_BAR_PROVIDER_PRIORITY,
    "market_index_bar": MARKET_INDEX_BAR_PROVIDER_PRIORITY,
    "trading_calendar": TRADING_CALENDAR_PROVIDER_PRIORITY,
    "adjust_factor": ADJUST_FACTOR_PROVIDER_PRIORITY,
    "market_index": MARKET_INDEX_PROVIDER_PRIORITY,
    "fundamental_snapshot": FUNDAMENTAL_SNAPSHOT_PROVIDER_PRIORITY,
    "instrument": INSTRUMENT_PROVIDER_PRIORITY,
}


def _normalize_dataset_code(dataset_code: str) -> str:
    return str(dataset_code).strip().lower()


def get_provider_priority(dataset_code: str) -> list[str]:
    normalized = _normalize_dataset_code(dataset_code)
    return list(TOPIC_PROVIDER_PRIORITY.get(normalized, DEFAULT_PROVIDER_PRIORITY))


def get_enabled_provider_priority(
    dataset_code: str,
    disabled_providers: set[str] | None = None,
) -> list[str]:
    priority = get_provider_priority(dataset_code)
    disabled = {str(item).strip().lower() for item in (disabled_providers or set())}
    return [provider for provider in priority if provider.lower() not in disabled]


def should_disable_tushare(
    *,
    has_token: bool,
    has_permission: bool,
) -> bool:
    return (not has_token) or (not has_permission)


def build_disabled_provider_set(
    *,
    tushare_enabled: bool,
    extra_disabled: set[str] | None = None,
) -> set[str]:
    disabled = {str(item).strip().lower() for item in (extra_disabled or set())}
    if not tushare_enabled:
        disabled.add("tushare")
    return disabled