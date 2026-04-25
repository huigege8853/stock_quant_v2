from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import text
from sqlalchemy.orm import Session

from stock_quant_v2.trading_domain.dto.paper_position import PaperPositionCreateDTO
from stock_quant_v2.trading_domain.dto.portfolio_snapshot import (
    PaperPortfolioSnapshotCreateDTO,
)
from stock_quant_v2.trading_domain.repositories.paper_position_repository import (
    PaperPositionRepository,
)
from stock_quant_v2.trading_domain.repositories.portfolio_snapshot_repository import (
    PortfolioSnapshotRepository,
)


class PaperPositionSnapshotService:
    def __init__(self, session: Session):
        self.session = session
        self.position_repo = PaperPositionRepository(session)
        self.snapshot_repo = PortfolioSnapshotRepository(session)

    def build_positions_and_snapshot_from_fills(
        self,
        run_id: int,
        fill_run_id: int,
        portfolio_id: int,
        snapshot_date: date,
    ):
        portfolio = self._load_portfolio(portfolio_id)

        fills = self._load_completed_fills(
            fill_run_id=fill_run_id,
            portfolio_id=portfolio_id,
            fill_date=snapshot_date,
        )

        if not fills:
            raise ValueError(
                "no completed paper fills found. "
                f"fill_run_id={fill_run_id}, "
                f"portfolio_id={portfolio_id}, "
                f"snapshot_date={snapshot_date}"
            )

        instrument_ids = sorted({int(row["instrument_id"]) for row in fills})

        close_prices = self._load_close_prices(
            instrument_ids=instrument_ids,
            trade_date=snapshot_date,
        )

        if not close_prices:
            raise ValueError(
                "no close prices found for portfolio snapshot. "
                f"snapshot_date={snapshot_date}"
            )

        self.position_repo.delete_by_run_portfolio_date(
            run_id=run_id,
            portfolio_id=portfolio_id,
            position_date=snapshot_date,
        )

        position_items = self._build_position_items(
            run_id=run_id,
            portfolio_id=portfolio_id,
            position_date=snapshot_date,
            fills=fills,
            close_prices=close_prices,
        )

        positions = self.position_repo.bulk_create(position_items)

        snapshot = self._build_snapshot(
            run_id=run_id,
            fill_run_id=fill_run_id,
            portfolio_id=portfolio_id,
            snapshot_date=snapshot_date,
            initial_cash=Decimal(str(portfolio["initial_cash"])),
            positions=positions,
        )

        self.session.flush()

        return positions, snapshot

    def _load_portfolio(self, portfolio_id: int) -> dict:
        row = self.session.execute(
            text(
                """
                select *
                from trading_paper_portfolio
                where id = :portfolio_id
                """
            ),
            {"portfolio_id": portfolio_id},
        ).mappings().one_or_none()

        if row is None:
            raise ValueError(f"paper portfolio not found: {portfolio_id}")

        return dict(row)

    def _load_completed_fills(
        self,
        fill_run_id: int,
        portfolio_id: int,
        fill_date: date,
    ) -> list[dict]:
        rows = self.session.execute(
            text(
                """
                select
                    id,
                    instrument_id,
                    fill_price,
                    fill_quantity,
                    gross_amount,
                    total_fee_amount,
                    net_amount,
                    cash_delta,
                    fill_status
                from trading_paper_fill
                where run_id = :fill_run_id
                  and portfolio_id = :portfolio_id
                  and fill_date = :fill_date
                  and fill_status = 'COMPLETED'
                order by instrument_id, id
                """
            ),
            {
                "fill_run_id": fill_run_id,
                "portfolio_id": portfolio_id,
                "fill_date": fill_date,
            },
        ).mappings().all()

        return [dict(row) for row in rows]

    def _build_position_items(
        self,
        run_id: int,
        portfolio_id: int,
        position_date: date,
        fills: list[dict],
        close_prices: dict[int, Decimal],
    ) -> list[PaperPositionCreateDTO]:
        grouped: dict[int, dict[str, Decimal]] = {}

        for fill in fills:
            instrument_id = int(fill["instrument_id"])
            qty = Decimal(str(fill["fill_quantity"]))
            net_amount = Decimal(str(fill["net_amount"]))

            if instrument_id not in grouped:
                grouped[instrument_id] = {
                    "quantity": Decimal("0"),
                    "cost_amount": Decimal("0"),
                }

            grouped[instrument_id]["quantity"] += qty
            grouped[instrument_id]["cost_amount"] += net_amount

        items: list[PaperPositionCreateDTO] = []

        for instrument_id, values in grouped.items():
            quantity = values["quantity"].quantize(Decimal("0.00000001"))
            cost_amount = values["cost_amount"].quantize(Decimal("0.00000001"))

            if quantity <= 0:
                continue

            market_price = close_prices.get(instrument_id)
            if market_price is None:
                raise ValueError(
                    f"missing close price for instrument_id={instrument_id}, "
                    f"position_date={position_date}"
                )

            avg_cost = self._safe_div(cost_amount, quantity)
            market_value = (quantity * market_price).quantize(Decimal("0.00000001"))
            unrealized_pnl = (market_value - cost_amount).quantize(
                Decimal("0.00000001")
            )
            realized_pnl = Decimal("0.00000000")
            total_pnl = unrealized_pnl

            items.append(
                PaperPositionCreateDTO(
                    run_id=run_id,
                    portfolio_id=portfolio_id,
                    instrument_id=instrument_id,
                    position_date=position_date,
                    quantity=quantity,
                    available_quantity=Decimal("0.00000000"),
                    frozen_quantity=Decimal("0.00000000"),
                    avg_cost=avg_cost,
                    cost_amount=cost_amount,
                    market_price=market_price,
                    market_value=market_value,
                    unrealized_pnl=unrealized_pnl,
                    realized_pnl=realized_pnl,
                    total_pnl=total_pnl,
                    position_status="OPEN",
                )
            )

        return items

    def _build_snapshot(
        self,
        run_id: int,
        fill_run_id: int,
        portfolio_id: int,
        snapshot_date: date,
        initial_cash: Decimal,
        positions,
    ):
        fill_cash_delta = self.session.execute(
            text(
                """
                select coalesce(sum(cash_delta), 0)
                from trading_paper_fill
                where run_id = :fill_run_id
                  and portfolio_id = :portfolio_id
                  and fill_date = :snapshot_date
                  and fill_status = 'COMPLETED'
                """
            ),
            {
                "fill_run_id": fill_run_id,
                "portfolio_id": portfolio_id,
                "snapshot_date": snapshot_date,
            },
        ).scalar_one()

        cash_balance = (initial_cash + Decimal(str(fill_cash_delta))).quantize(
            Decimal("0.00000001")
        )

        market_value = sum(
            Decimal(str(position.market_value)) for position in positions
        ).quantize(Decimal("0.00000001"))

        total_equity = (cash_balance + market_value).quantize(Decimal("0.00000001"))

        holding_count = sum(
            1 for position in positions if Decimal(str(position.quantity)) > 0
        )

        turnover_amount = self.session.execute(
            text(
                """
                select coalesce(sum(abs(gross_amount)), 0)
                from trading_paper_fill
                where run_id = :fill_run_id
                  and portfolio_id = :portfolio_id
                  and fill_date = :snapshot_date
                  and fill_status = 'COMPLETED'
                """
            ),
            {
                "fill_run_id": fill_run_id,
                "portfolio_id": portfolio_id,
                "snapshot_date": snapshot_date,
            },
        ).scalar_one()

        turnover_amount = Decimal(str(turnover_amount)).quantize(Decimal("0.00000001"))

        daily_pnl = (total_equity - initial_cash).quantize(Decimal("0.00000001"))
        cumulative_pnl = daily_pnl

        daily_return = self._safe_div(daily_pnl, initial_cash)
        cumulative_return = daily_return
        turnover_rate = self._safe_div(turnover_amount, total_equity)

        snapshot_dto = PaperPortfolioSnapshotCreateDTO(
            run_id=run_id,
            portfolio_id=portfolio_id,
            snapshot_date=snapshot_date,
            cash_balance=cash_balance,
            market_value=market_value,
            total_equity=total_equity,
            gross_exposure=market_value,
            net_exposure=market_value,
            holding_count=holding_count,
            daily_pnl=daily_pnl,
            cumulative_pnl=cumulative_pnl,
            daily_return=daily_return,
            cumulative_return=cumulative_return,
            turnover_amount=turnover_amount,
            turnover_rate=turnover_rate,
        )

        return self.snapshot_repo.replace(snapshot_dto)

    def _load_close_prices(
        self,
        instrument_ids: list[int],
        trade_date: date,
    ) -> dict[int, Decimal]:
        if not instrument_ids:
            return {}

        columns = self._get_table_columns("core_daily_bar")

        close_col = self._pick_first_existing_column(
            columns,
            ["close_price", "close", "close_px"],
        )

        if close_col is None:
            raise ValueError(
                "cannot find close price column in core_daily_bar. "
                f"columns={sorted(columns)}"
            )

        rows = self.session.execute(
            text(
                f"""
                select
                    instrument_id,
                    {close_col} as close_price
                from core_daily_bar
                where trade_date = :trade_date
                  and instrument_id = any(:instrument_ids)
                  and {close_col} is not null
                """
            ),
            {
                "trade_date": trade_date,
                "instrument_ids": instrument_ids,
            },
        ).mappings().all()

        result: dict[int, Decimal] = {}
        for row in rows:
            result[int(row["instrument_id"])] = Decimal(str(row["close_price"]))

        return result

    def _get_table_columns(self, table_name: str) -> set[str]:
        rows = self.session.execute(
            text(
                """
                select column_name
                from information_schema.columns
                where table_schema = 'public'
                  and table_name = :table_name
                """
            ),
            {"table_name": table_name},
        ).all()

        return {row[0] for row in rows}

    @staticmethod
    def _pick_first_existing_column(
        columns: set[str],
        candidates: list[str],
    ) -> str | None:
        for candidate in candidates:
            if candidate in columns:
                return candidate
        return None

    @staticmethod
    def _safe_div(numerator: Decimal, denominator: Decimal) -> Decimal:
        if denominator == 0:
            return Decimal("0.0000000000")
        return (numerator / denominator).quantize(
            Decimal("0.0000000001"),
            rounding=ROUND_HALF_UP,
        )