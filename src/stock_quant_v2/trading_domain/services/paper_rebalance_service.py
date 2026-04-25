from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


POSITION_TABLE = "trading_paper_position"
TARGET_TABLE = "trading_paper_target_position"
ORDER_TABLE = "trading_paper_order"


@dataclass(frozen=True)
class RebalanceOrderResult:
    order_run_id: int
    portfolio_id: int
    current_position_run_id: int
    target_position_run_id: int
    effective_date: str
    target_quantity_source: str
    deleted_existing_count: int
    current_position_count: int
    target_position_count: int
    buy_order_count: int
    sell_order_count: int
    hold_count: int
    blocked_sell_count: int
    inserted_order_count: int
    current_quantity_total: str
    target_quantity_total: str
    status: str


class PaperRebalanceService:
    """
    M7.2: current position 与 target position 做差，生成 BUY / SELL 调仓订单。

    target_quantity_source:
    - TARGET_POSITION: 使用 trading_paper_target_position.target_quantity
    - TEMPLATE_ORDER: 使用 template_order_run_id 对应的 order_quantity 作为目标股数
    - AUTO: 有 template_order_run_id 时优先 TEMPLATE_ORDER，否则 TARGET_POSITION
    """

    def __init__(self, session: Session):
        self.session = session

    def generate_rebalance_orders(
        self,
        *,
        order_run_id: int,
        portfolio_id: int,
        current_position_run_id: int,
        target_position_run_id: int,
        effective_date: date,
        as_of_date: date | None = None,
        template_order_run_id: int | None = None,
        target_quantity_source: str = "AUTO",
        replace_existing: bool = False,
        write_hold_orders: bool = False,
    ) -> RebalanceOrderResult:
        target_quantity_source = target_quantity_source.strip().upper()

        position_columns = self._get_table_columns(POSITION_TABLE)
        target_columns = self._get_table_columns(TARGET_TABLE)
        order_columns = self._get_table_columns(ORDER_TABLE)

        self._validate_base_columns(
            position_columns=position_columns,
            target_columns=target_columns,
            order_columns=order_columns,
        )

        security_key = self._resolve_security_key(
            position_columns=position_columns,
            target_columns=target_columns,
            order_columns=order_columns,
        )
        target_quantity_col = self._resolve_target_quantity_column(target_columns)
        order_quantity_col = self._resolve_order_quantity_column(order_columns)

        if target_quantity_source == "AUTO":
            target_quantity_source = "TEMPLATE_ORDER" if template_order_run_id else "TARGET_POSITION"

        if target_quantity_source not in {"TARGET_POSITION", "TEMPLATE_ORDER"}:
            raise RuntimeError(
                "M7_TARGET_QUANTITY_SOURCE 只支持 AUTO / TARGET_POSITION / TEMPLATE_ORDER"
            )

        if target_quantity_source == "TEMPLATE_ORDER" and not template_order_run_id:
            raise RuntimeError(
                "target_quantity_source=TEMPLATE_ORDER 时必须提供 template_order_run_id"
            )

        existing_count = self._count_orders(
            order_run_id=order_run_id,
            portfolio_id=portfolio_id,
        )

        deleted_existing_count = 0
        if existing_count > 0:
            if not replace_existing:
                raise RuntimeError(
                    f"目标 order_run 已存在订单: order_run_id={order_run_id}, "
                    f"portfolio_id={portfolio_id}, count={existing_count}. "
                    f"如确认重跑，请设置 M7_REPLACE_EXISTING=true。"
                )

            deleted_existing_count = self._delete_orders(
                order_run_id=order_run_id,
                portfolio_id=portfolio_id,
            )

        current_positions = self._load_current_positions(
            security_key=security_key,
            current_position_run_id=current_position_run_id,
            portfolio_id=portfolio_id,
        )

        template_rows = self._load_template_orders(
            template_order_run_id=template_order_run_id,
            portfolio_id=portfolio_id,
            security_key=security_key,
        )

        target_positions = self._load_target_positions(
            security_key=security_key,
            target_quantity_col=target_quantity_col,
            order_quantity_col=order_quantity_col,
            target_position_run_id=target_position_run_id,
            portfolio_id=portfolio_id,
            target_quantity_source=target_quantity_source,
            template_rows=template_rows,
        )

        all_keys = sorted(set(current_positions.keys()) | set(target_positions.keys()))

        buy_order_count = 0
        sell_order_count = 0
        hold_count = 0
        blocked_sell_count = 0
        inserted_order_count = 0
        current_quantity_total = Decimal("0")
        target_quantity_total = Decimal("0")

        for key in all_keys:
            current_row = current_positions.get(key)
            target_row = target_positions.get(key)

            current_quantity = self._to_decimal(
                current_row.get("quantity") if current_row else 0
            )
            available_quantity = self._to_decimal(
                current_row.get("available_quantity") if current_row else 0
            )
            target_quantity = self._to_decimal(
                target_row.get("_target_quantity") if target_row else 0
            )

            current_quantity_total += current_quantity
            target_quantity_total += target_quantity

            delta_quantity = target_quantity - current_quantity

            if delta_quantity > 0:
                order_side = "BUY"
                order_quantity = delta_quantity
                reason = "TARGET_INCREASE" if current_quantity > 0 else "TARGET_NEW"
                buy_order_count += 1

            elif delta_quantity < 0:
                desired_sell_quantity = abs(delta_quantity)
                order_quantity = min(desired_sell_quantity, available_quantity)

                if order_quantity <= 0:
                    blocked_sell_count += 1
                    continue

                order_side = "SELL"
                reason = "TARGET_DECREASE" if target_quantity > 0 else "TARGET_REMOVED"
                sell_order_count += 1

            else:
                hold_count += 1
                if not write_hold_orders:
                    continue

                order_side = "HOLD"
                order_quantity = Decimal("0")
                reason = "TARGET_UNCHANGED"

            payload = self._build_order_payload(
                order_columns=order_columns,
                order_run_id=order_run_id,
                portfolio_id=portfolio_id,
                current_position_run_id=current_position_run_id,
                target_position_run_id=target_position_run_id,
                effective_date=effective_date,
                as_of_date=as_of_date or effective_date,
                security_key=security_key,
                security_value=key,
                order_side=order_side,
                order_quantity=order_quantity,
                target_quantity=target_quantity,
                reason=reason,
                current_row=current_row,
                target_row=target_row,
                template_row=template_rows.get(key),
                fallback_template_row=template_rows.get("__first__"),
            )

            self._insert_order(payload)
            inserted_order_count += 1

        return RebalanceOrderResult(
            order_run_id=order_run_id,
            portfolio_id=portfolio_id,
            current_position_run_id=current_position_run_id,
            target_position_run_id=target_position_run_id,
            effective_date=effective_date.isoformat(),
            target_quantity_source=target_quantity_source,
            deleted_existing_count=deleted_existing_count,
            current_position_count=len(current_positions),
            target_position_count=len(target_positions),
            buy_order_count=buy_order_count,
            sell_order_count=sell_order_count,
            hold_count=hold_count,
            blocked_sell_count=blocked_sell_count,
            inserted_order_count=inserted_order_count,
            current_quantity_total=str(current_quantity_total),
            target_quantity_total=str(target_quantity_total),
            status="SUCCESS",
        )

    def _validate_base_columns(
        self,
        *,
        position_columns: list[str],
        target_columns: list[str],
        order_columns: list[str],
    ) -> None:
        for col in ["run_id", "portfolio_id", "quantity", "available_quantity"]:
            if col not in position_columns:
                raise RuntimeError(f"{POSITION_TABLE} 缺少 {col}")

        for col in ["run_id", "portfolio_id"]:
            if col not in target_columns:
                raise RuntimeError(f"{TARGET_TABLE} 缺少 {col}")

        for col in ["run_id", "portfolio_id"]:
            if col not in order_columns:
                raise RuntimeError(f"{ORDER_TABLE} 缺少 {col}")

    def _resolve_security_key(
        self,
        *,
        position_columns: list[str],
        target_columns: list[str],
        order_columns: list[str],
    ) -> str:
        candidates = [
            "instrument_id",
            "security_id",
            "ticker",
            "symbol",
            "instrument_code",
            "vendor_symbol",
        ]

        for col in candidates:
            if col in position_columns and col in target_columns and col in order_columns:
                return col

        raise RuntimeError(
            "无法识别 position / target / order 共同证券键。"
            "请检查是否存在 instrument_id / ticker / symbol 等字段。"
        )

    def _resolve_target_quantity_column(self, target_columns: list[str]) -> str:
        candidates = [
            "target_quantity",
            "quantity",
            "target_shares",
            "shares",
        ]

        for col in candidates:
            if col in target_columns:
                return col

        raise RuntimeError(
            f"{TARGET_TABLE} 未找到目标数量字段。"
            "M7.2 需要 target_quantity / quantity / target_shares / shares 之一。"
        )

    def _resolve_order_quantity_column(self, order_columns: list[str]) -> str:
        candidates = [
            "order_quantity",
            "quantity",
            "requested_quantity",
        ]

        for col in candidates:
            if col in order_columns:
                return col

        raise RuntimeError(
            f"{ORDER_TABLE} 未找到订单数量字段。"
            "M7.2 需要 order_quantity / quantity / requested_quantity 之一。"
        )

    def _get_table_columns(self, table_name: str) -> list[str]:
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

    def _count_orders(self, *, order_run_id: int, portfolio_id: int) -> int:
        row = self.session.execute(
            text(
                f"""
                select count(*) as cnt
                from {ORDER_TABLE}
                where run_id = :order_run_id
                  and portfolio_id = :portfolio_id
                """
            ),
            {
                "order_run_id": order_run_id,
                "portfolio_id": portfolio_id,
            },
        ).mappings().one()

        return int(row["cnt"] or 0)

    def _delete_orders(self, *, order_run_id: int, portfolio_id: int) -> int:
        result = self.session.execute(
            text(
                f"""
                delete from {ORDER_TABLE}
                where run_id = :order_run_id
                  and portfolio_id = :portfolio_id
                """
            ),
            {
                "order_run_id": order_run_id,
                "portfolio_id": portfolio_id,
            },
        )

        return int(result.rowcount or 0)

    def _load_current_positions(
        self,
        *,
        security_key: str,
        current_position_run_id: int,
        portfolio_id: int,
    ) -> dict[Any, dict[str, Any]]:
        rows = self.session.execute(
            text(
                f"""
                select *
                from {POSITION_TABLE}
                where run_id = :current_position_run_id
                  and portfolio_id = :portfolio_id
                  and coalesce(quantity, 0) > 0
                order by {security_key}
                """
            ),
            {
                "current_position_run_id": current_position_run_id,
                "portfolio_id": portfolio_id,
            },
        ).mappings().all()

        result: dict[Any, dict[str, Any]] = {}
        for row in rows:
            row_dict = dict(row)
            result[row_dict[security_key]] = row_dict

        return result

    def _load_target_positions(
        self,
        *,
        security_key: str,
        target_quantity_col: str,
        order_quantity_col: str,
        target_position_run_id: int,
        portfolio_id: int,
        target_quantity_source: str,
        template_rows: dict[Any, dict[str, Any]],
    ) -> dict[Any, dict[str, Any]]:
        rows = self.session.execute(
            text(
                f"""
                select *
                from {TARGET_TABLE}
                where run_id = :target_position_run_id
                  and portfolio_id = :portfolio_id
                order by {security_key}
                """
            ),
            {
                "target_position_run_id": target_position_run_id,
                "portfolio_id": portfolio_id,
            },
        ).mappings().all()

        result: dict[Any, dict[str, Any]] = {}

        for row in rows:
            row_dict = dict(row)
            security_value = row_dict[security_key]

            if target_quantity_source == "TEMPLATE_ORDER":
                template_row = template_rows.get(security_value)
                if template_row is None:
                    target_quantity = Decimal("0")
                else:
                    target_quantity = self._to_decimal(template_row.get(order_quantity_col))
            else:
                target_quantity = self._to_decimal(row_dict.get(target_quantity_col))

            row_dict["_target_quantity"] = target_quantity
            result[security_value] = row_dict

        return result

    def _load_template_orders(
        self,
        *,
        template_order_run_id: int | None,
        portfolio_id: int,
        security_key: str,
    ) -> dict[Any, dict[str, Any]]:
        if not template_order_run_id:
            return {}

        rows = self.session.execute(
            text(
                f"""
                select *
                from {ORDER_TABLE}
                where run_id = :template_order_run_id
                  and portfolio_id = :portfolio_id
                order by id
                """
            ),
            {
                "template_order_run_id": template_order_run_id,
                "portfolio_id": portfolio_id,
            },
        ).mappings().all()

        result: dict[Any, dict[str, Any]] = {}
        first_row: dict[str, Any] | None = None

        for row in rows:
            row_dict = dict(row)

            if first_row is None:
                first_row = row_dict

            result[row_dict.get(security_key)] = row_dict

        if first_row is not None:
            result["__first__"] = first_row

        return result

    def _build_order_payload(
        self,
        *,
        order_columns: list[str],
        order_run_id: int,
        portfolio_id: int,
        current_position_run_id: int,
        target_position_run_id: int,
        effective_date: date,
        as_of_date: date,
        security_key: str,
        security_value: Any,
        order_side: str,
        order_quantity: Decimal,
        target_quantity: Decimal,
        reason: str,
        current_row: dict[str, Any] | None,
        target_row: dict[str, Any] | None,
        template_row: dict[str, Any] | None,
        fallback_template_row: dict[str, Any] | None,
    ) -> dict[str, Any]:
        now = datetime.utcnow()
        payload: dict[str, Any] = {}

        estimated_price = self._resolve_estimated_price(
            current_row=current_row,
            target_row=target_row,
            template_row=template_row,
            fallback_template_row=fallback_template_row,
            security_key=security_key,
            security_value=security_value,
            as_of_date=as_of_date,
            effective_date=effective_date,
        )

        estimated_gross_amount = order_quantity * estimated_price
        estimated_fee = Decimal("0")
        estimated_net_amount = estimated_gross_amount

        if order_side == "BUY":
            estimated_net_amount = estimated_gross_amount + estimated_fee
        elif order_side == "SELL":
            estimated_net_amount = estimated_gross_amount - estimated_fee

        skip_columns = {
            "id",
            "created_id",
            "updated_id",
        }

        for column in order_columns:
            if column in skip_columns:
                continue

            direct_template_value = template_row.get(column) if template_row else None
            fallback_template_value = (
                fallback_template_row.get(column) if fallback_template_row else None
            )

            if column == "run_id":
                payload[column] = order_run_id

            elif column == "portfolio_id":
                payload[column] = portfolio_id

            elif column == security_key:
                payload[column] = security_value

            elif column in {"target_run_id", "target_position_run_id"}:
                payload[column] = target_position_run_id

            elif column in {"current_position_run_id", "source_position_run_id"}:
                payload[column] = current_position_run_id

            elif column == "target_position_id":
                payload[column] = target_row.get("id") if target_row else None

            elif column in {"effective_date", "trade_date", "order_date"}:
                payload[column] = effective_date

            elif column == "as_of_date":
                payload[column] = as_of_date

            elif column in {"side", "order_side", "direction", "order_direction"}:
                payload[column] = order_side

            elif column in {"order_quantity", "quantity", "requested_quantity"}:
                payload[column] = order_quantity

            elif column == "target_quantity":
                payload[column] = target_quantity

            elif column in {"filled_quantity", "fill_quantity"}:
                payload[column] = Decimal("0")

            elif column in {"remaining_quantity", "unfilled_quantity"}:
                payload[column] = order_quantity

            elif column in {"order_status", "status"}:
                payload[column] = "CREATED"

            elif column in {"order_type", "execution_type"}:
                payload[column] = "NEXT_OPEN"

            elif column == "price_fill_rule":
                payload[column] = direct_template_value or fallback_template_value or "NEXT_OPEN"

            elif column == "time_in_force":
                payload[column] = direct_template_value or fallback_template_value or "DAY"

            elif column in {"rebalance_reason", "reason", "reason_code"}:
                payload[column] = reason

            elif column in {"reject_reason", "error_reason"}:
                payload[column] = None


            elif column == "estimated_price":

                payload[column] = estimated_price


            elif column == "estimated_gross_amount":

                payload[column] = estimated_gross_amount


            elif column == "estimated_fee":

                payload[column] = estimated_fee


            elif column == "estimated_net_amount":

                payload[column] = estimated_net_amount

            elif column in {"created_at", "updated_at", "created_time", "updated_time"}:
                payload[column] = now

            elif column in {"source_signal_run_id", "signal_run_id"}:
                payload[column] = self._pick_value(
                    target_row,
                    current_row,
                    column,
                    default=direct_template_value,
                )

            elif column in {"strategy_version_id", "strategy_id"}:
                payload[column] = self._pick_value(
                    target_row,
                    current_row,
                    column,
                    default=direct_template_value,
                )

            elif column in {"target_weight", "target_value", "target_amount"}:
                payload[column] = self._pick_value(
                    target_row,
                    current_row,
                    column,
                    default=direct_template_value,
                )

            else:
                payload[column] = self._pick_value(
                    target_row,
                    current_row,
                    column,
                    default=direct_template_value,
                )

        return payload

    def _insert_order(self, payload: dict[str, Any]) -> None:
        columns = list(payload.keys())
        column_sql = ", ".join([f'"{col}"' for col in columns])
        value_sql = ", ".join([f":{col}" for col in columns])

        self.session.execute(
            text(
                f"""
                insert into {ORDER_TABLE} ({column_sql})
                values ({value_sql})
                """
            ),
            payload,
        )

    def _resolve_estimated_price(
        self,
        *,
        current_row: dict[str, Any] | None,
        target_row: dict[str, Any] | None,
        template_row: dict[str, Any] | None,
        fallback_template_row: dict[str, Any] | None,
        security_key: str | None = None,
        security_value: Any | None = None,
        as_of_date: date | None = None,
        effective_date: date | None = None,
    ) -> Decimal:
        """
        M7.7-Fix-1: order 阶段必须尽量给出 estimated_price。

        价格优先级：
        1. 订单/持仓/目标行中已有价格字段；
        2. core_daily_bar 在 as_of_date 或 effective_date 之前最近一个交易日的 close/open；
        3. 返回 0，让 fill 阶段在没有价格时继续显式报错。

        注意：真正成交仍优先使用 effective_date NEXT_OPEN；这里的 estimated_price
        只是给缺失 NEXT_OPEN 的 paper-trading 测试链路提供保守 fallback。
        """

        candidate_keys = [
            "estimated_price",
            "fill_price",
            "avg_fill_price",
            "open_price",
            "close_price",
            "last_price",
            "market_price",
            "price",
            "open",
            "close",
            "avg_cost",
            "cost_price",
        ]

        for row in (template_row, current_row, target_row, fallback_template_row):
            if row is None:
                continue

            for key in candidate_keys:
                if key not in row:
                    continue

                value = self._to_decimal(row.get(key))
                if value > 0:
                    return value

        db_price = self._resolve_estimated_price_from_daily_bar(
            security_key=security_key,
            security_value=security_value,
            as_of_date=as_of_date,
            effective_date=effective_date,
        )
        if db_price > 0:
            return db_price

        return Decimal("0")

    def _resolve_estimated_price_from_daily_bar(
        self,
        *,
        security_key: str | None,
        security_value: Any | None,
        as_of_date: date | None,
        effective_date: date | None,
    ) -> Decimal:
        if not security_key or security_value is None:
            return Decimal("0")

        daily_bar_table = "core_daily_bar"
        columns = self._get_table_columns(daily_bar_table)
        if not columns:
            return Decimal("0")

        if security_key in columns:
            id_col = security_key
        elif security_key == "instrument_id" and "instrument_id" in columns:
            id_col = "instrument_id"
        else:
            return Decimal("0")

        date_col = None
        for col in ["trade_date", "bar_date", "date"]:
            if col in columns:
                date_col = col
                break
        if date_col is None:
            return Decimal("0")

        close_col = None
        for col in ["close", "close_price", "adj_close", "close_adj"]:
            if col in columns:
                close_col = col
                break

        open_col = None
        for col in ["open", "open_price", "adj_open", "open_adj"]:
            if col in columns:
                open_col = col
                break

        if close_col is None and open_col is None:
            return Decimal("0")

        price_expr_parts = []
        if close_col:
            price_expr_parts.append(close_col)
        if open_col:
            price_expr_parts.append(open_col)
        price_expr = "coalesce(" + ", ".join(price_expr_parts) + ")"

        anchor_date = as_of_date or effective_date
        if anchor_date is None:
            return Decimal("0")

        extra_filter = ""
        if "price_adjust_type" in columns:
            extra_filter = " and coalesce(price_adjust_type, 'RAW') = 'RAW'"

        row = self.session.execute(
            text(
                f"""
                select {price_expr} as estimated_price
                from {daily_bar_table}
                where {id_col} = :security_value
                  and {date_col} <= :anchor_date
                  {extra_filter}
                order by {date_col} desc
                limit 1
                """
            ),
            {
                "security_value": security_value,
                "anchor_date": anchor_date,
            },
        ).mappings().first()

        if row is None:
            return Decimal("0")

        value = self._to_decimal(row.get("estimated_price"))
        return value if value > 0 else Decimal("0")

    @staticmethod
    def _pick_value(
        first: dict[str, Any] | None,
        second: dict[str, Any] | None,
        key: str,
        default: Any = None,
    ) -> Any:
        if first is not None and key in first:
            return first.get(key)
        if second is not None and key in second:
            return second.get(key)
        return default

    @staticmethod
    def _to_decimal(value: Any) -> Decimal:
        if value is None:
            return Decimal("0")
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))


def result_to_dict(result: RebalanceOrderResult) -> dict[str, Any]:
    return asdict(result)