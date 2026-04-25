from datetime import date
from decimal import Decimal, ROUND_DOWN

from sqlalchemy import text
from sqlalchemy.orm import Session

from stock_quant_v2.trading_domain.constants import (
    DEFAULT_ORDER_TYPE,
    DEFAULT_PRICE_FILL_RULE,
    DEFAULT_TIME_IN_FORCE,
)
from stock_quant_v2.trading_domain.dto.paper_order import PaperOrderCreateDTO
from stock_quant_v2.trading_domain.repositories.paper_order_repository import (
    PaperOrderRepository,
)
from stock_quant_v2.trading_domain.repositories.target_position_repository import (
    TargetPositionRepository,
)


class PaperOrderService:
    def __init__(self, session: Session):
        self.session = session
        self.order_repo = PaperOrderRepository(session)
        self.target_repo = TargetPositionRepository(session)

    def generate_orders_from_target_positions(
        self,
        order_run_id: int,
        target_run_id: int,
        portfolio_id: int,
        effective_date: date,
    ):
        portfolio = self._load_portfolio(portfolio_id)
        exec_profile = self._load_execution_profile(
            int(portfolio["execution_assumption_profile_id"])
        )

        targets = self._load_targets(
            target_run_id=target_run_id,
            portfolio_id=portfolio_id,
            effective_date=effective_date,
        )

        if not targets:
            raise ValueError(
                "no pending target_position rows found. "
                f"target_run_id={target_run_id}, "
                f"portfolio_id={portfolio_id}, "
                f"effective_date={effective_date}"
            )

        # ---- 关键修复 1：M6 只允许首次建仓，不允许在已有组合上重复跑 ----
        snapshot_state = self._load_latest_snapshot_state_or_initial_cash(
            portfolio_id=portfolio_id,
            effective_date=effective_date,
            initial_cash=Decimal(str(portfolio["initial_cash"])),
        )

        if snapshot_state["snapshot_date"] is not None:
            raise RuntimeError(
                "M6 first chain detected an existing portfolio state before effective_date. "
                f"portfolio_id={portfolio_id}, "
                f"effective_date={effective_date}, "
                f"latest_snapshot_date={snapshot_state['snapshot_date']}, "
                f"cash_balance={snapshot_state['cash_balance']}, "
                f"total_equity={snapshot_state['total_equity']}. "
                "M6 is initial-build only. Use M7 rebalance / carry chain for subsequent trade dates."
            )

        instrument_ids = [int(row["instrument_id"]) for row in targets]

        prices = self._load_order_estimate_prices(
            instrument_ids=instrument_ids,
            effective_date=effective_date,
        )

        # ---- 关键修复 2：首次建仓也只能用现金，不是 total_equity ----
        total_equity = Decimal(str(snapshot_state["total_equity"]))
        remaining_cash = Decimal(str(snapshot_state["cash_balance"]))

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
        lot_size = self._int_from_profile(
            exec_profile,
            ["lot_size"],
            100,
        )

        order_items: list[PaperOrderCreateDTO] = []
        ordered_target_ids: list[int] = []
        skipped_reasons: dict[str, int] = {}

        for target in targets:
            target_id = int(target["id"])
            instrument_id = int(target["instrument_id"])
            target_weight = Decimal(str(target["target_weight"]))

            estimate_price = prices.get(instrument_id)
            if estimate_price is None or estimate_price <= 0:
                reason = "MISSING_ESTIMATE_PRICE"
                skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
                self._mark_target_skipped(target_id=target_id, reason=reason)
                continue

            estimated_price = self._apply_buy_slippage(
                estimate_price=estimate_price,
                slippage_bps=slippage_bps,
            )

            target_budget = (total_equity * target_weight).quantize(
                Decimal("0.00000001")
            )
            budget = min(target_budget, remaining_cash)

            order_quantity = self._calc_strict_cash_buy_quantity(
                budget=budget,
                price=estimated_price,
                lot_size=lot_size,
                commission_rate=commission_rate,
                min_commission=min_commission,
                transfer_fee_rate=transfer_fee_rate,
            )

            if order_quantity <= 0:
                reason = "INSUFFICIENT_CASH_OR_LOT_SIZE"
                skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
                self._mark_target_skipped(target_id=target_id, reason=reason)
                continue

            gross_amount = (estimated_price * order_quantity).quantize(
                Decimal("0.00000001")
            )
            estimated_fee = self._estimate_buy_fee(
                gross_amount=gross_amount,
                commission_rate=commission_rate,
                min_commission=min_commission,
                transfer_fee_rate=transfer_fee_rate,
            )
            estimated_net_amount = (gross_amount + estimated_fee).quantize(
                Decimal("0.00000001")
            )

            if estimated_net_amount > remaining_cash:
                reason = "STRICT_CASH_BLOCKED"
                skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
                self._mark_target_skipped(target_id=target_id, reason=reason)
                continue

            order_items.append(
                PaperOrderCreateDTO(
                    run_id=order_run_id,
                    portfolio_id=portfolio_id,
                    target_position_id=target_id,
                    instrument_id=instrument_id,
                    order_date=effective_date,
                    effective_date=effective_date,
                    order_side="BUY",
                    order_type=DEFAULT_ORDER_TYPE,
                    price_fill_rule=DEFAULT_PRICE_FILL_RULE,
                    time_in_force=DEFAULT_TIME_IN_FORCE,
                    target_quantity=None,
                    order_quantity=order_quantity,
                    estimated_price=estimated_price,
                    estimated_gross_amount=gross_amount,
                    estimated_fee=estimated_fee,
                    estimated_net_amount=estimated_net_amount,
                    status="ACCEPTED",
                    reject_reason=None,
                )
            )

            ordered_target_ids.append(target_id)
            remaining_cash = (remaining_cash - estimated_net_amount).quantize(
                Decimal("0.00000001")
            )

        if not order_items:
            raise ValueError(
                "no paper orders generated. "
                f"target_run_id={target_run_id}, "
                f"portfolio_id={portfolio_id}, "
                f"effective_date={effective_date}, "
                f"skipped_reasons={skipped_reasons}"
            )

        orders = self.order_repo.bulk_create(order_items)

        if ordered_target_ids:
            self.target_repo.mark_ordered(ordered_target_ids)

        self.session.flush()
        return orders

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

    def _load_targets(
        self,
        target_run_id: int,
        portfolio_id: int,
        effective_date: date,
    ) -> list[dict]:
        rows = self.session.execute(
            text(
                """
                select
                    id,
                    instrument_id,
                    target_weight,
                    rank_no,
                    status
                from trading_paper_target_position
                where run_id = :target_run_id
                  and portfolio_id = :portfolio_id
                  and effective_date = :effective_date
                  and status = 'PENDING'
                order by rank_no asc nulls last, instrument_id asc
                """
            ),
            {
                "target_run_id": target_run_id,
                "portfolio_id": portfolio_id,
                "effective_date": effective_date,
            },
        ).mappings().all()

        return [dict(row) for row in rows]

    def _load_order_estimate_prices(
        self,
        instrument_ids: list[int],
        effective_date: date,
    ) -> dict[int, Decimal]:
        if not instrument_ids:
            return {}

        columns = self._get_table_columns("core_daily_bar")

        open_col = self._pick_first_existing_column(
            columns,
            ["open_price", "open", "open_px"],
        )
        close_col = self._pick_first_existing_column(
            columns,
            ["close_price", "close", "close_px"],
        )

        if open_col is None and close_col is None:
            raise ValueError(
                "cannot find open/close price columns in core_daily_bar. "
                f"columns={sorted(columns)}"
            )

        result: dict[int, Decimal] = {}

        if open_col is not None:
            open_rows = self.session.execute(
                text(
                    f"""
                    select
                        instrument_id,
                        {open_col} as price
                    from core_daily_bar
                    where trade_date = :effective_date
                      and instrument_id = any(:instrument_ids)
                      and {open_col} is not null
                    """
                ),
                {
                    "effective_date": effective_date,
                    "instrument_ids": instrument_ids,
                },
            ).mappings().all()

            for row in open_rows:
                result[int(row["instrument_id"])] = Decimal(str(row["price"]))

        missing_ids = [iid for iid in instrument_ids if iid not in result]

        if missing_ids and close_col is not None:
            close_rows = self.session.execute(
                text(
                    f"""
                    select distinct on (instrument_id)
                        instrument_id,
                        {close_col} as price
                    from core_daily_bar
                    where trade_date < :effective_date
                      and instrument_id = any(:instrument_ids)
                      and {close_col} is not null
                    order by instrument_id, trade_date desc
                    """
                ),
                {
                    "effective_date": effective_date,
                    "instrument_ids": missing_ids,
                },
            ).mappings().all()

            for row in close_rows:
                result[int(row["instrument_id"])] = Decimal(str(row["price"]))

        return result

    def _load_latest_snapshot_state_or_initial_cash(
        self,
        portfolio_id: int,
        effective_date: date,
        initial_cash: Decimal,
    ) -> dict:
        row = self.session.execute(
            text(
                """
                select
                    snapshot_date,
                    cash_balance,
                    total_equity
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
        ).mappings().one_or_none()

        if row is None:
            return {
                "snapshot_date": None,
                "cash_balance": initial_cash,
                "total_equity": initial_cash,
            }

        return {
            "snapshot_date": row["snapshot_date"],
            "cash_balance": Decimal(str(row["cash_balance"])),
            "total_equity": Decimal(str(row["total_equity"])),
        }

    def _mark_target_skipped(self, target_id: int, reason: str) -> None:
        self.session.execute(
            text(
                """
                update trading_paper_target_position
                set status = 'SKIPPED',
                    status_reason = :reason,
                    updated_at = now()
                where id = :target_id
                """
            ),
            {
                "target_id": target_id,
                "reason": reason,
            },
        )

    @staticmethod
    def _apply_buy_slippage(
        estimate_price: Decimal,
        slippage_bps: Decimal,
    ) -> Decimal:
        multiplier = Decimal("1") + (slippage_bps / Decimal("10000"))
        return (estimate_price * multiplier).quantize(Decimal("0.00000001"))

    @staticmethod
    def _calc_strict_cash_buy_quantity(
        budget: Decimal,
        price: Decimal,
        lot_size: int,
        commission_rate: Decimal,
        min_commission: Decimal,
        transfer_fee_rate: Decimal,
    ) -> Decimal:
        if budget <= 0 or price <= 0:
            return Decimal("0")

        raw_qty = (budget / price).to_integral_value(rounding=ROUND_DOWN)
        lot = Decimal(str(lot_size))
        qty = (raw_qty // lot) * lot

        while qty > 0:
            gross_amount = (price * qty).quantize(Decimal("0.00000001"))
            fee = PaperOrderService._estimate_buy_fee(
                gross_amount=gross_amount,
                commission_rate=commission_rate,
                min_commission=min_commission,
                transfer_fee_rate=transfer_fee_rate,
            )
            total_cost = (gross_amount + fee).quantize(Decimal("0.00000001"))

            if total_cost <= budget:
                return qty

            qty -= lot

        return Decimal("0")

    @staticmethod
    def _estimate_buy_fee(
        gross_amount: Decimal,
        commission_rate: Decimal,
        min_commission: Decimal,
        transfer_fee_rate: Decimal,
    ) -> Decimal:
        commission = gross_amount * commission_rate
        if commission < min_commission:
            commission = min_commission

        transfer_fee = gross_amount * transfer_fee_rate
        return (commission + transfer_fee).quantize(Decimal("0.00000001"))

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

    @staticmethod
    def _int_from_profile(
        profile: dict,
        keys: list[str],
        default: int,
    ) -> int:
        for key in keys:
            value = profile.get(key)
            if value is not None:
                return int(value)
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