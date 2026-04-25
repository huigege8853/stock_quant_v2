from sqlalchemy.orm import Session

from stock_quant_v2.db.models.trading import TradingPaperTradeLedger
from stock_quant_v2.trading_domain.dto.trade_ledger import PaperTradeLedgerCreateDTO


class TradeLedgerRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, dto: PaperTradeLedgerCreateDTO) -> TradingPaperTradeLedger:
        obj = TradingPaperTradeLedger(
            run_id=dto.run_id,
            portfolio_id=dto.portfolio_id,
            event_date=dto.event_date,
            event_type=dto.event_type,
            instrument_id=dto.instrument_id,
            target_position_id=dto.target_position_id,
            order_id=dto.order_id,
            fill_id=dto.fill_id,
            position_id=dto.position_id,
            portfolio_snapshot_id=dto.portfolio_snapshot_id,
            quantity_delta=dto.quantity_delta,
            cash_delta=dto.cash_delta,
            amount_delta=dto.amount_delta,
            reason_code=dto.reason_code,
            message=dto.message,
            payload_json=dto.payload_json,
        )
        self.session.add(obj)
        self.session.flush()
        return obj

    def bulk_create(
        self,
        items: list[PaperTradeLedgerCreateDTO],
    ) -> list[TradingPaperTradeLedger]:
        objs = [
            TradingPaperTradeLedger(
                run_id=dto.run_id,
                portfolio_id=dto.portfolio_id,
                event_date=dto.event_date,
                event_type=dto.event_type,
                instrument_id=dto.instrument_id,
                target_position_id=dto.target_position_id,
                order_id=dto.order_id,
                fill_id=dto.fill_id,
                position_id=dto.position_id,
                portfolio_snapshot_id=dto.portfolio_snapshot_id,
                quantity_delta=dto.quantity_delta,
                cash_delta=dto.cash_delta,
                amount_delta=dto.amount_delta,
                reason_code=dto.reason_code,
                message=dto.message,
                payload_json=dto.payload_json,
            )
            for dto in items
        ]
        self.session.add_all(objs)
        self.session.flush()
        return objs