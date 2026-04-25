from __future__ import annotations

import json
import os
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from stock_quant_v2.db.session import SessionLocal


SNAPSHOT_TABLE = "trading_paper_portfolio_snapshot"
POSITION_TABLE = "trading_paper_position"
FILL_TABLE = "trading_paper_fill"
ORDER_TABLE = "trading_paper_order"


def _env_int(name: str, default: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        if default is None:
            raise RuntimeError(f"缺少环境变量: {name}")
        return default
    return int(raw)


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _columns(session, table_name: str) -> list[str]:
    rows = session.execute(
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


def _first_existing(columns: list[str], candidates: list[str], table_name: str) -> str:
    for col in candidates:
        if col in columns:
            return col
    raise RuntimeError(f"{table_name} 无法识别字段候选: {candidates}")


def main() -> None:
    snapshot_run_id = _env_int("M7_SNAPSHOT_RUN_ID", 133)
    previous_snapshot_run_id = _env_int("M7_PREVIOUS_SNAPSHOT_RUN_ID", 114)
    position_run_id = _env_int("M7_POSITION_RUN_ID", 131)
    fill_run_id = _env_int("M7_FILL_RUN_ID", 126)
    portfolio_id = _env_int("M7_PORTFOLIO_ID", 1)

    session = SessionLocal()

    try:
        snapshot_columns = _columns(session, SNAPSHOT_TABLE)
        fill_columns = _columns(session, FILL_TABLE)
        order_columns = _columns(session, ORDER_TABLE)

        cash_col = _first_existing(
            snapshot_columns,
            ["cash_balance", "cash", "available_cash", "cash_amount"],
            SNAPSHOT_TABLE,
        )
        market_value_col = _first_existing(
            snapshot_columns,
            ["market_value"],
            SNAPSHOT_TABLE,
        )
        total_equity_col = _first_existing(
            snapshot_columns,
            ["total_equity", "net_liquidation", "portfolio_value"],
            SNAPSHOT_TABLE,
        )
        realized_pnl_col = (
            "realized_pnl" if "realized_pnl" in snapshot_columns else None
        )
        position_count_col = (
            "position_count"
            if "position_count" in snapshot_columns
            else "open_position_count"
            if "open_position_count" in snapshot_columns
            else None
        )
        closed_position_count_col = (
            "closed_position_count" if "closed_position_count" in snapshot_columns else None
        )

        order_id_col = _first_existing(
            fill_columns,
            ["order_id", "paper_order_id"],
            FILL_TABLE,
        )
        order_side_col = _first_existing(
            order_columns,
            ["order_side", "side", "direction", "order_direction"],
            ORDER_TABLE,
        )
        fill_quantity_col = _first_existing(
            fill_columns,
            ["fill_quantity", "quantity", "filled_quantity"],
            FILL_TABLE,
        )
        fill_price_col = _first_existing(
            fill_columns,
            ["fill_price", "price"],
            FILL_TABLE,
        )

        current_snapshot = session.execute(
            text(
                f"""
                select *
                from {SNAPSHOT_TABLE}
                where run_id = :snapshot_run_id
                  and portfolio_id = :portfolio_id
                order by id desc
                limit 1
                """
            ),
            {
                "snapshot_run_id": snapshot_run_id,
                "portfolio_id": portfolio_id,
            },
        ).mappings().first()

        previous_snapshot = session.execute(
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

        if current_snapshot is None:
            raise RuntimeError(f"找不到当前 snapshot run: {snapshot_run_id}")

        if previous_snapshot is None:
            raise RuntimeError(f"找不到上一 snapshot run: {previous_snapshot_run_id}")

        current_snapshot = dict(current_snapshot)
        previous_snapshot = dict(previous_snapshot)

        previous_cash = _to_decimal(previous_snapshot.get(cash_col))
        snapshot_cash = _to_decimal(current_snapshot.get(cash_col))
        snapshot_market_value = _to_decimal(current_snapshot.get(market_value_col))
        snapshot_total_equity = _to_decimal(current_snapshot.get(total_equity_col))
        snapshot_realized_pnl = (
            _to_decimal(current_snapshot.get(realized_pnl_col))
            if realized_pnl_col
            else Decimal("0")
        )

        gross_expr = None
        for col in ["gross_amount", "fill_gross_amount"]:
            if col in fill_columns:
                gross_expr = f"coalesce(f.{col}, f.{fill_quantity_col} * f.{fill_price_col})"
                break
        if gross_expr is None:
            gross_expr = f"(f.{fill_quantity_col} * f.{fill_price_col})"

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
                    when o.{order_side_col} = 'BUY' then -abs({net_expr})
                    when o.{order_side_col} = 'SELL' then abs({net_expr})
                    else 0
                end
            """
        else:
            amount_expr = f"""
                case
                    when o.{order_side_col} = 'BUY' then -abs({net_expr})
                    when o.{order_side_col} = 'SELL' then abs({net_expr})
                    else 0
                end
            """

        fill_summary = session.execute(
            text(
                f"""
                select
                    count(*) as fill_count,
                    count(*) filter (where o.{order_side_col} = 'BUY') as buy_fill_count,
                    count(*) filter (where o.{order_side_col} = 'SELL') as sell_fill_count,
                    coalesce(sum({amount_expr}), 0) as cash_delta,
                    count(*) filter (where o.id is null) as missing_order_count
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

        position_summary = session.execute(
            text(
                f"""
                select
                    count(*) as position_count,
                    count(*) filter (where coalesce(quantity, 0) > 0) as open_position_count,
                    count(*) filter (where coalesce(quantity, 0) = 0) as closed_position_count,
                    coalesce(sum(quantity), 0) as quantity_total,
                    coalesce(sum(available_quantity), 0) as available_quantity_total,
                    coalesce(sum(realized_pnl), 0) as realized_pnl_total,
                    count(*) filter (where quantity < 0) as negative_quantity_count,
                    count(*) filter (where available_quantity < 0) as negative_available_quantity_count,
                    count(*) filter (where available_quantity > quantity) as available_gt_quantity_count
                from {POSITION_TABLE}
                where run_id = :position_run_id
                  and portfolio_id = :portfolio_id
                """
            ),
            {
                "position_run_id": position_run_id,
                "portfolio_id": portfolio_id,
            },
        ).mappings().one()

        cash_delta = _to_decimal(fill_summary["cash_delta"])
        expected_cash = previous_cash + cash_delta
        expected_total_equity = snapshot_cash + snapshot_market_value
        position_realized_pnl = _to_decimal(position_summary["realized_pnl_total"])

        snapshot_open_position_count = (
            int(current_snapshot.get(position_count_col) or 0)
            if position_count_col
            else None
        )
        snapshot_closed_position_count = (
            int(current_snapshot.get(closed_position_count_col) or 0)
            if closed_position_count_col
            else None
        )

        checks = {
            "snapshot_exists": True,
            "previous_snapshot_exists": True,
            "fill_exists": int(fill_summary["fill_count"] or 0) > 0,
            "fill_order_join_check": int(fill_summary["missing_order_count"] or 0) == 0,
            "cash_balance_check": snapshot_cash == expected_cash,
            "total_equity_check": snapshot_total_equity == expected_total_equity,
            "negative_quantity_check": int(position_summary["negative_quantity_count"] or 0) == 0,
            "negative_available_quantity_check": int(position_summary["negative_available_quantity_count"] or 0) == 0,
            "available_quantity_le_quantity_check": int(position_summary["available_gt_quantity_count"] or 0) == 0,
            "realized_pnl_check": snapshot_realized_pnl == position_realized_pnl,
        }

        if snapshot_open_position_count is not None:
            checks["open_position_count_check"] = (
                snapshot_open_position_count
                == int(position_summary["open_position_count"] or 0)
            )

        if snapshot_closed_position_count is not None:
            checks["closed_position_count_check"] = (
                snapshot_closed_position_count
                == int(position_summary["closed_position_count"] or 0)
            )

        overall_status = "PASS" if all(checks.values()) else "FAIL"

        result = {
            "module": "M7",
            "stage": "M7.3-C",
            "snapshot_run_id": snapshot_run_id,
            "previous_snapshot_run_id": previous_snapshot_run_id,
            "position_run_id": position_run_id,
            "fill_run_id": fill_run_id,
            "portfolio_id": portfolio_id,
            "overall_status": overall_status,
            "checks": checks,
            "snapshot": {
                "cash_balance": str(snapshot_cash),
                "market_value": str(snapshot_market_value),
                "total_equity": str(snapshot_total_equity),
                "realized_pnl": str(snapshot_realized_pnl),
                "open_position_count": snapshot_open_position_count,
                "closed_position_count": snapshot_closed_position_count,
            },
            "expected": {
                "previous_cash": str(previous_cash),
                "cash_delta": str(cash_delta),
                "expected_cash": str(expected_cash),
                "expected_total_equity": str(expected_total_equity),
                "position_realized_pnl": str(position_realized_pnl),
            },
            "fill": {
                "fill_count": int(fill_summary["fill_count"] or 0),
                "buy_fill_count": int(fill_summary["buy_fill_count"] or 0),
                "sell_fill_count": int(fill_summary["sell_fill_count"] or 0),
                "missing_order_count": int(fill_summary["missing_order_count"] or 0),
            },
            "position": {
                "position_count": int(position_summary["position_count"] or 0),
                "open_position_count": int(position_summary["open_position_count"] or 0),
                "closed_position_count": int(position_summary["closed_position_count"] or 0),
                "quantity_total": str(_to_decimal(position_summary["quantity_total"])),
                "available_quantity_total": str(_to_decimal(position_summary["available_quantity_total"])),
            },
        }

        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

        if overall_status != "PASS":
            raise SystemExit(1)

    finally:
        session.close()


if __name__ == "__main__":
    main()