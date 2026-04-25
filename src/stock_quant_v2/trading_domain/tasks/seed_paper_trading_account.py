from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from stock_quant_v2.trading_domain.constants import (
    DEFAULT_INITIAL_CASH,
    DEFAULT_PAPER_ACCOUNT_CODE,
    DEFAULT_PAPER_PORTFOLIO_CODE,
)
from stock_quant_v2.trading_domain.services.paper_account_service import (
    PaperAccountService,
)
from stock_quant_v2.trading_domain.services.paper_portfolio_service import (
    PaperPortfolioService,
)


@dataclass(frozen=True)
class SeedPaperTradingAccountRequest:
    account_code: str
    portfolio_code: str
    strategy_version_id: int
    execution_assumption_profile_id: int
    source_signal_run_id: int | None
    source_screen_request_id: int | None
    start_date: date
    initial_cash: Decimal


@dataclass(frozen=True)
class SeedPaperTradingAccountResult:
    account_id: int
    account_code: str
    portfolio_id: int
    portfolio_code: str
    strategy_version_id: int
    execution_assumption_profile_id: int
    source_signal_run_id: int | None
    source_screen_request_id: int | None
    initial_cash: Decimal
    status: str


def seed_paper_trading_account(
    session: Session,
    request: SeedPaperTradingAccountRequest,
) -> SeedPaperTradingAccountResult:
    account_service = PaperAccountService(session)
    portfolio_service = PaperPortfolioService(session)

    account = account_service.get_or_create_default_account(
        account_code=request.account_code or DEFAULT_PAPER_ACCOUNT_CODE,
        initial_cash=request.initial_cash or DEFAULT_INITIAL_CASH,
    )

    portfolio = portfolio_service.get_or_create_default_portfolio(
        account_id=account.id,
        strategy_version_id=request.strategy_version_id,
        execution_assumption_profile_id=request.execution_assumption_profile_id,
        source_signal_run_id=request.source_signal_run_id,
        source_screen_request_id=request.source_screen_request_id,
        start_date=request.start_date,
        portfolio_code=request.portfolio_code or DEFAULT_PAPER_PORTFOLIO_CODE,
        initial_cash=request.initial_cash or DEFAULT_INITIAL_CASH,
    )

    session.flush()

    return SeedPaperTradingAccountResult(
        account_id=account.id,
        account_code=account.account_code,
        portfolio_id=portfolio.id,
        portfolio_code=portfolio.portfolio_code,
        strategy_version_id=portfolio.strategy_version_id,
        execution_assumption_profile_id=portfolio.execution_assumption_profile_id,
        source_signal_run_id=portfolio.source_signal_run_id,
        source_screen_request_id=portfolio.source_screen_request_id,
        initial_cash=portfolio.initial_cash,
        status="SUCCESS",
    )