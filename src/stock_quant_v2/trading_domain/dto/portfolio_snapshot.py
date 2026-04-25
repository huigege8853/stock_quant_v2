from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class PaperPortfolioSnapshotCreateDTO:
    run_id: int
    portfolio_id: int
    snapshot_date: date
    cash_balance: Decimal
    market_value: Decimal
    total_equity: Decimal
    gross_exposure: Decimal
    net_exposure: Decimal
    holding_count: int
    daily_pnl: Decimal | None
    cumulative_pnl: Decimal | None
    daily_return: Decimal | None
    cumulative_return: Decimal | None
    turnover_amount: Decimal | None
    turnover_rate: Decimal | None


@dataclass(frozen=True, kw_only=True)
class PaperPortfolioSnapshotDTO(PaperPortfolioSnapshotCreateDTO):
    id: int