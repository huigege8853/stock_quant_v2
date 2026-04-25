from __future__ import annotations

from datetime import date

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # database
    postgres_v2_url: str = Field(..., alias="V2_SQLALCHEMY_URL")

    # auth / vendor
    tushare_token: str | None = Field(default=None, alias="TUSHARE_TOKEN")
    tushare_enabled: bool = Field(default=False, alias="TUSHARE_ENABLED")

    # defaults
    default_market_code: str = Field(default="CN_A", alias="DEFAULT_MARKET_CODE")
    default_daily_bar_provider: str = Field(default="fallback", alias="DEFAULT_DAILY_BAR_PROVIDER")
    fallback_daily_bar_provider: str = Field(default="sina", alias="FALLBACK_DAILY_BAR_PROVIDER")

    # bootstrap date range
    bootstrap_daily_bar_start_date: date = Field(default=date(2024, 1, 1), alias="BOOTSTRAP_DAILY_BAR_START_DATE")
    bootstrap_daily_bar_end_date: date = Field(default=date(2024, 1, 31), alias="BOOTSTRAP_DAILY_BAR_END_DATE")
    bootstrap_calendar_start_date: date = Field(default=date(2010, 1, 1), alias="BOOTSTRAP_CALENDAR_START_DATE")
    bootstrap_calendar_end_date: date = Field(default=date(2030, 12, 31), alias="BOOTSTRAP_CALENDAR_END_DATE")

    # runtime
    app_env: str = Field(default="dev", alias="APP_ENV")
    debug: bool = Field(default=False, alias="DEBUG")

    # debug controls
    daily_bar_debug_mode: bool = Field(default=False, alias="DAILY_BAR_DEBUG_MODE")
    daily_bar_debug_limit_symbols: int | None = Field(default=None, alias="DAILY_BAR_DEBUG_LIMIT_SYMBOLS")

    fundamental_snapshot_debug_symbols: str | None = Field(
        default=None,
        alias="FUNDAMENTAL_SNAPSHOT_DEBUG_SYMBOLS",
    )

    # daily_bar retry / resume controls
    daily_bar_resume_enabled: bool = Field(default=True, alias="DAILY_BAR_RESUME_ENABLED")
    daily_bar_max_reconnect_attempts: int = Field(default=5, alias="DAILY_BAR_MAX_RECONNECT_ATTEMPTS")
    daily_bar_reconnect_sleep_seconds: float = Field(default=2.0, alias="DAILY_BAR_RECONNECT_SLEEP_SECONDS")
    daily_bar_fail_fast: bool = Field(default=False, alias="DAILY_BAR_FAIL_FAST")
    daily_bar_flush_every_symbols: int = Field(default=10, alias="DAILY_BAR_FLUSH_EVERY_SYMBOLS")

    # daily_bar running guard controls
    daily_bar_running_guard_enabled: bool = Field(default=True, alias="DAILY_BAR_RUNNING_GUARD_ENABLED")
    daily_bar_auto_fail_stale_running: bool = Field(default=False, alias="DAILY_BAR_AUTO_FAIL_STALE_RUNNING")
    daily_bar_stale_running_minutes: int = Field(default=180, alias="DAILY_BAR_STALE_RUNNING_MINUTES")

    # adjust_factor retry / resume controls
    adjust_factor_resume_enabled: bool = Field(default=True, alias="ADJUST_FACTOR_RESUME_ENABLED")
    adjust_factor_max_reconnect_attempts: int = Field(default=3, alias="ADJUST_FACTOR_MAX_RECONNECT_ATTEMPTS")
    adjust_factor_reconnect_sleep_seconds: float = Field(default=1.0, alias="ADJUST_FACTOR_RECONNECT_SLEEP_SECONDS")
    adjust_factor_fail_fast: bool = Field(default=False, alias="ADJUST_FACTOR_FAIL_FAST")
    adjust_factor_force_rerun: bool = Field(default=False, alias="ADJUST_FACTOR_FORCE_RERUN")

    # adjust_factor running guard controls
    adjust_factor_running_guard_enabled: bool = Field(default=True, alias="ADJUST_FACTOR_RUNNING_GUARD_ENABLED")
    adjust_factor_auto_fail_stale_running: bool = Field(default=False, alias="ADJUST_FACTOR_AUTO_FAIL_STALE_RUNNING")
    adjust_factor_stale_running_minutes: int = Field(default=180, alias="ADJUST_FACTOR_STALE_RUNNING_MINUTES")

    daily_bar_socket_timeout_seconds: float = Field(default=60.0, alias="DAILY_BAR_SOCKET_TIMEOUT_SECONDS")


    # provider priorities
    trading_calendar_provider_priority: str = Field(
        default="baostock,tushare,akshare,paid,skip",
        alias="TRADING_CALENDAR_PROVIDER_PRIORITY",
    )
    daily_bar_provider_priority: str = Field(
        default="baostock,sina,akshare,pytdx,tushare,paid,skip",
        alias="DAILY_BAR_PROVIDER_PRIORITY",
    )
    adjust_factor_provider_priority: str = Field(
        default="baostock,akshare,tushare,paid,skip",
        alias="ADJUST_FACTOR_PROVIDER_PRIORITY",
    )
    market_index_bar_provider_priority: str = Field(
        default="baostock,sina,akshare,pytdx,tushare,paid,skip",
        alias="MARKET_INDEX_BAR_PROVIDER_PRIORITY",
    )
    fundamental_snapshot_provider_priority: str = Field(
        default="akshare,baostock,sina,pytdx,tushare,paid,skip",
        alias="FUNDAMENTAL_SNAPSHOT_PROVIDER_PRIORITY",
    )

    @field_validator("daily_bar_debug_limit_symbols", mode="before")
    @classmethod
    def _normalize_empty_int(cls, v):
        if v in ("", None):
            return None
        return v

    @field_validator("daily_bar_max_reconnect_attempts")
    @classmethod
    def _validate_daily_bar_max_reconnect_attempts(cls, v: int) -> int:
        if v < 1:
            raise ValueError("DAILY_BAR_MAX_RECONNECT_ATTEMPTS must be >= 1")
        return v

    @field_validator("daily_bar_reconnect_sleep_seconds")
    @classmethod
    def _validate_daily_bar_reconnect_sleep_seconds(cls, v: float) -> float:
        if v < 0:
            raise ValueError("DAILY_BAR_RECONNECT_SLEEP_SECONDS must be >= 0")
        return v

    @field_validator("daily_bar_flush_every_symbols")
    @classmethod
    def _validate_daily_bar_flush_every_symbols(cls, v: int) -> int:
        if v < 1:
            raise ValueError("DAILY_BAR_FLUSH_EVERY_SYMBOLS must be >= 1")
        return v

    @field_validator("daily_bar_stale_running_minutes")
    @classmethod
    def _validate_daily_bar_stale_running_minutes(cls, v: int) -> int:
        if v < 1:
            raise ValueError("DAILY_BAR_STALE_RUNNING_MINUTES must be >= 1")
        return v

    @field_validator("adjust_factor_max_reconnect_attempts")
    @classmethod
    def _validate_adjust_factor_max_reconnect_attempts(cls, v: int) -> int:
        if v < 1:
            raise ValueError("ADJUST_FACTOR_MAX_RECONNECT_ATTEMPTS must be >= 1")
        return v

    @field_validator("adjust_factor_reconnect_sleep_seconds")
    @classmethod
    def _validate_adjust_factor_reconnect_sleep_seconds(cls, v: float) -> float:
        if v < 0:
            raise ValueError("ADJUST_FACTOR_RECONNECT_SLEEP_SECONDS must be >= 0")
        return v

    @field_validator("adjust_factor_stale_running_minutes")
    @classmethod
    def _validate_adjust_factor_stale_running_minutes(cls, v: int) -> int:
        if v < 1:
            raise ValueError("ADJUST_FACTOR_STALE_RUNNING_MINUTES must be >= 1")
        return v

    @field_validator("daily_bar_socket_timeout_seconds")
    @classmethod
    def _validate_daily_bar_socket_timeout_seconds(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("DAILY_BAR_SOCKET_TIMEOUT_SECONDS must be > 0")
        return v

    def get_trading_calendar_provider_priority(self) -> list[str]:
        return [x.strip() for x in self.trading_calendar_provider_priority.split(",") if x.strip()]

    def get_daily_bar_provider_priority(self) -> list[str]:
        return [x.strip() for x in self.daily_bar_provider_priority.split(",") if x.strip()]

    def get_adjust_factor_provider_priority(self) -> list[str]:
        return [x.strip() for x in self.adjust_factor_provider_priority.split(",") if x.strip()]

    def get_market_index_bar_provider_priority(self) -> list[str]:
        return [x.strip() for x in self.market_index_bar_provider_priority.split(",") if x.strip()]

    def get_fundamental_snapshot_provider_priority(self) -> list[str]:
        return [x.strip() for x in self.fundamental_snapshot_provider_priority.split(",") if x.strip()]

    def get_fundamental_snapshot_debug_symbols(self) -> list[str]:
        if not self.fundamental_snapshot_debug_symbols:
            return []
        return [
            x.strip()
            for x in self.fundamental_snapshot_debug_symbols.split(",")
            if x.strip()
        ]


settings = Settings()