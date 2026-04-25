from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


POSITION_TABLE = "trading_paper_position"
FILL_TABLE = "trading_paper_fill"
ORDER_TABLE = "trading_paper_order"


@dataclass(frozen=True)
class ApplyFillPositionResult:
    new_position_run_id: int
    current_position_run_id: int
    fill_run_id: int
    portfolio_id: int
    effective_date: str
    current_position_count: int
    fill_count: int
    buy_fill_count: int
    sell_fill_count: int
    inserted_position_count: int
    open_position_count: int
    closed_position_count: int
    current_quantity_total: str
    new_quantity_total: str
    new_available_quantity_total: str
    realized_pnl_delta: str
    cash_delta: str
    status: str


class PaperPositionApplyFillService:
    """
    M7.3-B: 将 fill 应用到 position，生成新的 position run。

    兼容点：
    1. trading_paper_fill 可以没有买卖方向字段。
    2. 如果 fill 没有 side/order_side，则通过 fill.order_id -> trading_paper_order.order_side 解析。
    3. A股 T+1：BUY 当日不增加 available_quantity。
    """

    def __init__(self, session: Session):
        self.session = session

    def apply_fills_to_positions(
        self,
        *,
        new_position_run_id: int,
        current_position_run_id: int,
        fill_run_id: int,
        portfolio_id: int,
        effective_date: date,
        replace_existing: bool = False,
        keep_closed_positions: bool = True,
    ) -> ApplyFillPositionResult:
        position_columns = self._get_columns(POSITION_TABLE)
        fill_columns = self._get_columns(FILL_TABLE)
        order_columns = self._get_columns(ORDER_TABLE)
        position_meta = self._get_column_meta(POSITION_TABLE)

        self._validate_columns(
            position_columns=position_columns,
            fill_columns=fill_columns,
            order_columns=order_columns,
        )

        security_key = self._resolve_security_key(
            position_columns=position_columns,
            fill_columns=fill_columns,
            order_columns=order_columns,
        )
        fill_quantity_col = self._resolve_quantity_col(fill_columns)
        fill_price_col = self._resolve_price_col(fill_columns)
        order_side_col = self._resolve_order_side_col(order_columns)

        existing_count = self._count_positions(
            run_id=new_position_run_id,
            portfolio_id=portfolio_id,
        )
        if existing_count > 0:
            if not replace_existing:
                raise RuntimeError(
                    f"目标 position run 已存在持仓: new_position_run_id={new_position_run_id}, "
                    f"portfolio_id={portfolio_id}, count={existing_count}. "
                    f"如确认重跑，请设置 M7_REPLACE_EXISTING=true。"
                )
            self._delete_positions(
                run_id=new_position_run_id,
                portfolio_id=portfolio_id,
            )

        current_positions = self._load_current_positions(
            current_position_run_id=current_position_run_id,
            portfolio_id=portfolio_id,
            security_key=security_key,
        )
        fills = self._load_fills_with_order_side(
            fill_run_id=fill_run_id,
            portfolio_id=portfolio_id,
            security_key=security_key,
            fill_columns=fill_columns,
            order_columns=order_columns,
            fill_quantity_col=fill_quantity_col,
            fill_price_col=fill_price_col,
            order_side_col=order_side_col,
        )

        working_positions = {
            key: dict(row)
            for key, row in current_positions.items()
        }

        current_quantity_total = sum(
            self._to_decimal(row.get("quantity"))
            for row in current_positions.values()
        )

        buy_fill_count = 0
        sell_fill_count = 0
        realized_pnl_delta = Decimal("0")
        cash_delta_total = Decimal("0")

        # SELL 先于 BUY。
        fills_sorted = sorted(
            fills,
            key=lambda row: 0 if str(row.get("_resolved_side")).upper() == "SELL" else 1,
        )

        for fill in fills_sorted:
            side = str(fill.get("_resolved_side")).upper()
            quantity = self._to_decimal(fill.get("_resolved_fill_quantity"))
            fill_price = self._to_decimal(fill.get("_resolved_fill_price"))

            if quantity <= 0:
                continue

            if side not in {"BUY", "SELL"}:
                continue

            security_value = fill.get("_resolved_security_key")
            if security_value is None:
                raise RuntimeError(f"fill 无法解析证券键 {security_key}: {fill}")

            gross_amount = self._resolve_amount(
                row=fill,
                candidate_keys=["gross_amount", "fill_gross_amount"],
                default=quantity * fill_price,
            )
            net_amount = self._resolve_amount(
                row=fill,
                candidate_keys=["net_amount", "net_cash_amount", "net_fill_amount"],
                default=gross_amount,
            )
            cash_delta = self._resolve_cash_delta(
                fill=fill,
                side=side,
                gross_amount=gross_amount,
                net_amount=net_amount,
            )
            cash_delta_total += cash_delta

            if side == "SELL":
                sell_fill_count += 1
                pnl = self._apply_sell(
                    position=working_positions.get(security_value),
                    security_key=security_key,
                    security_value=security_value,
                    quantity=quantity,
                    net_amount=net_amount,
                    effective_date=effective_date,
                )
                realized_pnl_delta += pnl

            else:
                buy_fill_count += 1
                self._apply_buy(
                    working_positions=working_positions,
                    position=working_positions.get(security_value),
                    fill=fill,
                    security_key=security_key,
                    security_value=security_value,
                    quantity=quantity,
                    fill_price=fill_price,
                    net_amount=net_amount,
                    effective_date=effective_date,
                )

        inserted_position_count = 0
        open_position_count = 0
        closed_position_count = 0
        new_quantity_total = Decimal("0")
        new_available_quantity_total = Decimal("0")

        for security_value, row in sorted(working_positions.items(), key=lambda item: str(item[0])):
            quantity = self._to_decimal(row.get("quantity"))
            available_quantity = self._to_decimal(row.get("available_quantity"))

            if quantity <= 0:
                closed_position_count += 1
                if not keep_closed_positions:
                    continue
            else:
                open_position_count += 1

            payload = self._build_position_payload(
                position_columns=position_columns,
                position_meta=position_meta,
                source_row=row,
                new_position_run_id=new_position_run_id,
                current_position_run_id=current_position_run_id,
                fill_run_id=fill_run_id,
                portfolio_id=portfolio_id,
                effective_date=effective_date,
                security_key=security_key,
                security_value=security_value,
            )

            self._insert_position(payload)
            inserted_position_count += 1

            new_quantity_total += max(quantity, Decimal("0"))
            new_available_quantity_total += max(available_quantity, Decimal("0"))

        return ApplyFillPositionResult(
            new_position_run_id=new_position_run_id,
            current_position_run_id=current_position_run_id,
            fill_run_id=fill_run_id,
            portfolio_id=portfolio_id,
            effective_date=effective_date.isoformat(),
            current_position_count=len(current_positions),
            fill_count=len(fills),
            buy_fill_count=buy_fill_count,
            sell_fill_count=sell_fill_count,
            inserted_position_count=inserted_position_count,
            open_position_count=open_position_count,
            closed_position_count=closed_position_count,
            current_quantity_total=str(current_quantity_total),
            new_quantity_total=str(new_quantity_total),
            new_available_quantity_total=str(new_available_quantity_total),
            realized_pnl_delta=str(realized_pnl_delta),
            cash_delta=str(cash_delta_total),
            status="SUCCESS",
        )

    def _validate_columns(
        self,
        *,
        position_columns: list[str],
        fill_columns: list[str],
        order_columns: list[str],
    ) -> None:
        for col in ["run_id", "portfolio_id", "quantity", "available_quantity"]:
            if col not in position_columns:
                raise RuntimeError(f"{POSITION_TABLE} 缺少 {col}")

        for col in ["run_id", "portfolio_id"]:
            if col not in fill_columns:
                raise RuntimeError(f"{FILL_TABLE} 缺少 {col}")

        for col in ["id", "run_id", "portfolio_id"]:
            if col not in order_columns:
                raise RuntimeError(f"{ORDER_TABLE} 缺少 {col}")

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

    def _resolve_security_key(
        self,
        *,
        position_columns: list[str],
        fill_columns: list[str],
        order_columns: list[str],
    ) -> str:
        for col in [
            "instrument_id",
            "security_id",
            "ticker",
            "symbol",
            "instrument_code",
            "vendor_symbol",
        ]:
            if col in position_columns and (col in fill_columns or col in order_columns):
                return col
        raise RuntimeError("无法识别 position / fill / order 证券键")

    def _resolve_order_side_col(self, order_columns: list[str]) -> str:
        for col in ["order_side", "side", "direction", "order_direction"]:
            if col in order_columns:
                return col
        raise RuntimeError(f"{ORDER_TABLE} 无法识别买卖方向字段")

    def _resolve_quantity_col(self, fill_columns: list[str]) -> str:
        for col in ["fill_quantity", "quantity", "filled_quantity"]:
            if col in fill_columns:
                return col
        raise RuntimeError(f"{FILL_TABLE} 无法识别成交数量字段")

    def _resolve_price_col(self, fill_columns: list[str]) -> str:
        for col in ["fill_price", "price"]:
            if col in fill_columns:
                return col
        raise RuntimeError(f"{FILL_TABLE} 无法识别成交价格字段")

    def _count_positions(self, *, run_id: int, portfolio_id: int) -> int:
        row = self.session.execute(
            text(
                f"""
                select count(*) as cnt
                from {POSITION_TABLE}
                where run_id = :run_id
                  and portfolio_id = :portfolio_id
                """
            ),
            {"run_id": run_id, "portfolio_id": portfolio_id},
        ).mappings().one()
        return int(row["cnt"] or 0)

    def _delete_positions(self, *, run_id: int, portfolio_id: int) -> int:
        result = self.session.execute(
            text(
                f"""
                delete from {POSITION_TABLE}
                where run_id = :run_id
                  and portfolio_id = :portfolio_id
                """
            ),
            {"run_id": run_id, "portfolio_id": portfolio_id},
        )
        return int(result.rowcount or 0)

    def _load_current_positions(
        self,
        *,
        current_position_run_id: int,
        portfolio_id: int,
        security_key: str,
    ) -> dict[Any, dict[str, Any]]:
        rows = self.session.execute(
            text(
                f"""
                select *
                from {POSITION_TABLE}
                where run_id = :current_position_run_id
                  and portfolio_id = :portfolio_id
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

    def _load_fills_with_order_side(
        self,
        *,
        fill_run_id: int,
        portfolio_id: int,
        security_key: str,
        fill_columns: list[str],
        order_columns: list[str],
        fill_quantity_col: str,
        fill_price_col: str,
        order_side_col: str,
    ) -> list[dict[str, Any]]:
        order_id_col = None
        if "order_id" in fill_columns:
            order_id_col = "order_id"
        elif "paper_order_id" in fill_columns:
            order_id_col = "paper_order_id"

        if order_id_col is None:
            raise RuntimeError(
                f"{FILL_TABLE} 缺少 order_id / paper_order_id，无法从 {ORDER_TABLE} 解析买卖方向"
            )

        if security_key in fill_columns:
            resolved_security_sql = f"f.{security_key}"
        elif security_key in order_columns:
            resolved_security_sql = f"o.{security_key}"
        else:
            raise RuntimeError(f"fill/order 均缺少证券键 {security_key}")

        rows = self.session.execute(
            text(
                f"""
                select
                    f.*,
                    o.{order_side_col} as _resolved_side,
                    {resolved_security_sql} as _resolved_security_key,
                    f.{fill_quantity_col} as _resolved_fill_quantity,
                    f.{fill_price_col} as _resolved_fill_price
                from {FILL_TABLE} f
                left join {ORDER_TABLE} o
                  on f.{order_id_col} = o.id
                where f.run_id = :fill_run_id
                  and f.portfolio_id = :portfolio_id
                  and coalesce(f.{fill_quantity_col}, 0) > 0
                order by f.id
                """
            ),
            {
                "fill_run_id": fill_run_id,
                "portfolio_id": portfolio_id,
            },
        ).mappings().all()

        result = [dict(row) for row in rows]

        missing_side = [
            row for row in result
            if not row.get("_resolved_side")
        ]
        if missing_side:
            raise RuntimeError(
                f"存在 fill 无法从 order 解析买卖方向，数量={len(missing_side)}。"
                f"请检查 fill_run_id={fill_run_id} 是否由 M7.3-A 生成，且 fill.order_id 是否正确。"
            )

        return result

    def _apply_sell(
        self,
        *,
        position: dict[str, Any] | None,
        security_key: str,
        security_value: Any,
        quantity: Decimal,
        net_amount: Decimal,
        effective_date: date,
    ) -> Decimal:
        if position is None:
            raise RuntimeError(f"SELL 找不到当前持仓: {security_key}={security_value}")

        current_quantity = self._to_decimal(position.get("quantity"))
        available_quantity = self._to_decimal(position.get("available_quantity"))

        if quantity > current_quantity:
            raise RuntimeError(
                f"SELL 数量超过持仓: {security_key}={security_value}, "
                f"sell={quantity}, current={current_quantity}"
            )

        if quantity > available_quantity:
            raise RuntimeError(
                f"SELL 数量超过可卖数量: {security_key}={security_value}, "
                f"sell={quantity}, available={available_quantity}"
            )

        avg_cost = self._resolve_avg_cost(position)
        sold_cost_amount = avg_cost * quantity
        realized_pnl = net_amount - sold_cost_amount

        new_quantity = current_quantity - quantity
        new_available_quantity = available_quantity - quantity
        new_cost_amount = avg_cost * new_quantity

        position["quantity"] = new_quantity
        position["available_quantity"] = new_available_quantity

        self._set_if_exists(position, "cost_amount", new_cost_amount)
        self._set_if_exists(
            position,
            "realized_pnl",
            self._to_decimal(position.get("realized_pnl")) + realized_pnl,
        )
        self._set_if_exists(position, "realized_pnl_delta", realized_pnl)
        self._set_if_exists(position, "last_sell_date", effective_date)
        self._set_if_exists(position, "position_status", "OPEN" if new_quantity > 0 else "CLOSED")
        self._set_if_exists(position, "status", "OPEN" if new_quantity > 0 else "CLOSED")

        return realized_pnl

    def _apply_buy(
        self,
        *,
        working_positions: dict[Any, dict[str, Any]],
        position: dict[str, Any] | None,
        fill: dict[str, Any],
        security_key: str,
        security_value: Any,
        quantity: Decimal,
        fill_price: Decimal,
        net_amount: Decimal,
        effective_date: date,
    ) -> None:
        if position is None:
            position = self._new_position_from_fill(
                fill=fill,
                security_key=security_key,
                security_value=security_value,
                effective_date=effective_date,
            )
            working_positions[security_value] = position

        current_quantity = self._to_decimal(position.get("quantity"))
        avg_cost = self._resolve_avg_cost(position)
        current_cost_amount = avg_cost * current_quantity

        new_quantity = current_quantity + quantity
        new_cost_amount = current_cost_amount + net_amount
        new_avg_cost = new_cost_amount / new_quantity if new_quantity > 0 else Decimal("0")

        position["quantity"] = new_quantity

        # T+1：当日买入不增加 available_quantity。
        if "available_quantity" not in position or position.get("available_quantity") is None:
            position["available_quantity"] = Decimal("0")

        # M7.7-Fix-2:
        # New BUY positions are created from fill rows, so the working row may not
        # contain position-table cost / valuation keys yet.  The final insert payload
        # is built from this working row, therefore these values must be materialized
        # here instead of using _set_if_exists only.
        position["avg_cost"] = new_avg_cost
        position["cost_price"] = new_avg_cost
        position["average_cost"] = new_avg_cost
        position["cost_amount"] = new_cost_amount
        position["total_cost"] = new_cost_amount

        position["market_price"] = fill_price
        position["last_price"] = fill_price
        position["close_price"] = fill_price
        position["price"] = fill_price

        market_value = self._money(new_quantity * fill_price)
        unrealized_pnl = self._money(market_value - new_cost_amount)
        realized_pnl = self._to_decimal(position.get("realized_pnl"))

        position["market_value"] = market_value
        position["unrealized_pnl"] = unrealized_pnl
        position["total_pnl"] = self._money(realized_pnl + unrealized_pnl)

        self._set_if_exists(position, "last_buy_date", effective_date)
        self._set_if_exists(position, "position_status", "OPEN")
        self._set_if_exists(position, "status", "OPEN")

    def _new_position_from_fill(
        self,
        *,
        fill: dict[str, Any],
        security_key: str,
        security_value: Any,
        effective_date: date,
    ) -> dict[str, Any]:
        row = dict(fill)
        row[security_key] = security_value
        row["quantity"] = Decimal("0")
        row["available_quantity"] = Decimal("0")
        row["effective_date"] = effective_date
        row["as_of_date"] = effective_date
        row["position_date"] = effective_date
        row["trade_date"] = effective_date
        row["position_status"] = "OPEN"
        row["status"] = "OPEN"
        return row

    def _build_position_payload(
        self,
        *,
        position_columns: list[str],
        position_meta: dict[str, dict[str, Any]],
        source_row: dict[str, Any],
        new_position_run_id: int,
        current_position_run_id: int,
        fill_run_id: int,
        portfolio_id: int,
        effective_date: date,
        security_key: str,
        security_value: Any,
    ) -> dict[str, Any]:
        now = datetime.utcnow()
        payload: dict[str, Any] = {}

        skip_columns = {"id", "created_id", "updated_id"}

        quantity = self._to_decimal(source_row.get("quantity"))
        available_quantity = self._to_decimal(source_row.get("available_quantity"))

        if available_quantity > quantity:
            available_quantity = quantity

        if available_quantity < 0:
            available_quantity = Decimal("0")

        for column in position_columns:
            if column in skip_columns:
                continue

            if column == "run_id":
                payload[column] = new_position_run_id
            elif column == "portfolio_id":
                payload[column] = portfolio_id
            elif column == security_key:
                payload[column] = security_value
            elif column == "quantity":
                payload[column] = quantity
            elif column == "available_quantity":
                payload[column] = available_quantity
            elif column == "frozen_quantity":
                payload[column] = Decimal("0")
            elif column in {"effective_date", "position_date", "trade_date", "snapshot_date"}:
                payload[column] = effective_date
            elif column == "as_of_date":
                payload[column] = effective_date
            elif column in {"source_position_run_id", "carry_source_run_id"}:
                payload[column] = current_position_run_id
            elif column in {"source_fill_run_id", "fill_run_id"}:
                payload[column] = fill_run_id
            elif column in {"position_status", "status"}:
                payload[column] = "OPEN" if quantity > 0 else "CLOSED"
            elif column in {"created_at", "updated_at", "created_time", "updated_time"}:
                payload[column] = now
            else:
                payload[column] = source_row.get(column)

        self._fill_required_defaults(
            payload=payload,
            column_meta=position_meta,
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

    def _insert_position(self, payload: dict[str, Any]) -> None:
        columns = list(payload.keys())
        column_sql = ", ".join([f'"{col}"' for col in columns])
        value_sql = ", ".join([f":{col}" for col in columns])

        self.session.execute(
            text(
                f"""
                insert into {POSITION_TABLE} ({column_sql})
                values ({value_sql})
                """
            ),
            payload,
        )

    def _resolve_avg_cost(self, position: dict[str, Any]) -> Decimal:
        for key in ["avg_cost", "cost_price", "average_cost"]:
            if key in position:
                value = self._to_decimal(position.get(key))
                if value > 0:
                    return value

        quantity = self._to_decimal(position.get("quantity"))
        for key in ["cost_amount", "total_cost"]:
            if key in position:
                cost_amount = self._to_decimal(position.get(key))
                if quantity > 0 and cost_amount > 0:
                    return cost_amount / quantity

        for key in ["market_price", "last_price", "close_price", "price"]:
            if key in position:
                value = self._to_decimal(position.get(key))
                if value > 0:
                    return value

        return Decimal("0")

    def _resolve_amount(
        self,
        *,
        row: dict[str, Any],
        candidate_keys: list[str],
        default: Decimal,
    ) -> Decimal:
        for key in candidate_keys:
            if key in row:
                value = self._to_decimal(row.get(key))
                if value != 0:
                    return value
        return default

    def _resolve_cash_delta(
        self,
        *,
        fill: dict[str, Any],
        side: str,
        gross_amount: Decimal,
        net_amount: Decimal,
    ) -> Decimal:
        for key in ["cash_delta", "cash_change"]:
            if key in fill:
                value = self._to_decimal(fill.get(key))
                if value != 0:
                    return value

        if side == "BUY":
            return -abs(net_amount if net_amount != 0 else gross_amount)

        return abs(net_amount if net_amount != 0 else gross_amount)

    @staticmethod
    def _set_if_exists(row: dict[str, Any], key: str, value: Any) -> None:
        if key in row:
            row[key] = value

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


def result_to_dict(result: ApplyFillPositionResult) -> dict[str, Any]:
    return asdict(result)