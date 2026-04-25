from sqlalchemy.orm import Session

from stock_quant_v2.db.models.trading import TradingPaperPortfolio
from stock_quant_v2.trading_domain.dto.paper_portfolio import PaperPortfolioCreateDTO


class PaperPortfolioRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, portfolio_id: int) -> TradingPaperPortfolio | None:
        return (
            self.session.query(TradingPaperPortfolio)
            .filter(TradingPaperPortfolio.id == portfolio_id)
            .one_or_none()
        )

    def get_by_code(self, portfolio_code: str) -> TradingPaperPortfolio | None:
        return (
            self.session.query(TradingPaperPortfolio)
            .filter(TradingPaperPortfolio.portfolio_code == portfolio_code)
            .one_or_none()
        )

    def create(self, dto: PaperPortfolioCreateDTO) -> TradingPaperPortfolio:
        obj = TradingPaperPortfolio(
            account_id=dto.account_id,
            portfolio_code=dto.portfolio_code,
            portfolio_name=dto.portfolio_name,
            strategy_version_id=dto.strategy_version_id,
            execution_assumption_profile_id=dto.execution_assumption_profile_id,
            source_signal_run_id=dto.source_signal_run_id,
            source_screen_request_id=dto.source_screen_request_id,
            portfolio_construction_mode=dto.portfolio_construction_mode,
            rebalance_frequency=dto.rebalance_frequency,
            max_position_count=dto.max_position_count,
            long_only=dto.long_only,
            initial_cash=dto.initial_cash,
            start_date=dto.start_date,
            end_date=dto.end_date,
            status=dto.status,
        )
        self.session.add(obj)
        self.session.flush()
        return obj

    def get_or_create(self, dto: PaperPortfolioCreateDTO) -> TradingPaperPortfolio:
        existing = self.get_by_code(dto.portfolio_code)
        if existing is not None:
            return existing
        return self.create(dto)

    def activate(self, portfolio_id: int) -> TradingPaperPortfolio:
        obj = self.get_by_id(portfolio_id)
        if obj is None:
            raise ValueError(f"paper portfolio not found: {portfolio_id}")
        obj.status = "ACTIVE"
        self.session.flush()
        return obj