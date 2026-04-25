from datetime import date

from sqlalchemy.orm import Session

from stock_quant_v2.db.models.trading import TradingPaperOrder
from stock_quant_v2.trading_domain.dto.paper_order import PaperOrderCreateDTO


class PaperOrderRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, order_id: int) -> TradingPaperOrder | None:
        return (
            self.session.query(TradingPaperOrder)
            .filter(TradingPaperOrder.id == order_id)
            .one_or_none()
        )

    def list_by_run(
        self,
        run_id: int,
        portfolio_id: int | None = None,
    ) -> list[TradingPaperOrder]:
        query = self.session.query(TradingPaperOrder).filter(
            TradingPaperOrder.run_id == run_id
        )
        if portfolio_id is not None:
            query = query.filter(TradingPaperOrder.portfolio_id == portfolio_id)
        return query.order_by(
            TradingPaperOrder.effective_date,
            TradingPaperOrder.instrument_id,
        ).all()

    def list_by_portfolio_date(
        self,
        portfolio_id: int,
        effective_date: date,
    ) -> list[TradingPaperOrder]:
        return (
            self.session.query(TradingPaperOrder)
            .filter(
                TradingPaperOrder.portfolio_id == portfolio_id,
                TradingPaperOrder.effective_date == effective_date,
            )
            .order_by(TradingPaperOrder.instrument_id)
            .all()
        )

    def bulk_create(self, items: list[PaperOrderCreateDTO]) -> list[TradingPaperOrder]:
        objs = [
            TradingPaperOrder(
                run_id=dto.run_id,
                portfolio_id=dto.portfolio_id,
                target_position_id=dto.target_position_id,
                instrument_id=dto.instrument_id,
                order_date=dto.order_date,
                effective_date=dto.effective_date,
                order_side=dto.order_side,
                order_type=dto.order_type,
                price_fill_rule=dto.price_fill_rule,
                time_in_force=dto.time_in_force,
                target_quantity=dto.target_quantity,
                order_quantity=dto.order_quantity,
                estimated_price=dto.estimated_price,
                estimated_gross_amount=dto.estimated_gross_amount,
                estimated_fee=dto.estimated_fee,
                estimated_net_amount=dto.estimated_net_amount,
                status=dto.status,
                reject_reason=dto.reject_reason,
            )
            for dto in items
        ]
        self.session.add_all(objs)
        self.session.flush()
        return objs

    def update_status(
        self,
        order_id: int,
        status: str,
        reject_reason: str | None = None,
    ) -> TradingPaperOrder:
        obj = self.get_by_id(order_id)
        if obj is None:
            raise ValueError(f"paper order not found: {order_id}")
        obj.status = status
        obj.reject_reason = reject_reason
        self.session.flush()
        return obj

    def bulk_mark_filled(self, order_ids: list[int]) -> int:
        if not order_ids:
            return 0
        updated = (
            self.session.query(TradingPaperOrder)
            .filter(TradingPaperOrder.id.in_(order_ids))
            .update(
                {TradingPaperOrder.status: "FILLED"},
                synchronize_session=False,
            )
        )
        self.session.flush()
        return updated