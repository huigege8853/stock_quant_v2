from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from stock_quant_v2.trading_domain.dto.paper_fill import PaperFillCreateDTO
from stock_quant_v2.trading_domain.repositories.paper_fill_repository import (
    PaperFillRepository,
)
from stock_quant_v2.trading_domain.repositories.paper_order_repository import (
    PaperOrderRepository,
)

class PaperFillService:
    def __init__(self, session: Session):
        self.session = session
        self.fill_repo = PaperFillRepository(session)
        self.order_repo = PaperOrderRepository(session)

    def simulate_fills_from_orders(
        self,
        fill_run_id: int,
        order_run_id: int,
        portfolio_id: int,
        effective_date: date,
    ):
        portfolio = self._load_portfolio(portfolio_id)
        exec_profile = self._load_execution_profile(
            int(portfolio["execution_assumption_profile_id"])
        )

        orders = self._load_accepted_orders(
            order_run_id=order_run_id,
            portfolio_id=portfolio_id,
            effective_date=effective_date,
        )

        if not orders:
            raise ValueError(
                "no ACCEPTED paper orders found. "
                f"order_run_id={order_run_id}, "
                f"portfolio_id={portfolio_id}, "
                f"effective_date={effective_date}"
            )

        instrument_ids = [int(row["instrument_id"]) for row in orders]
        open_prices = self._load_open_prices(
            instrument_ids=instrument_ids,
            trade_date=effective_date,
        )

        if not open_prices:
            raise ValueError(
                "no NEXT_OPEN prices found for fill. "
                f"effective_date={effective_date}. "
                "M6 fill is strict NEXT_OPEN; run M2 catchup/backfill first."
            )

        available_cash = self._load_available_cash(
            portfolio_id=portfolio_id,
            effective_date=effective_date,
            initial_cash=Decimal(str(portfolio["initial_cash"])),
            fill_run_id=fill_run_id,
        )

        commission_rate = self._decimal_from_profile(
            exec_profile,
            ["commission_rate"],
            Decimal("0.0003"),
        )
        min_commission = self._decimal_from_profile(
            exec_profile,
            ["min_commission"],
            Decimal("5"),
        )
        transfer_fee_rate = self._decimal_from_profile(
            exec_profile,
            ["transfer_fee_rate"],
            Decimal("0.00001"),
        )
        slippage_bps = self._decimal_from_profile(
            exec_profile,
            ["slippage_bps"],
            Decimal("5"),
        )

        fill_items: list[PaperFillCreateDTO] = []
        filled_order_ids: list[int] = []

        for order in orders:
            order_id = int(order["id"])
            instrument_id = int(order["instrument_id"])
            quantity = Decimal(str(order["order_quantity"]))

            open_price = open_prices.get(instrument_id)
            if open_price is None or open_price <= 0:
                self.order_repo.update_status(
                    order_id=order_id,
                    status="REJECTED",
                    reject_reason="MISSING_NEXT_OPEN_PRICE",
                )
                continue

            fill_price = self._apply_buy_slippage(
                open_price=open_price,
                slippage_bps=slippage_bps,
            )

            gross_amount = (fill_price * quantity).quantize(Decimal("0.00000001"))

            commission_amount = self._estimate_commission(
                gross_amount=gross_amount,
                commission_rate=commission_rate,
                min_commission=min_commission,
            )
            stamp_duty_amount = Decimal("0.00000000")
            transfer_fee_amount = (gross_amount * transfer_fee_rate).quantize(
                Decimal("0.00000001")
            )
            slippage_amount = ((fill_price - open_price) * quantity).quantize(
                Decimal("0.00000001")
            )

            total_fee_amount = (
                commission_amount + stamp_duty_amount + transfer_fee_amount
            ).quantize(Decimal("0.00000001"))

            net_amount = (gross_amount + total_fee_amount).quantize(
                Decimal("0.00000001")
            )
            cash_delta = -net_amount

            if net_amount > available_cash:
                self.order_repo.update_status(
                    order_id=order_id,
                    status="REJECTED",
                    reject_reason="STRICT_CASH_BLOCKED_AT_FILL",
                )
                continue

            fill_items.append(
                PaperFillCreateDTO(
                    run_id=fill_run_id,
                    portfolio_id=portfolio_id,
                    order_id=order_id,
                    instrument_id=instrument_id,
                    fill_date=effective_date,
                    fill_price=fill_price,
                    fill_quantity=quantity,
                    gross_amount=gross_amount,
                    commission_amount=commission_amount,
                    stamp_duty_amount=stamp_duty_amount,
                    transfer_fee_amount=transfer_fee_amount,
                    slippage_amount=slippage_amount,
                    total_fee_amount=total_fee_amount,
                    net_amount=net_amount,
                    cash_delta=cash_delta,
                    price_source="CORE_DAILY_BAR_OPEN",
                    fill_rule="NEXT_OPEN",
                    fill_status="COMPLETED",
                )
            )

            filled_order_ids.append(order_id)
            available_cash = (available_cash - net_amount).quantize(
                Decimal("0.00000001")
            )

        if not fill_items:
            raise ValueError(
                "no paper fills generated. "
                f"fill_run_id={fill_run_id}, "
                f"order_run_id={order_run_id}, "
                f"portfolio_id={portfolio_id}, "
                f"effective_date={effective_date}"
            )

        fills = self.fill_repo.bulk_create(fill_items)

        if filled_order_ids:
            self.order_repo.bulk_mark_filled(filled_order_ids)

        self.session.flush()
        return fills

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

    def _load_execution_profile(self, execution_assumption_profile_id: int) -> dict:
        row = self.session.execute(
            text(
                """
                select *
                from research_execution_assumption_profile
                where id = :id
                """
            ),
            {"id": execution_assumption_profile_id},
        ).mappings().one_or_none()

        if row is None:
            raise ValueError(
                f"execution assumption profile not found: {execution_assumption_profile_id}"
            )

        return dict(row)

    def _load_accepted_orders(
        self,
        order_run_id: int,
        portfolio_id: int,
        effective_date: date,
    ) -> list[dict]:
        rows = self.session.execute(
            text(
                """
                select
                    id,
                    instrument_id,
                    order_quantity,
                    status
                from trading_paper_order
                where run_id = :order_run_id
                  and portfolio_id = :portfolio_id
                  and effective_date = :effective_date
                  and status = 'ACCEPTED'
                order by id asc
                """
            ),
            {
                "order_run_id": order_run_id,
                "portfolio_id": portfolio_id,
                "effective_date": effective_date,
            },
        ).mappings().all()

        return [dict(row) for row in rows]

    def _load_open_prices(
        self,
        instrument_ids: list[int],
        trade_date: date,
    ) -> dict[int, Decimal]:
        if not instrument_ids:
            return {}

        columns = self._get_table_columns("core_daily_bar")

        open_col = self._pick_first_existing_column(
            columns,
            ["open_price", "open", "open_px"],
        )
        if open_col is None:
            raise ValueError(
                "cannot find open price column in core_daily_bar. "
                f"columns={sorted(columns)}"
            )

        rows = self.session.execute(
            text(
                f"""
                select
                    instrument_id,
                    {open_col} as open_price
                from core_daily_bar
                where trade_date = :trade_date
                  and instrument_id = any(:instrument_ids)
                  and {open_col} is not null
                """
            ),
            {
                "trade_date": trade_date,
                "instrument_ids": instrument_ids,
            },
        ).mappings().all()

        result: dict[int, Decimal] = {}
        for row in rows:
            result[int(row["instrument_id"])] = Decimal(str(row["open_price"]))

        return result

    def _load_available_cash(
            self,
            portfolio_id: int,
            effective_date: date,
            initial_cash: Decimal,
            fill_run_id: int,
    ) -> Decimal:
        """
        Cash should be isolated by M6 chain.

        We use:
        - latest snapshot before effective_date, if any
        - otherwise portfolio.initial_cash

        We do NOT subtract fills from other runs on the same effective_date.
        Otherwise rerunning M6 for the same date would be contaminated by old runs.
        """
        snapshot_row = self.session.execute(
            text(
                """
                select cash_balance
                from trading_paper_portfolio_snapshot
                where portfolio_id = :portfolio_id
                  and snapshot_date < :effective_date
                order by snapshot_date desc
                limit 1
                """
            ),
            {
                "portfolio_id": portfolio_id,
                "effective_date": effective_date,
            },
        ).one_or_none()

        if snapshot_row is not None:
            base_cash = Decimal(str(snapshot_row[0]))
        else:
            base_cash = initial_cash

        current_run_cash_delta = self.session.execute(
            text(
                """
                select coalesce(sum(cash_delta), 0)
                from trading_paper_fill
                where run_id = :fill_run_id
                  and portfolio_id = :portfolio_id
                  and fill_date = :effective_date
                  and fill_status = 'COMPLETED'
                """
            ),
            {
                "fill_run_id": fill_run_id,
                "portfolio_id": portfolio_id,
                "effective_date": effective_date,
            },
        ).scalar_one()

        return (base_cash + Decimal(str(current_run_cash_delta))).quantize(
            Decimal("0.00000001")
        )

    @staticmethod
    def _apply_buy_slippage(
        open_price: Decimal,
        slippage_bps: Decimal,
    ) -> Decimal:
        multiplier = Decimal("1") + (slippage_bps / Decimal("10000"))
        return (open_price * multiplier).quantize(Decimal("0.00000001"))

    @staticmethod
    def _estimate_commission(
        gross_amount: Decimal,
        commission_rate: Decimal,
        min_commission: Decimal,
    ) -> Decimal:
        commission = gross_amount * commission_rate
        if commission < min_commission:
            commission = min_commission
        return commission.quantize(Decimal("0.00000001"))

    @staticmethod
    def _decimal_from_profile(
        profile: dict,
        keys: list[str],
        default: Decimal,
    ) -> Decimal:
        for key in keys:
            value = profile.get(key)
            if value is not None:
                return Decimal(str(value))
        return default

    def _get_table_columns(self, table_name: str) -> set[str]:
        sql = text(
            """
            select column_name
            from information_schema.columns
            where table_schema = 'public'
              and table_name = :table_name
            """
        )
        rows = self.session.execute(sql, {"table_name": table_name}).all()
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