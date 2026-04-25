from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class PaperPortfolioCreateDTO:
    account_id: int
    portfolio_code: str
    portfolio_name: str
    strategy_version_id: int
    execution_assumption_profile_id: int
    source_signal_run_id: int | None
    source_screen_request_id: int | None
    portfolio_construction_mode: str
    rebalance_frequency: str
    max_position_count: int
    long_only: bool
    initial_cash: Decimal
    start_date: date
    end_date: date | None = None
    status: str = "CREATED"


@dataclass(frozen=True)
class PaperPortfolioDTO:
    id: int
    account_id: int
    portfolio_code: str
    portfolio_name: str
    strategy_version_id: int
    execution_assumption_profile_id: int
    source_signal_run_id: int | None
    source_screen_request_id: int | None
    portfolio_construction_mode: str
    rebalance_frequency: str
    max_position_count: int
    long_only: bool
    initial_cash: Decimal
    start_date: date
    end_date: date | None
    status: str