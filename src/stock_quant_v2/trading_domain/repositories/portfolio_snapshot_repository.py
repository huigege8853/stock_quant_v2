from datetime import date

from sqlalchemy.orm import Session

from stock_quant_v2.db.models.trading import TradingPaperPortfolioSnapshot
from stock_quant_v2.trading_domain.dto.portfolio_snapshot import (
    PaperPortfolioSnapshotCreateDTO,
)


class PortfolioSnapshotRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_run_portfolio_date(
        self,
        run_id: int,
        portfolio_id: int,
        snapshot_date: date,
    ) -> TradingPaperPortfolioSnapshot | None:
        return (
            self.session.query(TradingPaperPortfolioSnapshot)
            .filter(
                TradingPaperPortfolioSnapshot.run_id == run_id,
                TradingPaperPortfolioSnapshot.portfolio_id == portfolio_id,
                TradingPaperPortfolioSnapshot.snapshot_date == snapshot_date,
            )
            .one_or_none()
        )

    def create(
        self,
        dto: PaperPortfolioSnapshotCreateDTO,
    ) -> TradingPaperPortfolioSnapshot:
        obj = TradingPaperPortfolioSnapshot(
            run_id=dto.run_id,
            portfolio_id=dto.portfolio_id,
            snapshot_date=dto.snapshot_date,
            cash_balance=dto.cash_balance,
            market_value=dto.market_value,
            total_equity=dto.total_equity,
            gross_exposure=dto.gross_exposure,
            net_exposure=dto.net_exposure,
            holding_count=dto.holding_count,
            daily_pnl=dto.daily_pnl,
            cumulative_pnl=dto.cumulative_pnl,
            daily_return=dto.daily_return,
            cumulative_return=dto.cumulative_return,
            turnover_amount=dto.turnover_amount,
            turnover_rate=dto.turnover_rate,
        )
        self.session.add(obj)
        self.session.flush()
        return obj

    def replace(
        self,
        dto: PaperPortfolioSnapshotCreateDTO,
    ) -> TradingPaperPortfolioSnapshot:
        existing = self.get_by_run_portfolio_date(
            run_id=dto.run_id,
            portfolio_id=dto.portfolio_id,
            snapshot_date=dto.snapshot_date,
        )
        if existing is not None:
            self.session.delete(existing)
            self.session.flush()
        return self.create(dto)