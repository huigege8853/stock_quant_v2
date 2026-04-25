from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


ORDER_TABLE = "trading_paper_order"
FILL_TABLE = "trading_paper_fill"
DAILY_BAR_TABLE = "core_daily_bar"
SNAPSHOT_TABLE = "trading_paper_portfolio_snapshot"


@dataclass(frozen=True)
class RebalanceFillResult:
    fill_run_id: int
    order_run_id: int
    portfolio_id: int
    effective_date: str
    order_count: int
    inserted_fill_count: int
    buy_fill_count: int
    sell_fill_count: int
    rejected_buy_count: int
    starting_cash_balance: str
    ending_cash_balance: str
    total_buy_gross_amount: str
    total_sell_gross_amount: str
    total_commission: str
    total_stamp_duty: str
    total_slippage_amount: str
    total_cash_delta: str
    status: str


class PaperRebalanceFillService:
    """
    M7.3-A: 将 M7.2 生成的 BUY / SELL rebalance order 模拟成交为 fill。

    严格现金规则：
    1. SELL 先成交，先释放现金；
    2. BUY 再成交；
    3. 任意 BUY 若会导致 available_cash < 0，则拒单（REJECTED）；
    4. fill 阶段只写 trading_paper_fill，不直接写 snapshot。
    """

    def __init__(self, session: Session):
        self.session = session

    def simulate_rebalance_fills(
        self,
        *,
        fill_run_id: int,
        order_run_id: int,
        portfolio_id: int,
        effective_date: date,
        commission_rate: Decimal = Decimal("0.0003"),
        min_commission: Decimal = Decimal("5"),
        stamp_duty_rate: Decimal = Decimal("0.001"),
        slippage_rate: Decimal = Decimal("0"),
        replace_existing: bool = False,
    ) -> RebalanceFillResult:
        order_columns = self._get_columns(ORDER_TABLE)
        fill_columns = self._get_columns(FILL_TABLE)
        fill_column_meta = self._get_column_meta(FILL_TABLE)

        security_key = self._resolve_security_key(order_columns, fill_columns)
        order_quantity_col = self._resolve_quantity_col(
            order_columns,
            ["order_quantity", "quantity", "requested_quantity"],
            ORDER_TABLE,
        )
        order_side_col = self._resolve_side_col(order_columns)

        existing_count = self._count_fills(
            fill_run_id=fill_run_id,
            portfolio_id=portfolio_id,
        )
        if existing_count > 0:
            if not replace_existing:
                raise RuntimeError(
                    f"目标 fill_run 已存在成交记录: fill_run_id={fill_run_id}, "
                    f"portfolio_id={portfolio_id}, count={existing_count}. "
                    f"如确认重跑，请设置 M7_REPLACE_EXISTING=true。"
                )
            self._delete_fills(fill_run_id=fill_run_id, portfolio_id=portfolio_id)

        orders = self._load_orders(
            order_run_id=order_run_id,
            portfolio_id=portfolio_id,
            order_quantity_col=order_quantity_col,
            order_side_col=order_side_col,
        )

        available_cash = self._load_available_cash(
            portfolio_id=portfolio_id,
            effective_date=effective_date,
        )
        starting_cash_balance = available_cash

        # 先卖后买，优先释放现金
        orders = sorted(
            orders,
            key=lambda row: 0 if str(row[order_side_col]).upper() == "SELL" else 1,
        )

        inserted_fill_count = 0
        buy_fill_count = 0
        sell_fill_count = 0
        rejected_buy_count = 0

        total_buy_gross_amount = Decimal("0")
        total_sell_gross_amount = Decimal("0")
        total_commission = Decimal("0")
        total_stamp_duty = Decimal("0")
        total_slippage_amount = Decimal("0")
        total_cash_delta = Decimal("0")

        for order in orders:
            side = str(order[order_side_col]).upper()
            quantity = self._to_decimal(order[order_quantity_col])

            if side not in {"BUY", "SELL"}:
                continue

            if quantity <= 0:
                continue

            instrument_id = order.get(security_key)

            fill_price = self._resolve_next_open_price(
                instrument_id=instrument_id,
                effective_date=effective_date,
                fallback_price=self._to_decimal(order.get("estimated_price")),
            )

            gross_amount = self._money(quantity * fill_price)
            commission = self._calc_commission(
                gross_amount=gross_amount,
                commission_rate=commission_rate,
                min_commission=min_commission,
            )
            stamp_duty = (
                self._money(gross_amount * stamp_duty_rate)
                if side == "SELL"
                else Decimal("0")
            )
            slippage_amount = self._money(gross_amount * slippage_rate)

            if side == "BUY":
                cash_required = self._money(
                    gross_amount + commission + slippage_amount
                )
                cash_delta = -cash_required
                net_amount = cash_required

                # 严格现金约束：买入后现金不能小于 0
                if available_cash + cash_delta < Decimal("0"):
                    self._mark_order_rejected(
                        order_id=order.get("id"),
                        order_columns=order_columns,
                        reject_reason="STRICT_CASH_BLOCKED_AT_FILL",
                    )
                    rejected_buy_count += 1
                    continue

                available_cash = self._money(available_cash + cash_delta)
                buy_fill_count += 1
                total_buy_gross_amount += gross_amount

            else:
                cash_delta = self._money(
                    gross_amount - commission - stamp_duty - slippage_amount
                )
                net_amount = cash_delta
                available_cash = self._money(available_cash + cash_delta)

                sell_fill_count += 1
                total_sell_gross_amount += gross_amount

            total_commission += commission
            total_stamp_duty += stamp_duty
            total_slippage_amount += slippage_amount
            total_cash_delta += cash_delta

            payload = self._build_fill_payload(
                fill_columns=fill_columns,
                fill_column_meta=fill_column_meta,
                fill_run_id=fill_run_id,
                order_run_id=order_run_id,
                portfolio_id=portfolio_id,
                effective_date=effective_date,
                security_key=security_key,
                order=order,
                side=side,
                quantity=quantity,
                fill_price=fill_price,
                gross_amount=gross_amount,
                commission=commission,
                stamp_duty=stamp_duty,
                slippage_amount=slippage_amount,
                net_amount=net_amount,
                cash_delta=cash_delta,
            )
            self._insert_fill(payload)
            self._mark_order_filled(
                order_id=order.get("id"),
                order_columns=order_columns,
                order_quantity_col=order_quantity_col,
                quantity=quantity,
            )

            inserted_fill_count += 1

        return RebalanceFillResult(
            fill_run_id=fill_run_id,
            order_run_id=order_run_id,
            portfolio_id=portfolio_id,
            effective_date=effective_date.isoformat(),
            order_count=len(orders),
            inserted_fill_count=inserted_fill_count,
            buy_fill_count=buy_fill_count,
            sell_fill_count=sell_fill_count,
            rejected_buy_count=rejected_buy_count,
            starting_cash_balance=str(starting_cash_balance),
            ending_cash_balance=str(available_cash),
            total_buy_gross_amount=str(total_buy_gross_amount),
            total_sell_gross_amount=str(total_sell_gross_amount),
            total_commission=str(total_commission),
            total_stamp_duty=str(total_stamp_duty),
            total_slippage_amount=str(total_slippage_amount),
            total_cash_delta=str(total_cash_delta),
            status="SUCCESS",
        )

    def _get_columns(self, table_name: str) -> list[str]:
        rows = self.session.execute(
            text(
                """
                select column_name
                from information_schema.columns
                where table_schema = 'public'
                  and table_name = :table_name
                order by ordinal_position
                """
            ),
            {"table_name": table_name},
        ).mappings().all()
        return [row["column_name"] for row in rows]

    def _get_column_meta(self, table_name: str) -> dict[str, dict[str, Any]]:
        rows = self.session.execute(
            text(
                """
                select
                    column_name,
                    data_type,
                    is_nullable,
                    column_default
                from information_schema.columns
                where table_schema = 'public'
                  and table_name = :table_name
                """
            ),
            {"table_name": table_name},
        ).mappings().all()

        return {row["column_name"]: dict(row) for row in rows}

    def _resolve_security_key(self, order_columns: list[str], fill_columns: list[str]) -> str:
        for col in ["instrument_id", "security_id", "ticker", "symbol", "instrument_code"]:
            if col in order_columns and col in fill_columns:
                return col
        raise RuntimeError("无法识别 order / fill 共同证券键")

    def _resolve_quantity_col(
        self,
        columns: list[str],
        candidates: list[str],
        table_name: str,
    ) -> str:
        for col in candidates:
            if col in columns:
                return col
        raise RuntimeError(f"{table_name} 无法识别数量字段: {candidates}")

    def _resolve_side_col(self, columns: list[str]) -> str:
        for col in ["order_side", "side", "direction", "order_direction"]:
            if col in columns:
                return col
        raise RuntimeError(f"{ORDER_TABLE} 无法识别买卖方向字段")

    def _count_fills(self, *, fill_run_id: int, portfolio_id: int) -> int:
        row = self.session.execute(
            text(
                f"""
                select count(*) as cnt
                from {FILL_TABLE}
                where run_id = :fill_run_id
                  and portfolio_id = :portfolio_id
                """
            ),
            {"fill_run_id": fill_run_id, "portfolio_id": portfolio_id},
        ).mappings().one()
        return int(row["cnt"] or 0)

    def _delete_fills(self, *, fill_run_id: int, portfolio_id: int) -> int:
        result = self.session.execute(
            text(
                f"""
                delete from {FILL_TABLE}
                where run_id = :fill_run_id
                  and portfolio_id = :portfolio_id
                """
            ),
            {"fill_run_id": fill_run_id, "portfolio_id": portfolio_id},
        )
        return int(result.rowcount or 0)

    def _load_orders(
        self,
        *,
        order_run_id: int,
        portfolio_id: int,
        order_quantity_col: str,
        order_side_col: str,
    ) -> list[dict[str, Any]]:
        rows = self.session.execute(
            text(
                f"""
                select *
                from {ORDER_TABLE}
                where run_id = :order_run_id
                  and portfolio_id = :portfolio_id
                  and coalesce({order_quantity_col}, 0) > 0
                  and {order_side_col} in ('BUY', 'SELL')
                order by id
                """
            ),
            {"order_run_id": order_run_id, "portfolio_id": portfolio_id},
        ).mappings().all()
        return [dict(row) for row in rows]

    def _load_available_cash(
        self,
        *,
        portfolio_id: int,
        effective_date: date,
    ) -> Decimal:
        row = self.session.execute(
            text(
                f"""
                select cash_balance
                from {SNAPSHOT_TABLE}
                where portfolio_id = :portfolio_id
                  and snapshot_date < :effective_date
                order by snapshot_date desc, run_id desc
                limit 1
                """
            ),
            {
                "portfolio_id": portfolio_id,
                "effective_date": effective_date,
            },
        ).scalar_one_or_none()

        if row is None:
            return Decimal("0")

        return self._to_decimal(row)

    def _resolve_next_open_price(
        self,
        *,
        instrument_id: Any,
        effective_date: date,
        fallback_price: Decimal,
    ) -> Decimal:
        daily_bar_columns = self._get_columns(DAILY_BAR_TABLE)

        if "instrument_id" not in daily_bar_columns:
            if fallback_price > 0:
                return fallback_price
            raise RuntimeError(f"{DAILY_BAR_TABLE} 缺少 instrument_id")

        date_col = None
        for col in ["trade_date", "bar_date", "date"]:
            if col in daily_bar_columns:
                date_col = col
                break

        if not date_col:
            if fallback_price > 0:
                return fallback_price
            raise RuntimeError(f"{DAILY_BAR_TABLE} 无法识别交易日期字段")

        price_col = None
        for col in ["open_price", "open", "adj_open", "open_adj"]:
            if col in daily_bar_columns:
                price_col = col
                break

        if not price_col:
            if fallback_price > 0:
                return fallback_price
            raise RuntimeError(f"{DAILY_BAR_TABLE} 无法识别开盘价字段")

        row = self.session.execute(
            text(
                f"""
                select {price_col} as open_price
                from {DAILY_BAR_TABLE}
                where instrument_id = :instrument_id
                  and {date_col} = :effective_date
                limit 1
                """
            ),
            {
                "instrument_id": instrument_id,
                "effective_date": effective_date,
            },
        ).mappings().first()

        if row is not None:
            price = self._to_decimal(row["open_price"])
            if price > 0:
                return price

        if fallback_price > 0:
            return fallback_price

        raise RuntimeError(
            f"无法取得 NEXT_OPEN 价格: instrument_id={instrument_id}, effective_date={effective_date}"
        )

    def _build_fill_payload(
        self,
        *,
        fill_columns: list[str],
        fill_column_meta: dict[str, dict[str, Any]],
        fill_run_id: int,
        order_run_id: int,
        portfolio_id: int,
        effective_date: date,
        security_key: str,
        order: dict[str, Any],
        side: str,
        quantity: Decimal,
        fill_price: Decimal,
        gross_amount: Decimal,
        commission: Decimal,
        stamp_duty: Decimal,
        slippage_amount: Decimal,
        net_amount: Decimal,
        cash_delta: Decimal,
    ) -> dict[str, Any]:
        now = datetime.utcnow()
        payload: dict[str, Any] = {}

        skip_columns = {"id", "created_id", "updated_id"}

        for column in fill_columns:
            if column in skip_columns:
                continue

            if column == "run_id":
                payload[column] = fill_run_id
            elif column == "portfolio_id":
                payload[column] = portfolio_id
            elif column in {"order_id", "paper_order_id"}:
                payload[column] = order.get("id")
            elif column in {"order_run_id", "source_order_run_id"}:
                payload[column] = order_run_id
            elif column == security_key:
                payload[column] = order.get(security_key)
            elif column in {"target_position_id"}:
                payload[column] = order.get("target_position_id")
            elif column in {"fill_date", "trade_date", "effective_date"}:
                payload[column] = effective_date
            elif column == "as_of_date":
                payload[column] = order.get("as_of_date") or effective_date
            elif column in {"order_side", "side", "direction", "fill_side"}:
                payload[column] = side
            elif column in {"fill_quantity", "quantity", "filled_quantity"}:
                payload[column] = quantity
            elif column in {"fill_price", "price"}:
                payload[column] = fill_price
            elif column in {"gross_amount", "fill_gross_amount"}:
                payload[column] = gross_amount
            elif column in {"commission", "commission_amount", "fee", "fee_amount"}:
                payload[column] = commission
            elif column in {"stamp_duty", "stamp_duty_amount"}:
                payload[column] = stamp_duty
            elif column in {"slippage_amount"}:
                payload[column] = slippage_amount
            elif column in {"net_amount", "net_cash_amount", "net_fill_amount"}:
                payload[column] = net_amount
            elif column in {"cash_delta", "cash_change"}:
                payload[column] = cash_delta
            elif column in {"fill_status", "status"}:
                payload[column] = "FILLED"
            elif column in {"price_fill_rule"}:
                payload[column] = "NEXT_OPEN"
            elif column in {"created_at", "updated_at", "created_time", "updated_time"}:
                payload[column] = now
            else:
                payload[column] = order.get(column)

        self._fill_required_defaults(
            payload=payload,
            column_meta=fill_column_meta,
            effective_date=effective_date,
            now=now,
        )

        return payload

    def _fill_required_defaults(
        self,
        *,
        payload: dict[str, Any],
        column_meta: dict[str, dict[str, Any]],
        effective_date: date,
        now: datetime,
    ) -> None:
        for column, meta in column_meta.items():
            if column not in payload:
                continue

            if payload[column] is not None:
                continue

            if meta.get("is_nullable") == "YES":
                continue

            data_type = str(meta.get("data_type") or "").lower()

            if "numeric" in data_type or "double" in data_type or "integer" in data_type:
                payload[column] = Decimal("0")
            elif data_type == "date":
                payload[column] = effective_date
            elif "timestamp" in data_type:
                payload[column] = now
            elif "bool" in data_type:
                payload[column] = False
            elif "json" in data_type:
                payload[column] = {}
            else:
                payload[column] = "UNKNOWN"

    def _insert_fill(self, payload: dict[str, Any]) -> None:
        columns = list(payload.keys())
        column_sql = ", ".join([f'"{col}"' for col in columns])
        value_sql = ", ".join([f":{col}" for col in columns])

        self.session.execute(
            text(
                f"""
                insert into {FILL_TABLE} ({column_sql})
                values ({value_sql})
                """
            ),
            payload,
        )

    def _mark_order_filled(
        self,
        *,
        order_id: Any,
        order_columns: list[str],
        order_quantity_col: str,
        quantity: Decimal,
    ) -> None:
        if order_id is None:
            return

        updates: list[str] = []
        params: dict[str, Any] = {
            "order_id": order_id,
            "quantity": quantity,
            "now": datetime.utcnow(),
        }

        if "filled_quantity" in order_columns:
            updates.append("filled_quantity = :quantity")
        if "fill_quantity" in order_columns:
            updates.append("fill_quantity = :quantity")
        if "remaining_quantity" in order_columns:
            updates.append("remaining_quantity = 0")
        if "unfilled_quantity" in order_columns:
            updates.append("unfilled_quantity = 0")
        if "status" in order_columns:
            updates.append("status = 'FILLED'")
        if "order_status" in order_columns:
            updates.append("order_status = 'FILLED'")
        if "updated_at" in order_columns:
            updates.append("updated_at = :now")
        if "updated_time" in order_columns:
            updates.append("updated_time = :now")

        if not updates:
            return

        self.session.execute(
            text(
                f"""
                update {ORDER_TABLE}
                set {", ".join(updates)}
                where id = :order_id
                """
            ),
            params,
        )

    def _mark_order_rejected(
        self,
        *,
        order_id: Any,
        order_columns: list[str],
        reject_reason: str,
    ) -> None:
        if order_id is None:
            return

        updates: list[str] = []
        params: dict[str, Any] = {
            "order_id": order_id,
            "reject_reason": reject_reason,
            "now": datetime.utcnow(),
        }

        if "status" in order_columns:
            updates.append("status = 'REJECTED'")
        if "order_status" in order_columns:
            updates.append("order_status = 'REJECTED'")
        if "reject_reason" in order_columns:
            updates.append("reject_reason = :reject_reason")
        if "error_reason" in order_columns:
            updates.append("error_reason = :reject_reason")
        if "updated_at" in order_columns:
            updates.append("updated_at = :now")
        if "updated_time" in order_columns:
            updates.append("updated_time = :now")

        if not updates:
            return

        self.session.execute(
            text(
                f"""
                update {ORDER_TABLE}
                set {", ".join(updates)}
                where id = :order_id
                """
            ),
            params,
        )

    @staticmethod
    def _calc_commission(
        *,
        gross_amount: Decimal,
        commission_rate: Decimal,
        min_commission: Decimal,
    ) -> Decimal:
        commission = gross_amount * commission_rate
        if commission < min_commission:
            commission = min_commission
        return PaperRebalanceFillService._money(commission)

    @staticmethod
    def _money(value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _to_decimal(value: Any) -> Decimal:
        if value is None:
            return Decimal("0")
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))


def result_to_dict(result: RebalanceFillResult) -> dict[str, Any]:
    return asdict(result)