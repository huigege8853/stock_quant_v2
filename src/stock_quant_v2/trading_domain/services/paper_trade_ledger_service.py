from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from stock_quant_v2.trading_domain.dto.trade_ledger import PaperTradeLedgerCreateDTO
from stock_quant_v2.trading_domain.repositories.trade_ledger_repository import (
    TradeLedgerRepository,
)


class PaperTradeLedgerService:
    def __init__(self, session: Session):
        self.session = session
        self.ledger_repo = TradeLedgerRepository(session)

    def build_ledger_for_chain(
        self,
        ledger_run_id: int,
        portfolio_id: int,
        target_run_id: int,
        order_run_id: int,
        fill_run_id: int,
        position_snapshot_run_id: int,
    ):
        snapshot_date = self._resolve_snapshot_date(
            run_id=position_snapshot_run_id,
            portfolio_id=portfolio_id,
        )

        self._delete_existing_ledger(ledger_run_id=ledger_run_id)

        items: list[PaperTradeLedgerCreateDTO] = []

        items.extend(
            self._build_target_events(
                ledger_run_id=ledger_run_id,
                portfolio_id=portfolio_id,
                target_run_id=target_run_id,
            )
        )

        items.extend(
            self._build_order_events(
                ledger_run_id=ledger_run_id,
                portfolio_id=portfolio_id,
                order_run_id=order_run_id,
            )
        )

        items.extend(
            self._build_fill_events(
                ledger_run_id=ledger_run_id,
                portfolio_id=portfolio_id,
                fill_run_id=fill_run_id,
            )
        )

        items.extend(
            self._build_position_events(
                ledger_run_id=ledger_run_id,
                portfolio_id=portfolio_id,
                position_snapshot_run_id=position_snapshot_run_id,
            )
        )

        items.extend(
            self._build_snapshot_events(
                ledger_run_id=ledger_run_id,
                portfolio_id=portfolio_id,
                position_snapshot_run_id=position_snapshot_run_id,
            )
        )

        items.append(
            PaperTradeLedgerCreateDTO(
                run_id=ledger_run_id,
                portfolio_id=portfolio_id,
                event_date=snapshot_date,
                event_type="QUALITY_CHECKED",
                reason_code="M6_QUALITY_PASS",
                message="M6 paper trading minimal chain quality check passed.",
                payload_json={
                    "target_run_id": target_run_id,
                    "order_run_id": order_run_id,
                    "fill_run_id": fill_run_id,
                    "position_snapshot_run_id": position_snapshot_run_id,
                    "quality_status": "PASS",
                },
            )
        )

        ledgers = self.ledger_repo.bulk_create(items)
        self.session.flush()
        return ledgers

    def _delete_existing_ledger(self, ledger_run_id: int) -> None:
        self.session.execute(
            text(
                """
                delete from trading_paper_trade_ledger
                where run_id = :ledger_run_id
                """
            ),
            {"ledger_run_id": ledger_run_id},
        )
        self.session.flush()

    def _resolve_snapshot_date(self, run_id: int, portfolio_id: int) -> date:
        value = self.session.execute(
            text(
                """
                select snapshot_date
                from trading_paper_portfolio_snapshot
                where run_id = :run_id
                  and portfolio_id = :portfolio_id
                limit 1
                """
            ),
            {
                "run_id": run_id,
                "portfolio_id": portfolio_id,
            },
        ).scalar_one_or_none()

        if value is None:
            raise ValueError(
                f"snapshot not found: run_id={run_id}, portfolio_id={portfolio_id}"
            )

        return value

    def _build_target_events(
        self,
        ledger_run_id: int,
        portfolio_id: int,
        target_run_id: int,
    ) -> list[PaperTradeLedgerCreateDTO]:
        rows = self.session.execute(
            text(
                """
                select
                    id,
                    instrument_id,
                    effective_date,
                    target_side,
                    target_weight,
                    rank_no,
                    score,
                    reason_code,
                    status
                from trading_paper_target_position
                where run_id = :target_run_id
                  and portfolio_id = :portfolio_id
                order by rank_no asc nulls last, id asc
                """
            ),
            {
                "target_run_id": target_run_id,
                "portfolio_id": portfolio_id,
            },
        ).mappings().all()

        return [
            PaperTradeLedgerCreateDTO(
                run_id=ledger_run_id,
                portfolio_id=portfolio_id,
                event_date=row["effective_date"],
                event_type="TARGET_CREATED",
                instrument_id=row["instrument_id"],
                target_position_id=row["id"],
                reason_code=row["reason_code"],
                message="Paper target position created from strategy signal.",
                payload_json={
                    "target_run_id": target_run_id,
                    "target_side": row["target_side"],
                    "target_weight": str(row["target_weight"]),
                    "rank_no": row["rank_no"],
                    "score": str(row["score"]) if row["score"] is not None else None,
                    "status": row["status"],
                },
            )
            for row in rows
        ]

    def _build_order_events(
        self,
        ledger_run_id: int,
        portfolio_id: int,
        order_run_id: int,
    ) -> list[PaperTradeLedgerCreateDTO]:
        rows = self.session.execute(
            text(
                """
                select
                    id,
                    target_position_id,
                    instrument_id,
                    effective_date,
                    order_side,
                    order_type,
                    price_fill_rule,
                    order_quantity,
                    estimated_net_amount,
                    status
                from trading_paper_order
                where run_id = :order_run_id
                  and portfolio_id = :portfolio_id
                order by id asc
                """
            ),
            {
                "order_run_id": order_run_id,
                "portfolio_id": portfolio_id,
            },
        ).mappings().all()

        return [
            PaperTradeLedgerCreateDTO(
                run_id=ledger_run_id,
                portfolio_id=portfolio_id,
                event_date=row["effective_date"],
                event_type="ORDER_ACCEPTED",
                instrument_id=row["instrument_id"],
                target_position_id=row["target_position_id"],
                order_id=row["id"],
                quantity_delta=Decimal(str(row["order_quantity"])),
                amount_delta=Decimal(str(row["estimated_net_amount"])),
                reason_code="PAPER_ORDER_ACCEPTED",
                message="Paper order accepted.",
                payload_json={
                    "order_run_id": order_run_id,
                    "order_side": row["order_side"],
                    "order_type": row["order_type"],
                    "price_fill_rule": row["price_fill_rule"],
                    "status": row["status"],
                },
            )
            for row in rows
        ]

    def _build_fill_events(
        self,
        ledger_run_id: int,
        portfolio_id: int,
        fill_run_id: int,
    ) -> list[PaperTradeLedgerCreateDTO]:
        rows = self.session.execute(
            text(
                """
                select
                    id,
                    order_id,
                    instrument_id,
                    fill_date,
                    fill_quantity,
                    fill_price,
                    net_amount,
                    cash_delta,
                    fill_status
                from trading_paper_fill
                where run_id = :fill_run_id
                  and portfolio_id = :portfolio_id
                order by id asc
                """
            ),
            {
                "fill_run_id": fill_run_id,
                "portfolio_id": portfolio_id,
            },
        ).mappings().all()

        return [
            PaperTradeLedgerCreateDTO(
                run_id=ledger_run_id,
                portfolio_id=portfolio_id,
                event_date=row["fill_date"],
                event_type="FILL_COMPLETED",
                instrument_id=row["instrument_id"],
                order_id=row["order_id"],
                fill_id=row["id"],
                quantity_delta=Decimal(str(row["fill_quantity"])),
                cash_delta=Decimal(str(row["cash_delta"])),
                amount_delta=Decimal(str(row["net_amount"])),
                reason_code="PAPER_FILL_COMPLETED",
                message="Paper order filled by strict NEXT_OPEN simulation.",
                payload_json={
                    "fill_run_id": fill_run_id,
                    "fill_price": str(row["fill_price"]),
                    "fill_status": row["fill_status"],
                },
            )
            for row in rows
        ]

    def _build_position_events(
        self,
        ledger_run_id: int,
        portfolio_id: int,
        position_snapshot_run_id: int,
    ) -> list[PaperTradeLedgerCreateDTO]:
        rows = self.session.execute(
            text(
                """
                select
                    id,
                    instrument_id,
                    position_date,
                    quantity,
                    available_quantity,
                    avg_cost,
                    market_price,
                    market_value,
                    unrealized_pnl,
                    position_status
                from trading_paper_position
                where run_id = :position_snapshot_run_id
                  and portfolio_id = :portfolio_id
                order by id asc
                """
            ),
            {
                "position_snapshot_run_id": position_snapshot_run_id,
                "portfolio_id": portfolio_id,
            },
        ).mappings().all()

        return [
            PaperTradeLedgerCreateDTO(
                run_id=ledger_run_id,
                portfolio_id=portfolio_id,
                event_date=row["position_date"],
                event_type="POSITION_UPDATED",
                instrument_id=row["instrument_id"],
                position_id=row["id"],
                quantity_delta=Decimal(str(row["quantity"])),
                amount_delta=Decimal(str(row["market_value"])),
                reason_code="POSITION_FROM_COMPLETED_FILL",
                message="Paper position updated from completed fills.",
                payload_json={
                    "position_snapshot_run_id": position_snapshot_run_id,
                    "available_quantity": str(row["available_quantity"]),
                    "avg_cost": str(row["avg_cost"]),
                    "market_price": str(row["market_price"]),
                    "unrealized_pnl": str(row["unrealized_pnl"]),
                    "position_status": row["position_status"],
                },
            )
            for row in rows
        ]

    def _build_snapshot_events(
        self,
        ledger_run_id: int,
        portfolio_id: int,
        position_snapshot_run_id: int,
    ) -> list[PaperTradeLedgerCreateDTO]:
        rows = self.session.execute(
            text(
                """
                select
                    id,
                    snapshot_date,
                    cash_balance,
                    market_value,
                    total_equity,
                    holding_count,
                    daily_pnl,
                    daily_return
                from trading_paper_portfolio_snapshot
                where run_id = :position_snapshot_run_id
                  and portfolio_id = :portfolio_id
                order by id asc
                """
            ),
            {
                "position_snapshot_run_id": position_snapshot_run_id,
                "portfolio_id": portfolio_id,
            },
        ).mappings().all()

        return [
            PaperTradeLedgerCreateDTO(
                run_id=ledger_run_id,
                portfolio_id=portfolio_id,
                event_date=row["snapshot_date"],
                event_type="SNAPSHOT_CREATED",
                portfolio_snapshot_id=row["id"],
                cash_delta=Decimal(str(row["cash_balance"])),
                amount_delta=Decimal(str(row["total_equity"])),
                reason_code="EOD_PORTFOLIO_SNAPSHOT",
                message="End-of-day paper portfolio snapshot created.",
                payload_json={
                    "position_snapshot_run_id": position_snapshot_run_id,
                    "cash_balance": str(row["cash_balance"]),
                    "market_value": str(row["market_value"]),
                    "total_equity": str(row["total_equity"]),
                    "holding_count": row["holding_count"],
                    "daily_pnl": str(row["daily_pnl"]),
                    "daily_return": str(row["daily_return"]),
                },
            )
            for row in rows
        ]