from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

CampaignStatus = Literal["ACTIVE", "PAUSED", "COMPLETED", "FAILED"]
CampaignRunMode = Literal["auto", "m6", "m7", "skip"]


@dataclass(frozen=True)
class PaperCampaignConfig:
    """User supplied campaign configuration.

    P1 intentionally keeps campaign metadata outside the database.  The config is
    read from a local JSON file and should not be committed when it contains
    environment-specific account/portfolio choices.
    """

    campaign_code: str
    campaign_name: str
    strategy_code: str
    strategy_version_code: str = "v1"
    account_code: str | None = None
    portfolio_code: str | None = None
    account_id: int | None = None
    portfolio_id: int | None = None
    initial_cash: Decimal = Decimal("10000000")
    planned_trading_days: int = 20
    start_trade_date: date | None = None
    status: CampaignStatus = "ACTIVE"
    run_mode: CampaignRunMode = "auto"
    target_count: int = 30
    replace_existing: bool = False
    allow_main_portfolio: bool = False
    run_m9_finalizers: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def resolved_account_code(self) -> str:
        return self.account_code or f"paper_campaign_{self.campaign_code}"

    @property
    def resolved_portfolio_code(self) -> str:
        return self.portfolio_code or f"paper_campaign_{self.campaign_code}"


@dataclass(frozen=True)
class CampaignSignalSource:
    strategy_version_id: int
    signal_run_id: int
    screen_request_id: int | None
    as_of_date: date
    effective_date: date


@dataclass(frozen=True)
class CampaignExecutionPlan:
    campaign: PaperCampaignConfig
    trade_date: date
    day_no: int
    action: str
    reason: str
    portfolio_id: int | None = None
    signal_source: CampaignSignalSource | None = None


@dataclass(frozen=True)
class CampaignModuleExecution:
    step_name: str
    module_name: str
    command: list[str]
    exit_code: int
    started_at: datetime
    finished_at: datetime
    stdout_tail: str
    parsed_payloads: list[dict[str, Any]]


@dataclass(frozen=True)
class CampaignDailyResult:
    campaign_code: str
    campaign_name: str
    trade_date: date
    day_no: int
    action: str
    status: str
    reason: str
    generated_at: datetime
    portfolio_id: int | None
    portfolio_code: str
    strategy_code: str
    strategy_version_code: str
    signal_source: CampaignSignalSource | None
    module_executions: list[CampaignModuleExecution]
    artifact_paths: dict[str, str]
    extracted_run_ids: dict[str, int]


@dataclass(frozen=True)
class CampaignSummaryResult:
    campaign_code: str
    campaign_name: str
    status: str
    generated_at: datetime
    planned_trading_days: int
    completed_day_count: int
    first_trade_date: date | None
    last_trade_date: date | None
    portfolio_id: int | None
    initial_equity: Decimal | None
    final_equity: Decimal | None
    total_return: Decimal | None
    artifact_paths: dict[str, str]
