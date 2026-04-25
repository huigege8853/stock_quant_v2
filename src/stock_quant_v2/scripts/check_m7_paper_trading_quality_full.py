from __future__ import annotations

import json
import os
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from stock_quant_v2.db.session import SessionLocal


POSITION_TABLE = "trading_paper_position"
ORDER_TABLE = "trading_paper_order"
FILL_TABLE = "trading_paper_fill"
SNAPSHOT_TABLE = "trading_paper_portfolio_snapshot"
TARGET_TABLE = "trading_paper_target_position"

MONEY_EPS = Decimal("0.000001")


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


def _money_equal(left: Any, right: Any) -> bool:
    return abs(_to_decimal(left) - _to_decimal(right)) <= MONEY_EPS


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


def _optional_existing(columns: list[str], candidates: list[str]) -> str | None:
    for col in candidates:
        if col in columns:
            return col
    return None


def _all_checks_pass(checks: dict[str, Any]) -> bool:
    for value in checks.values():
        if isinstance(value, dict):
            if not _all_checks_pass(value):
                return False
        elif value is not True:
            return False
    return True


def _position_summary(session, *, run_id: int, portfolio_id: int) -> dict[str, Any]:
    cols = _columns(session, POSITION_TABLE)
    realized_expr = "coalesce(sum(realized_pnl), 0)" if "realized_pnl" in cols else "0"

    row = session.execute(
        text(
            f"""
            select
                count(*) as position_count,
                count(*) filter (where coalesce(quantity, 0) > 0) as open_position_count,
                count(*) filter (where coalesce(quantity, 0) = 0) as closed_position_count,
                coalesce(sum(quantity), 0) as quantity_total,
                coalesce(sum(available_quantity), 0) as available_quantity_total,
                {realized_expr} as realized_pnl_total,
                count(*) filter (where quantity < 0) as negative_quantity_count,
                count(*) filter (where available_quantity < 0) as negative_available_quantity_count,
                count(*) filter (where available_quantity > quantity) as available_gt_quantity_count
            from {POSITION_TABLE}
            where run_id = :run_id
              and portfolio_id = :portfolio_id
            """
        ),
        {"run_id": run_id, "portfolio_id": portfolio_id},
    ).mappings().one()

    return {
        "position_count": int(row["position_count"] or 0),
        "open_position_count": int(row["open_position_count"] or 0),
        "closed_position_count": int(row["closed_position_count"] or 0),
        "quantity_total": _to_decimal(row["quantity_total"]),
        "available_quantity_total": _to_decimal(row["available_quantity_total"]),
        "realized_pnl_total": _to_decimal(row["realized_pnl_total"]),
        "negative_quantity_count": int(row["negative_quantity_count"] or 0),
        "negative_available_quantity_count": int(row["negative_available_quantity_count"] or 0),
        "available_gt_quantity_count": int(row["available_gt_quantity_count"] or 0),
    }


def _resolve_security_key(
    *,
    position_columns: list[str],
    order_columns: list[str],
) -> str:
    for col in ["instrument_id", "security_id", "ticker", "symbol", "instrument_code", "vendor_symbol"]:
        if col in position_columns and col in order_columns:
            return col
    raise RuntimeError("无法识别 position / order 共同证券键")


def _order_summary(
    session,
    *,
    order_run_id: int,
    current_position_run_id: int,
    portfolio_id: int,
) -> dict[str, Any]:
    position_columns = _columns(session, POSITION_TABLE)
    order_columns = _columns(session, ORDER_TABLE)

    security_key = _resolve_security_key(
        position_columns=position_columns,
        order_columns=order_columns,
    )
    order_side_col = _first_existing(
        order_columns,
        ["order_side", "side", "direction", "order_direction"],
        ORDER_TABLE,
    )
    order_quantity_col = _first_existing(
        order_columns,
        ["order_quantity", "quantity", "requested_quantity"],
        ORDER_TABLE,
    )

    summary = session.execute(
        text(
            f"""
            select
                count(*) as order_count,
                count(*) filter (where {order_side_col} = 'BUY') as buy_order_count,
                count(*) filter (where {order_side_col} = 'SELL') as sell_order_count,
                count(*) filter (where coalesce({order_quantity_col}, 0) <= 0) as non_positive_order_count,
                coalesce(sum(case when {order_side_col} = 'BUY' then {order_quantity_col} else 0 end), 0) as buy_quantity_total,
                coalesce(sum(case when {order_side_col} = 'SELL' then {order_quantity_col} else 0 end), 0) as sell_quantity_total
            from {ORDER_TABLE}
            where run_id = :order_run_id
              and portfolio_id = :portfolio_id
            """
        ),
        {"order_run_id": order_run_id, "portfolio_id": portfolio_id},
    ).mappings().one()

    sell_violation = session.execute(
        text(
            f"""
            with sell_orders as (
                select
                    {security_key} as security_key,
                    coalesce({order_quantity_col}, 0) as sell_quantity
                from {ORDER_TABLE}
                where run_id = :order_run_id
                  and portfolio_id = :portfolio_id
                  and {order_side_col} = 'SELL'
            ),
            positions as (
                select
                    {security_key} as security_key,
                    coalesce(available_quantity, 0) as available_quantity
                from {POSITION_TABLE}
                where run_id = :current_position_run_id
                  and portfolio_id = :portfolio_id
            )
            select
                count(*) as sell_order_count,
                count(*) filter (
                    where sell_orders.sell_quantity > coalesce(positions.available_quantity, 0)
                ) as sell_gt_available_count
            from sell_orders
            left join positions
              on sell_orders.security_key = positions.security_key
            """
        ),
        {
            "order_run_id": order_run_id,
            "current_position_run_id": current_position_run_id,
            "portfolio_id": portfolio_id,
        },
    ).mappings().one()

    return {
        "security_key": security_key,
        "order_side_col": order_side_col,
        "order_quantity_col": order_quantity_col,
        "order_count": int(summary["order_count"] or 0),
        "buy_order_count": int(summary["buy_order_count"] or 0),
        "sell_order_count": int(summary["sell_order_count"] or 0),
        "non_positive_order_count": int(summary["non_positive_order_count"] or 0),
        "buy_quantity_total": _to_decimal(summary["buy_quantity_total"]),
        "sell_quantity_total": _to_decimal(summary["sell_quantity_total"]),
        "sell_gt_available_count": int(sell_violation["sell_gt_available_count"] or 0),
    }


def _fill_summary(
    session,
    *,
    fill_run_id: int,
    portfolio_id: int,
) -> dict[str, Any]:
    fill_columns = _columns(session, FILL_TABLE)
    order_columns = _columns(session, ORDER_TABLE)

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

    stamp_col = _optional_existing(fill_columns, ["stamp_duty", "stamp_duty_amount"])
    if stamp_col:
        buy_stamp_expr = f"coalesce(sum(case when o.{order_side_col} = 'BUY' then f.{stamp_col} else 0 end), 0)"
        sell_stamp_expr = f"coalesce(sum(case when o.{order_side_col} = 'SELL' then f.{stamp_col} else 0 end), 0)"
    else:
        buy_stamp_expr = "0"
        sell_stamp_expr = "0"

    summary = session.execute(
        text(
            f"""
            select
                count(*) as fill_count,
                count(*) filter (where o.{order_side_col} = 'BUY') as buy_fill_count,
                count(*) filter (where o.{order_side_col} = 'SELL') as sell_fill_count,
                coalesce(sum(case when o.{order_side_col} = 'BUY' then f.{fill_quantity_col} else 0 end), 0) as buy_quantity_total,
                coalesce(sum(case when o.{order_side_col} = 'SELL' then f.{fill_quantity_col} else 0 end), 0) as sell_quantity_total,
                coalesce(sum({amount_expr}), 0) as cash_delta,
                {buy_stamp_expr} as buy_stamp_duty_total,
                {sell_stamp_expr} as sell_stamp_duty_total,
                count(*) filter (where o.id is null) as missing_order_count
            from {FILL_TABLE} f
            left join {ORDER_TABLE} o
              on f.{order_id_col} = o.id
            where f.run_id = :fill_run_id
              and f.portfolio_id = :portfolio_id
            """
        ),
        {"fill_run_id": fill_run_id, "portfolio_id": portfolio_id},
    ).mappings().one()

    return {
        "order_id_col": order_id_col,
        "order_side_col": order_side_col,
        "fill_quantity_col": fill_quantity_col,
        "fill_price_col": fill_price_col,
        "stamp_col": stamp_col,
        "fill_count": int(summary["fill_count"] or 0),
        "buy_fill_count": int(summary["buy_fill_count"] or 0),
        "sell_fill_count": int(summary["sell_fill_count"] or 0),
        "buy_quantity_total": _to_decimal(summary["buy_quantity_total"]),
        "sell_quantity_total": _to_decimal(summary["sell_quantity_total"]),
        "cash_delta": _to_decimal(summary["cash_delta"]),
        "buy_stamp_duty_total": _to_decimal(summary["buy_stamp_duty_total"]),
        "sell_stamp_duty_total": _to_decimal(summary["sell_stamp_duty_total"]),
        "missing_order_count": int(summary["missing_order_count"] or 0),
    }


def _snapshot_summary(
    session,
    *,
    snapshot_run_id: int,
    previous_snapshot_run_id: int,
    portfolio_id: int,
) -> dict[str, Any]:
    snapshot_columns = _columns(session, SNAPSHOT_TABLE)

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
    realized_pnl_col = _optional_existing(snapshot_columns, ["realized_pnl"])
    open_position_count_col = _optional_existing(snapshot_columns, ["open_position_count", "position_count"])
    closed_position_count_col = _optional_existing(snapshot_columns, ["closed_position_count"])

    current = session.execute(
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
        {"snapshot_run_id": snapshot_run_id, "portfolio_id": portfolio_id},
    ).mappings().first()

    previous = session.execute(
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

    if current is None:
        raise RuntimeError(f"找不到 snapshot run: {snapshot_run_id}")
    if previous is None:
        raise RuntimeError(f"找不到 previous snapshot run: {previous_snapshot_run_id}")

    current = dict(current)
    previous = dict(previous)

    return {
        "cash_col": cash_col,
        "market_value_col": market_value_col,
        "total_equity_col": total_equity_col,
        "realized_pnl_col": realized_pnl_col,
        "open_position_count_col": open_position_count_col,
        "closed_position_count_col": closed_position_count_col,
        "snapshot_exists": True,
        "previous_snapshot_exists": True,
        "previous_cash": _to_decimal(previous.get(cash_col)),
        "cash_balance": _to_decimal(current.get(cash_col)),
        "market_value": _to_decimal(current.get(market_value_col)),
        "total_equity": _to_decimal(current.get(total_equity_col)),
        "realized_pnl": _to_decimal(current.get(realized_pnl_col)) if realized_pnl_col else Decimal("0"),
        "open_position_count": int(current.get(open_position_count_col) or 0) if open_position_count_col else None,
        "closed_position_count": int(current.get(closed_position_count_col) or 0) if closed_position_count_col else None,
    }


def _target_exists(session, *, target_position_run_id: int, portfolio_id: int) -> bool:
    row = session.execute(
        text(
            f"""
            select count(*) as cnt
            from {TARGET_TABLE}
            where run_id = :target_position_run_id
              and portfolio_id = :portfolio_id
            """
        ),
        {
            "target_position_run_id": target_position_run_id,
            "portfolio_id": portfolio_id,
        },
    ).mappings().one()

    return int(row["cnt"] or 0) > 0


def main() -> None:
    portfolio_id = _env_int("M7_PORTFOLIO_ID", 1)

    carry_source_position_run_id = _env_int("M7_CARRY_SOURCE_POSITION_RUN_ID", 114)
    carry_target_position_run_id = _env_int("M7_CARRY_TARGET_POSITION_RUN_ID", 116)

    current_position_run_id = _env_int("M7_CURRENT_POSITION_RUN_ID", carry_target_position_run_id)
    target_position_run_id = _env_int("M7_TARGET_POSITION_RUN_ID", 111)

    order_run_id = _env_int("M7_ORDER_RUN_ID", 141)
    fill_run_id = _env_int("M7_FILL_RUN_ID", 142)
    new_position_run_id = _env_int("M7_NEW_POSITION_RUN_ID", 143)
    snapshot_run_id = _env_int("M7_SNAPSHOT_RUN_ID", 144)
    previous_snapshot_run_id = _env_int("M7_PREVIOUS_SNAPSHOT_RUN_ID", 114)

    session = SessionLocal()

    try:
        carry_source = _position_summary(
            session,
            run_id=carry_source_position_run_id,
            portfolio_id=portfolio_id,
        )
        carry_target = _position_summary(
            session,
            run_id=carry_target_position_run_id,
            portfolio_id=portfolio_id,
        )

        current_position = _position_summary(
            session,
            run_id=current_position_run_id,
            portfolio_id=portfolio_id,
        )
        new_position = _position_summary(
            session,
            run_id=new_position_run_id,
            portfolio_id=portfolio_id,
        )

        order = _order_summary(
            session,
            order_run_id=order_run_id,
            current_position_run_id=current_position_run_id,
            portfolio_id=portfolio_id,
        )
        fill = _fill_summary(
            session,
            fill_run_id=fill_run_id,
            portfolio_id=portfolio_id,
        )
        snapshot = _snapshot_summary(
            session,
            snapshot_run_id=snapshot_run_id,
            previous_snapshot_run_id=previous_snapshot_run_id,
            portfolio_id=portfolio_id,
        )

        target_exists = _target_exists(
            session,
            target_position_run_id=target_position_run_id,
            portfolio_id=portfolio_id,
        )

        expected_new_quantity_total = (
            current_position["quantity_total"]
            + fill["buy_quantity_total"]
            - fill["sell_quantity_total"]
        )
        actual_available_gap = (
            new_position["quantity_total"]
            - new_position["available_quantity_total"]
        )
        expected_available_gap_from_today_buy = fill["buy_quantity_total"]

        expected_cash = snapshot["previous_cash"] + fill["cash_delta"]
        expected_total_equity = snapshot["cash_balance"] + snapshot["market_value"]

        checks = {
            "m7_1_carry_forward": {
                "source_position_exists": carry_source["position_count"] > 0,
                "target_position_exists": carry_target["position_count"] > 0,
                "position_count_check": carry_source["position_count"] == carry_target["position_count"],
                "quantity_total_check": carry_source["quantity_total"] == carry_target["quantity_total"],
                "t_plus_1_available_quantity_check": carry_target["available_quantity_total"] == carry_target["quantity_total"],
                "negative_quantity_check": carry_target["negative_quantity_count"] == 0,
                "negative_available_quantity_check": carry_target["negative_available_quantity_count"] == 0,
                "available_quantity_le_quantity_check": carry_target["available_gt_quantity_count"] == 0,
            },
            "m7_2_rebalance_order": {
                "current_position_exists": current_position["position_count"] > 0,
                "target_position_exists": target_exists,
                "order_exists": order["order_count"] > 0,
                "buy_order_exists": order["buy_order_count"] > 0,
                "sell_order_exists": order["sell_order_count"] > 0,
                "order_quantity_positive_check": order["non_positive_order_count"] == 0,
                "sell_quantity_le_available_check": order["sell_gt_available_count"] == 0,
            },
            "m7_3a_fill": {
                "fill_exists": fill["fill_count"] > 0,
                "fill_order_join_check": fill["missing_order_count"] == 0,
                "fill_count_eq_order_count_check": fill["fill_count"] == order["order_count"],
                "buy_fill_count_check": fill["buy_fill_count"] == order["buy_order_count"],
                "sell_fill_count_check": fill["sell_fill_count"] == order["sell_order_count"],
                "buy_stamp_duty_zero_check": fill["buy_stamp_duty_total"] == 0,
                "sell_stamp_duty_positive_check": (
                    fill["sell_stamp_duty_total"] > 0 if fill["sell_fill_count"] > 0 else True
                ),
                "cash_delta_nonzero_check": fill["cash_delta"] != 0,
            },
            "m7_3b_position_after_fill": {
                "new_position_exists": new_position["position_count"] > 0,
                "quantity_total_check": new_position["quantity_total"] == expected_new_quantity_total,
                "negative_quantity_check": new_position["negative_quantity_count"] == 0,
                "negative_available_quantity_check": new_position["negative_available_quantity_count"] == 0,
                "available_quantity_le_quantity_check": new_position["available_gt_quantity_count"] == 0,
                "t_plus_1_buy_not_available_check": actual_available_gap == expected_available_gap_from_today_buy,
            },
            "m7_3c_snapshot": {
                "snapshot_exists": snapshot["snapshot_exists"],
                "previous_snapshot_exists": snapshot["previous_snapshot_exists"],
                "cash_balance_check": _money_equal(snapshot["cash_balance"], expected_cash),
                "total_equity_check": _money_equal(snapshot["total_equity"], expected_total_equity),
                "realized_pnl_check": _money_equal(snapshot["realized_pnl"], new_position["realized_pnl_total"]),
                "open_position_count_check": (
                    snapshot["open_position_count"] == new_position["open_position_count"]
                    if snapshot["open_position_count"] is not None
                    else True
                ),
                "closed_position_count_check": (
                    snapshot["closed_position_count"] == new_position["closed_position_count"]
                    if snapshot["closed_position_count"] is not None
                    else True
                ),
            },
        }

        overall_status = "PASS" if _all_checks_pass(checks) else "FAIL"

        result = {
            "module": "M7",
            "stage": "M7.5",
            "overall_status": overall_status,
            "runs": {
                "carry_source_position_run_id": carry_source_position_run_id,
                "carry_target_position_run_id": carry_target_position_run_id,
                "current_position_run_id": current_position_run_id,
                "target_position_run_id": target_position_run_id,
                "order_run_id": order_run_id,
                "fill_run_id": fill_run_id,
                "new_position_run_id": new_position_run_id,
                "snapshot_run_id": snapshot_run_id,
                "previous_snapshot_run_id": previous_snapshot_run_id,
                "portfolio_id": portfolio_id,
            },
            "checks": checks,
            "summary": {
                "order": {
                    "order_count": order["order_count"],
                    "buy_order_count": order["buy_order_count"],
                    "sell_order_count": order["sell_order_count"],
                    "buy_quantity_total": str(order["buy_quantity_total"]),
                    "sell_quantity_total": str(order["sell_quantity_total"]),
                },
                "fill": {
                    "fill_count": fill["fill_count"],
                    "buy_fill_count": fill["buy_fill_count"],
                    "sell_fill_count": fill["sell_fill_count"],
                    "buy_quantity_total": str(fill["buy_quantity_total"]),
                    "sell_quantity_total": str(fill["sell_quantity_total"]),
                    "cash_delta": str(fill["cash_delta"]),
                    "buy_stamp_duty_total": str(fill["buy_stamp_duty_total"]),
                    "sell_stamp_duty_total": str(fill["sell_stamp_duty_total"]),
                },
                "position": {
                    "current_quantity_total": str(current_position["quantity_total"]),
                    "new_quantity_total": str(new_position["quantity_total"]),
                    "new_available_quantity_total": str(new_position["available_quantity_total"]),
                    "open_position_count": new_position["open_position_count"],
                    "closed_position_count": new_position["closed_position_count"],
                    "realized_pnl_total": str(new_position["realized_pnl_total"]),
                    "expected_new_quantity_total": str(expected_new_quantity_total),
                    "actual_available_gap": str(actual_available_gap),
                    "expected_available_gap_from_today_buy": str(expected_available_gap_from_today_buy),
                },
                "snapshot": {
                    "previous_cash": str(snapshot["previous_cash"]),
                    "cash_balance": str(snapshot["cash_balance"]),
                    "market_value": str(snapshot["market_value"]),
                    "total_equity": str(snapshot["total_equity"]),
                    "realized_pnl": str(snapshot["realized_pnl"]),
                    "expected_cash": str(expected_cash),
                    "expected_total_equity": str(expected_total_equity),
                },
            },
            "resolved_columns": {
                "security_key": order["security_key"],
                "order_side_col": order["order_side_col"],
                "order_quantity_col": order["order_quantity_col"],
                "fill_order_id_col": fill["order_id_col"],
                "fill_quantity_col": fill["fill_quantity_col"],
                "fill_price_col": fill["fill_price_col"],
                "fill_stamp_col": fill["stamp_col"],
                "snapshot_cash_col": snapshot["cash_col"],
                "snapshot_total_equity_col": snapshot["total_equity_col"],
                "snapshot_realized_pnl_col": snapshot["realized_pnl_col"],
            },
        }

        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

        if overall_status != "PASS":
            raise SystemExit(1)

    finally:
        session.close()


if __name__ == "__main__":
    main()