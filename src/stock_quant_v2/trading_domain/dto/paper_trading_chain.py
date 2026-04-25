from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class PaperTradingFirstChainRequestDTO:
    signal_run_id: int
    screen_request_id: int
    as_of_date: date
    effective_date: date
    initial_cash: Decimal
    execution_assumption_profile_id: int
    strategy_version_id: int
    target_count: int = 30
    portfolio_construction_mode: str = "EQUAL_WEIGHT_SELECTED"


@dataclass(frozen=True)
class PaperTradingFirstChainResultDTO:
    run_id: int
    account_id: int
    portfolio_id: int
    target_position_count: int
    order_count: int
    fill_count: int
    position_count: int
    snapshot_id: int | None
    status: str