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
SNAPSHOT_TABLE = "trading_paper_portfolio_snapshot"
DAILY_BAR_TABLE = "core_daily_bar"


@dataclass(frozen=True)
class PortfolioSnapshotM7Result:
    snapshot_run_id: int
    previous_snapshot_run_id: int
    position_run_id: int
    fill_run_id: int
    portfolio_id: int
    snapshot_date: str
    previous_cash_balance: str
    cash_delta: str
    cash_balance: str
    market_value: str
    total_equity: str
    total_cost: str
    unrealized_pnl: str
    realized_pnl: str
    open_position_count: int
    closed_position_count: int
    inserted_snapshot_count: int
    status: str


class PaperPortfolioSnapshotM7Service:
    """
    M7.3-C: 基于新 position run + fill cash_delta 生成连续 portfolio snapshot。

    逻辑：
    1. 从上一 snapshot 读取 cash_balance。
    2. 从 fill + order 计算 cash_delta。
    3. 用 position_run_id 的当前持仓按 effective_date close 估值。
    4. 写入 trading_paper_portfolio_snapshot。
    """

    def __init__(self, session: Session):
        self.session = session

    def build_snapshot(
        self,
        *,
        snapshot_run_id: int,
        previous_snapshot_run_id: int,
        position_run_id: int,
        fill_run_id: int,
        portfolio_id: int,
        snapshot_date: date,
        replace_existing: bool = False,
    ) -> PortfolioSnapshotM7Result:
        snapshot_columns = self._get_columns(SNAPSHOT_TABLE)
        snapshot_meta = self._get_column_meta(SNAPSHOT_TABLE)
        position_columns = self._get_columns(POSITION_TABLE)
        fill_columns = self._get_columns(FILL_TABLE)
        order_columns = self._get_columns(ORDER_TABLE)

        security_key = self._resolve_security_key(position_columns=position_columns)

        existing_count = self._count_snapshot(
            run_id=snapshot_run_id,
            portfolio_id=portfolio_id,
        )
        if existing_count > 0:
            if not replace_existing:
                raise RuntimeError(
                    f"目标 snapshot run 已存在快照: snapshot_run_id={snapshot_run_id}, "
                    f"portfolio_id={portfolio_id}, count={existing_count}. "
                    f"如确认重跑，请设置 M7_REPLACE_EXISTING=true。"
                )
            self._delete_snapshot(
                run_id=snapshot_run_id,
                portfolio_id=portfolio_id,
            )

        previous_snapshot = self._load_previous_snapshot(
            previous_snapshot_run_id=previous_snapshot_run_id,
            portfolio_id=portfolio_id,
        )
        previous_cash_balance = self._resolve_previous_cash(previous_snapshot)
        previous_realized_pnl = self._resolve_previous_realized_pnl(previous_snapshot)

        cash_delta = self._calculate_fill_cash_delta(
            fill_run_id=fill_run_id,
            portfolio_id=portfolio_id,
            fill_columns=fill_columns,
            order_columns=order_columns,
        )
        cash_balance = self._money(previous_cash_balance + cash_delta)

        valuation = self._calculate_position_valuation(
            position_run_id=position_run_id,
            portfolio_id=portfolio_id,
            snapshot_date=snapshot_date,
            security_key=security_key,
            position_columns=position_columns,
        )

        market_value = valuation["market_value"]
        total_cost = valuation["total_cost"]
        unrealized_pnl = valuation["unrealized_pnl"]
        current_position_realized_pnl = valuation["realized_pnl"]
        open_position_count = valuation["open_position_count"]
        closed_position_count = valuation["closed_position_count"]
        realized_pnl = self._resolve_snapshot_realized_pnl(
            previous_realized_pnl=previous_realized_pnl,
            current_position_realized_pnl=current_position_realized_pnl,
            open_position_count=open_position_count,
            closed_position_count=closed_position_count,
        )

        total_equity = self._money(cash_balance + market_value)

        payload = self._build_snapshot_payload(
            snapshot_columns=snapshot_columns,
            snapshot_meta=snapshot_meta,
            previous_snapshot=previous_snapshot,
            snapshot_run_id=snapshot_run_id,
            previous_snapshot_run_id=previous_snapshot_run_id,
            position_run_id=position_run_id,
            fill_run_id=fill_run_id,
            portfolio_id=portfolio_id,
            snapshot_date=snapshot_date,
            previous_cash_balance=previous_cash_balance,
            cash_delta=cash_delta,
            cash_balance=cash_balance,
            market_value=market_value,
            total_equity=total_equity,
            total_cost=total_cost,
            unrealized_pnl=unrealized_pnl,
            realized_pnl=realized_pnl,
            open_position_count=open_position_count,
            closed_position_count=closed_position_count,
        )

        self._insert_snapshot(payload)

        return PortfolioSnapshotM7Result(
            snapshot_run_id=snapshot_run_id,
            previous_snapshot_run_id=previous_snapshot_run_id,
            position_run_id=position_run_id,
            fill_run_id=fill_run_id,
            portfolio_id=portfolio_id,
            snapshot_date=snapshot_date.isoformat(),
            previous_cash_balance=str(previous_cash_balance),
            cash_delta=str(cash_delta),
            cash_balance=str(cash_balance),
            market_value=str(market_value),
            total_equity=str(total_equity),
            total_cost=str(total_cost),
            unrealized_pnl=str(unrealized_pnl),
            realized_pnl=str(realized_pnl),
            open_position_count=open_position_count,
            closed_position_count=closed_position_count,
            inserted_snapshot_count=1,
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

    def _resolve_security_key(self, *, position_columns: list[str]) -> str:
        for col in [
            "instrument_id",
            "security_id",
            "ticker",
            "symbol",
            "instrument_code",
            "vendor_symbol",
        ]:
            if col in position_columns:
                return col
        raise RuntimeError(f"{POSITION_TABLE} 无法识别证券键")

    def _count_snapshot(self, *, run_id: int, portfolio_id: int) -> int:
        row = self.session.execute(
            text(
                f"""
                select count(*) as cnt
                from {SNAPSHOT_TABLE}
                where run_id = :run_id
                  and portfolio_id = :portfolio_id
                """
            ),
            {"run_id": run_id, "portfolio_id": portfolio_id},
        ).mappings().one()
        return int(row["cnt"] or 0)

    def _delete_snapshot(self, *, run_id: int, portfolio_id: int) -> int:
        result = self.session.execute(
            text(
                f"""
                delete from {SNAPSHOT_TABLE}
                where run_id = :run_id
                  and portfolio_id = :portfolio_id
                """
            ),
            {"run_id": run_id, "portfolio_id": portfolio_id},
        )
        return int(result.rowcount or 0)

    def _load_previous_snapshot(
        self,
        *,
        previous_snapshot_run_id: int,
        portfolio_id: int,
    ) -> dict[str, Any]:
        row = self.session.execute(
            text(
                f"""
                select *
                from {SNAPSHOT_TABLE}
                where run_id = :previous_snapshot_run_id
                  and portfolio_id = :portfolio_id
                order by id desc
                limit 1
                """
            ),
            {
                "previous_snapshot_run_id": previous_snapshot_run_id,
                "portfolio_id": portfolio_id,
            },
        ).mappings().first()

        if row is None:
            raise RuntimeError(
                f"找不到 previous snapshot: run_id={previous_snapshot_run_id}, "
                f"portfolio_id={portfolio_id}"
            )

        return dict(row)

    def _resolve_previous_cash(self, previous_snapshot: dict[str, Any]) -> Decimal:
        for key in [
            "cash_balance",
            "cash",
            "available_cash",
            "cash_amount",
        ]:
            if key in previous_snapshot:
                value = self._to_decimal(previous_snapshot.get(key))
                return value

        raise RuntimeError(
            f"{SNAPSHOT_TABLE} 无法从上一 snapshot 解析现金字段，"
            "需要 cash_balance / cash / available_cash / cash_amount 之一"
        )

    def _resolve_previous_realized_pnl(self, previous_snapshot: dict[str, Any]) -> Decimal:
        if "realized_pnl" not in previous_snapshot:
            return Decimal("0")
        return self._money(self._to_decimal(previous_snapshot.get("realized_pnl")))

    def _resolve_snapshot_realized_pnl(
        self,
        *,
        previous_realized_pnl: Decimal,
        current_position_realized_pnl: Decimal,
        open_position_count: int,
        closed_position_count: int,
    ) -> Decimal:
        """
        M7.6 hotfix: keep portfolio_snapshot.realized_pnl continuous across days.

        Current M7 carry-forward only rolls open positions. After a full exit day, the
        next day may have an empty position run, so summing realized_pnl from current
        positions returns 0 and incorrectly resets the portfolio-level realized_pnl.

        Minimal accounting rule for M7.6:
        - If current position run has no open/closed positions and no position-level
          realized_pnl source, inherit previous snapshot realized_pnl.
        - Otherwise keep existing M7 behavior: use realized_pnl resolved from the
          current position run, including closed positions when present.

        A later M7.7/M8 accounting enhancement can introduce explicit
        realized_pnl_delta at snapshot level to avoid relying on position-row sums.
        """
        current_value = self._money(current_position_realized_pnl)
        if open_position_count == 0 and closed_position_count == 0 and current_value == 0:
            return self._money(previous_realized_pnl)
        return current_value

    def _calculate_fill_cash_delta(
        self,
        *,
        fill_run_id: int,
        portfolio_id: int,
        fill_columns: list[str],
        order_columns: list[str],
    ) -> Decimal:
        order_id_col = None
        for col in ["order_id", "paper_order_id"]:
            if col in fill_columns:
                order_id_col = col
                break

        if order_id_col is None:
            raise RuntimeError(f"{FILL_TABLE} 缺少 order_id / paper_order_id")

        side_col = None
        for col in ["order_side", "side", "direction", "order_direction"]:
            if col in order_columns:
                side_col = col
                break

        if side_col is None:
            raise RuntimeError(f"{ORDER_TABLE} 无法识别买卖方向字段")

        quantity_col = None
        for col in ["fill_quantity", "quantity", "filled_quantity"]:
            if col in fill_columns:
                quantity_col = col
                break

        if quantity_col is None:
            raise RuntimeError(f"{FILL_TABLE} 无法识别成交数量字段")

        price_col = None
        for col in ["fill_price", "price"]:
            if col in fill_columns:
                price_col = col
                break

        if price_col is None:
            raise RuntimeError(f"{FILL_TABLE} 无法识别成交价格字段")

        gross_expr = None
        for col in ["gross_amount", "fill_gross_amount"]:
            if col in fill_columns:
                gross_expr = f"coalesce(f.{col}, f.{quantity_col} * f.{price_col})"
                break
        if gross_expr is None:
            gross_expr = f"(f.{quantity_col} * f.{price_col})"

        net_expr = None
        for col in ["net_amount", "net_cash_amount", "net_fill_amount"]:
            if col in fill_columns:
                net_expr = f"coalesce(f.{col}, {gross_expr})"
                break
        if net_expr is None:
            net_expr = gross_expr

        cash_delta_expr = None
        for col in ["cash_delta", "cash_change"]:
            if col in fill_columns:
                cash_delta_expr = f"f.{col}"
                break

        if cash_delta_expr:
            amount_expr = f"""
                case
                    when coalesce({cash_delta_expr}, 0) <> 0 then {cash_delta_expr}
                    when o.{side_col} = 'BUY' then -abs({net_expr})
                    when o.{side_col} = 'SELL' then abs({net_expr})
                    else 0
                end
            """
        else:
            amount_expr = f"""
                case
                    when o.{side_col} = 'BUY' then -abs({net_expr})
                    when o.{side_col} = 'SELL' then abs({net_expr})
                    else 0
                end
            """

        row = self.session.execute(
            text(
                f"""
                select coalesce(sum({amount_expr}), 0) as cash_delta
                from {FILL_TABLE} f
                left join {ORDER_TABLE} o
                  on f.{order_id_col} = o.id
                where f.run_id = :fill_run_id
                  and f.portfolio_id = :portfolio_id
                """
            ),
            {
                "fill_run_id": fill_run_id,
                "portfolio_id": portfolio_id,
            },
        ).mappings().one()

        return self._money(self._to_decimal(row["cash_delta"]))

    def _calculate_position_valuation(
            self,
            *,
            position_run_id: int,
            portfolio_id: int,
            snapshot_date: date,
            security_key: str,
            position_columns: list[str],
    ) -> dict[str, Any]:
        rows = self.session.execute(
            text(
                f"""
                select *
                from {POSITION_TABLE}
                where run_id = :position_run_id
                  and portfolio_id = :portfolio_id
                order by {security_key}
                """
            ),
            {
                "position_run_id": position_run_id,
                "portfolio_id": portfolio_id,
            },
        ).mappings().all()

        market_value = Decimal("0")
        total_cost = Decimal("0")
        realized_pnl = Decimal("0")
        open_position_count = 0
        closed_position_count = 0

        for raw_row in rows:
            row = dict(raw_row)
            quantity = self._to_decimal(row.get("quantity"))

            # realized_pnl 必须先累计，closed position 也要计入。
            # 否则清仓标的的已实现收益会被漏掉。
            if "realized_pnl" in row:
                realized_pnl += self._to_decimal(row.get("realized_pnl"))

            if quantity <= 0:
                closed_position_count += 1
                continue

            open_position_count += 1

            security_value = row.get(security_key)
            price = self._resolve_mark_price(
                security_key=security_key,
                security_value=security_value,
                snapshot_date=snapshot_date,
                position_row=row,
            )

            position_market_value = self._money(quantity * price)
            market_value += position_market_value

            cost_amount = self._resolve_cost_amount(row=row, quantity=quantity)
            total_cost += cost_amount

        market_value = self._money(market_value)
        total_cost = self._money(total_cost)
        unrealized_pnl = self._money(market_value - total_cost)
        realized_pnl = self._money(realized_pnl)

        return {
            "market_value": market_value,
            "total_cost": total_cost,
            "unrealized_pnl": unrealized_pnl,
            "realized_pnl": realized_pnl,
            "open_position_count": open_position_count,
            "closed_position_count": closed_position_count,
        }

    def _resolve_mark_price(
        self,
        *,
        security_key: str,
        security_value: Any,
        snapshot_date: date,
        position_row: dict[str, Any],
    ) -> Decimal:
        daily_bar_columns = self._get_columns(DAILY_BAR_TABLE)

        if "instrument_id" in daily_bar_columns and security_key == "instrument_id":
            id_col = "instrument_id"
        elif security_key in daily_bar_columns:
            id_col = security_key
        else:
            return self._resolve_fallback_price(position_row)

        date_col = None
        for col in ["trade_date", "bar_date", "date"]:
            if col in daily_bar_columns:
                date_col = col
                break

        price_col = None
        for col in ["close_price", "close", "adj_close", "close_adj"]:
            if col in daily_bar_columns:
                price_col = col
                break

        if not date_col or not price_col:
            return self._resolve_fallback_price(position_row)

        row = self.session.execute(
            text(
                f"""
                select {price_col} as close_price
                from {DAILY_BAR_TABLE}
                where {id_col} = :security_value
                  and {date_col} = :snapshot_date
                limit 1
                """
            ),
            {
                "security_value": security_value,
                "snapshot_date": snapshot_date,
            },
        ).mappings().first()

        if row is not None:
            price = self._to_decimal(row["close_price"])
            if price > 0:
                return price

        return self._resolve_fallback_price(position_row)

    def _resolve_fallback_price(self, row: dict[str, Any]) -> Decimal:
        for key in [
            "market_price",
            "last_price",
            "close_price",
            "price",
            "avg_cost",
            "cost_price",
        ]:
            if key in row:
                value = self._to_decimal(row.get(key))
                if value > 0:
                    return value

        raise RuntimeError(f"无法解析持仓估值价格: {row}")

    def _resolve_cost_amount(self, *, row: dict[str, Any], quantity: Decimal) -> Decimal:
        for key in ["cost_amount", "total_cost"]:
            if key in row:
                value = self._to_decimal(row.get(key))
                if value >= 0:
                    return self._money(value)

        for key in ["avg_cost", "cost_price", "average_cost"]:
            if key in row:
                price = self._to_decimal(row.get(key))
                if price > 0:
                    return self._money(price * quantity)

        return Decimal("0")

    def _build_snapshot_payload(
        self,
        *,
        snapshot_columns: list[str],
        snapshot_meta: dict[str, dict[str, Any]],
        previous_snapshot: dict[str, Any],
        snapshot_run_id: int,
        previous_snapshot_run_id: int,
        position_run_id: int,
        fill_run_id: int,
        portfolio_id: int,
        snapshot_date: date,
        previous_cash_balance: Decimal,
        cash_delta: Decimal,
        cash_balance: Decimal,
        market_value: Decimal,
        total_equity: Decimal,
        total_cost: Decimal,
        unrealized_pnl: Decimal,
        realized_pnl: Decimal,
        open_position_count: int,
        closed_position_count: int,
    ) -> dict[str, Any]:
        now = datetime.utcnow()
        payload: dict[str, Any] = {}

        skip_columns = {
            "id",
            "created_id",
            "updated_id",
        }

        for column in snapshot_columns:
            if column in skip_columns:
                continue

            if column == "run_id":
                payload[column] = snapshot_run_id
            elif column == "portfolio_id":
                payload[column] = portfolio_id
            elif column in {"snapshot_date", "as_of_date", "effective_date", "trade_date"}:
                payload[column] = snapshot_date
            elif column in {"previous_snapshot_run_id", "source_snapshot_run_id"}:
                payload[column] = previous_snapshot_run_id
            elif column in {"position_run_id", "source_position_run_id"}:
                payload[column] = position_run_id
            elif column in {"fill_run_id", "source_fill_run_id"}:
                payload[column] = fill_run_id
            elif column in {"previous_cash_balance", "cash_before"}:
                payload[column] = previous_cash_balance
            elif column in {"cash_delta", "cash_change"}:
                payload[column] = cash_delta
            elif column in {"cash_balance", "cash", "available_cash", "cash_amount"}:
                payload[column] = cash_balance
            elif column == "market_value":
                payload[column] = market_value
            elif column in {"total_equity", "net_liquidation", "portfolio_value"}:
                payload[column] = total_equity
            elif column in {"total_cost", "cost_amount"}:
                payload[column] = total_cost
            elif column in {"unrealized_pnl", "floating_pnl"}:
                payload[column] = unrealized_pnl
            elif column == "realized_pnl":
                payload[column] = realized_pnl
            elif column in {"position_count", "open_position_count"}:
                payload[column] = open_position_count
            elif column == "closed_position_count":
                payload[column] = closed_position_count
            elif column in {"status", "snapshot_status"}:
                payload[column] = "SUCCESS"
            elif column in {"created_at", "updated_at", "created_time", "updated_time"}:
                payload[column] = now
            else:
                payload[column] = previous_snapshot.get(column)

        self._fill_required_defaults(
            payload=payload,
            column_meta=snapshot_meta,
            snapshot_date=snapshot_date,
            now=now,
        )

        return payload

    def _fill_required_defaults(
        self,
        *,
        payload: dict[str, Any],
        column_meta: dict[str, dict[str, Any]],
        snapshot_date: date,
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
                payload[column] = snapshot_date
            elif "timestamp" in data_type:
                payload[column] = now
            elif "bool" in data_type:
                payload[column] = False
            elif "json" in data_type:
                payload[column] = {}
            else:
                payload[column] = "UNKNOWN"

    def _insert_snapshot(self, payload: dict[str, Any]) -> None:
        columns = list(payload.keys())
        column_sql = ", ".join([f'"{col}"' for col in columns])
        value_sql = ", ".join([f":{col}" for col in columns])

        self.session.execute(
            text(
                f"""
                insert into {SNAPSHOT_TABLE} ({column_sql})
                values ({value_sql})
                """
            ),
            payload,
        )

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


def result_to_dict(result: PortfolioSnapshotM7Result) -> dict[str, Any]:
    return asdict(result)