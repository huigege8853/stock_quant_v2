from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from stock_quant_v2.trading_domain.constants import (
    DEFAULT_INITIAL_CASH,
    DEFAULT_PAPER_PORTFOLIO_CODE,
    DEFAULT_PORTFOLIO_CONSTRUCTION_MODE,
    DEFAULT_REBALANCE_FREQUENCY,
    DEFAULT_TARGET_COUNT,
)
from stock_quant_v2.trading_domain.dto.paper_portfolio import PaperPortfolioCreateDTO
from stock_quant_v2.trading_domain.repositories.paper_portfolio_repository import (
    PaperPortfolioRepository,
)


class PaperPortfolioService:
    def __init__(self, session: Session):
        self.session = session
        self.portfolio_repo = PaperPortfolioRepository(session)

    def get_or_create_default_portfolio(
        self,
        account_id: int,
        strategy_version_id: int,
        execution_assumption_profile_id: int,
        source_signal_run_id: int | None,
        source_screen_request_id: int | None,
        start_date: date,
        portfolio_code: str = DEFAULT_PAPER_PORTFOLIO_CODE,
        portfolio_name: str = "Alpha Selection v1 Default Paper Portfolio",
        initial_cash: Decimal = DEFAULT_INITIAL_CASH,
        max_position_count: int = DEFAULT_TARGET_COUNT,
    ):
        dto = PaperPortfolioCreateDTO(
            account_id=account_id,
            portfolio_code=portfolio_code,
            portfolio_name=portfolio_name,
            strategy_version_id=strategy_version_id,
            execution_assumption_profile_id=execution_assumption_profile_id,
            source_signal_run_id=source_signal_run_id,
            source_screen_request_id=source_screen_request_id,
            portfolio_construction_mode=DEFAULT_PORTFOLIO_CONSTRUCTION_MODE,
            rebalance_frequency=DEFAULT_REBALANCE_FREQUENCY,
            max_position_count=max_position_count,
            long_only=True,
            initial_cash=initial_cash,
            start_date=start_date,
            end_date=None,
            status="ACTIVE",
        )
        return self.portfolio_repo.get_or_create(dto)