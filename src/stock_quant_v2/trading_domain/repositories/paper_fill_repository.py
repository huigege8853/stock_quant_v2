from datetime import date

from sqlalchemy.orm import Session

from stock_quant_v2.db.models.trading import TradingPaperFill
from stock_quant_v2.trading_domain.dto.paper_fill import PaperFillCreateDTO


class PaperFillRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_by_run(
        self,
        run_id: int,
        portfolio_id: int | None = None,
    ) -> list[TradingPaperFill]:
        query = self.session.query(TradingPaperFill).filter(
            TradingPaperFill.run_id == run_id
        )
        if portfolio_id is not None:
            query = query.filter(TradingPaperFill.portfolio_id == portfolio_id)
        return query.order_by(
            TradingPaperFill.fill_date,
            TradingPaperFill.instrument_id,
        ).all()

    def list_by_portfolio_date(
        self,
        portfolio_id: int,
        fill_date: date,
    ) -> list[TradingPaperFill]:
        return (
            self.session.query(TradingPaperFill)
            .filter(
                TradingPaperFill.portfolio_id == portfolio_id,
                TradingPaperFill.fill_date == fill_date,
            )
            .order_by(TradingPaperFill.instrument_id)
            .all()
        )

    def bulk_create(self, items: list[PaperFillCreateDTO]) -> list[TradingPaperFill]:
        objs = [
            TradingPaperFill(
                run_id=dto.run_id,
                portfolio_id=dto.portfolio_id,
                order_id=dto.order_id,
                instrument_id=dto.instrument_id,
                fill_date=dto.fill_date,
                fill_price=dto.fill_price,
                fill_quantity=dto.fill_quantity,
                gross_amount=dto.gross_amount,
                commission_amount=dto.commission_amount,
                stamp_duty_amount=dto.stamp_duty_amount,
                transfer_fee_amount=dto.transfer_fee_amount,
                slippage_amount=dto.slippage_amount,
                total_fee_amount=dto.total_fee_amount,
                net_amount=dto.net_amount,
                cash_delta=dto.cash_delta,
                price_source=dto.price_source,
                fill_rule=dto.fill_rule,
                fill_status=dto.fill_status,
            )
            for dto in items
        ]
        self.session.add_all(objs)
        self.session.flush()
        return objs