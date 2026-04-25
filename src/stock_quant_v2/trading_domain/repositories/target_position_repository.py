from datetime import date

from sqlalchemy.orm import Session

from stock_quant_v2.db.models.trading import TradingPaperTargetPosition
from stock_quant_v2.trading_domain.dto.target_position import PaperTargetPositionCreateDTO


class TargetPositionRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_by_run(
        self,
        run_id: int,
        portfolio_id: int | None = None,
    ) -> list[TradingPaperTargetPosition]:
        query = self.session.query(TradingPaperTargetPosition).filter(
            TradingPaperTargetPosition.run_id == run_id
        )
        if portfolio_id is not None:
            query = query.filter(TradingPaperTargetPosition.portfolio_id == portfolio_id)
        return query.order_by(
            TradingPaperTargetPosition.effective_date,
            TradingPaperTargetPosition.rank_no,
            TradingPaperTargetPosition.instrument_id,
        ).all()

    def list_by_portfolio_date(
        self,
        portfolio_id: int,
        effective_date: date,
    ) -> list[TradingPaperTargetPosition]:
        return (
            self.session.query(TradingPaperTargetPosition)
            .filter(
                TradingPaperTargetPosition.portfolio_id == portfolio_id,
                TradingPaperTargetPosition.effective_date == effective_date,
            )
            .order_by(
                TradingPaperTargetPosition.rank_no,
                TradingPaperTargetPosition.instrument_id,
            )
            .all()
        )

    def delete_by_run_portfolio_date(
        self,
        run_id: int,
        portfolio_id: int,
        effective_date: date,
    ) -> int:
        deleted = (
            self.session.query(TradingPaperTargetPosition)
            .filter(
                TradingPaperTargetPosition.run_id == run_id,
                TradingPaperTargetPosition.portfolio_id == portfolio_id,
                TradingPaperTargetPosition.effective_date == effective_date,
            )
            .delete(synchronize_session=False)
        )
        self.session.flush()
        return deleted

    def bulk_create(
        self,
        items: list[PaperTargetPositionCreateDTO],
    ) -> list[TradingPaperTargetPosition]:
        objs = [
            TradingPaperTargetPosition(
                run_id=dto.run_id,
                portfolio_id=dto.portfolio_id,
                source_signal_run_id=dto.source_signal_run_id,
                source_screen_request_id=dto.source_screen_request_id,
                strategy_signal_id=dto.strategy_signal_id,
                as_of_date=dto.as_of_date,
                effective_date=dto.effective_date,
                instrument_id=dto.instrument_id,
                target_side=dto.target_side,
                target_weight=dto.target_weight,
                target_amount=dto.target_amount,
                target_quantity=dto.target_quantity,
                rank_no=dto.rank_no,
                score=dto.score,
                reason_code=dto.reason_code,
                target_source=dto.target_source,
                construction_mode=dto.construction_mode,
                status=dto.status,
                status_reason=dto.status_reason,
            )
            for dto in items
        ]
        self.session.add_all(objs)
        self.session.flush()
        return objs

    def mark_ordered(self, target_position_ids: list[int]) -> int:
        if not target_position_ids:
            return 0
        updated = (
            self.session.query(TradingPaperTargetPosition)
            .filter(TradingPaperTargetPosition.id.in_(target_position_ids))
            .update(
                {TradingPaperTargetPosition.status: "ORDERED"},
                synchronize_session=False,
            )
        )
        self.session.flush()
        return updated