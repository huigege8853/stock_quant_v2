from datetime import date

from sqlalchemy.orm import Session

from stock_quant_v2.db.models.trading import TradingPaperPosition
from stock_quant_v2.trading_domain.dto.paper_position import PaperPositionCreateDTO


class PaperPositionRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_by_run(
        self,
        run_id: int,
        portfolio_id: int | None = None,
    ) -> list[TradingPaperPosition]:
        query = self.session.query(TradingPaperPosition).filter(
            TradingPaperPosition.run_id == run_id
        )
        if portfolio_id is not None:
            query = query.filter(TradingPaperPosition.portfolio_id == portfolio_id)
        return query.order_by(
            TradingPaperPosition.position_date,
            TradingPaperPosition.instrument_id,
        ).all()

    def list_by_portfolio_date(
        self,
        portfolio_id: int,
        position_date: date,
    ) -> list[TradingPaperPosition]:
        return (
            self.session.query(TradingPaperPosition)
            .filter(
                TradingPaperPosition.portfolio_id == portfolio_id,
                TradingPaperPosition.position_date == position_date,
            )
            .order_by(TradingPaperPosition.instrument_id)
            .all()
        )

    def delete_by_run_portfolio_date(
        self,
        run_id: int,
        portfolio_id: int,
        position_date: date,
    ) -> int:
        deleted = (
            self.session.query(TradingPaperPosition)
            .filter(
                TradingPaperPosition.run_id == run_id,
                TradingPaperPosition.portfolio_id == portfolio_id,
                TradingPaperPosition.position_date == position_date,
            )
            .delete(synchronize_session=False)
        )
        self.session.flush()
        return deleted

    def bulk_create(
        self,
        items: list[PaperPositionCreateDTO],
    ) -> list[TradingPaperPosition]:
        objs = [
            TradingPaperPosition(
                run_id=dto.run_id,
                portfolio_id=dto.portfolio_id,
                instrument_id=dto.instrument_id,
                position_date=dto.position_date,
                quantity=dto.quantity,
                available_quantity=dto.available_quantity,
                frozen_quantity=dto.frozen_quantity,
                avg_cost=dto.avg_cost,
                cost_amount=dto.cost_amount,
                market_price=dto.market_price,
                market_value=dto.market_value,
                unrealized_pnl=dto.unrealized_pnl,
                realized_pnl=dto.realized_pnl,
                total_pnl=dto.total_pnl,
                position_status=dto.position_status,
            )
            for dto in items
        ]
        self.session.add_all(objs)
        self.session.flush()
        return objs