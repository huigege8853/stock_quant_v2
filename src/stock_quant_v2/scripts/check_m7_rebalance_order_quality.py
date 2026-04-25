from __future__ import annotations

import json
import os
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from stock_quant_v2.db.session import SessionLocal


POSITION_TABLE = "trading_paper_position"
TARGET_TABLE = "trading_paper_target_position"
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


def _resolve_security_key(
    position_columns: list[str],
    target_columns: list[str],
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
        if col in position_columns and col in target_columns and col in order_columns:
            return col
    raise RuntimeError("无法识别共同证券键")


def _resolve_target_quantity_col(target_columns: list[str]) -> str:
    for col in ["target_quantity", "quantity", "target_shares", "shares"]:
        if col in target_columns:
            return col
    raise RuntimeError("无法识别 target quantity 字段")


def _resolve_order_quantity_col(order_columns: list[str]) -> str:
    for col in ["order_quantity", "quantity", "requested_quantity"]:
        if col in order_columns:
            return col
    raise RuntimeError("无法识别 order quantity 字段")


def _resolve_order_side_col(order_columns: list[str]) -> str:
    for col in ["side", "order_side", "direction", "order_direction"]:
        if col in order_columns:
            return col
    raise RuntimeError("无法识别 order side 字段")


def main() -> None:
    order_run_id = _env_int("M7_ORDER_RUN_ID")
    current_position_run_id = _env_int("M7_CURRENT_POSITION_RUN_ID", 116)
    target_position_run_id = _env_int("M7_TARGET_POSITION_RUN_ID")
    portfolio_id = _env_int("M7_PORTFOLIO_ID", 1)

    session = SessionLocal()

    try:
        position_columns = _columns(session, POSITION_TABLE)
        target_columns = _columns(session, TARGET_TABLE)
        order_columns = _columns(session, ORDER_TABLE)

        security_key = _resolve_security_key(
            position_columns,
            target_columns,
            order_columns,
        )
        target_quantity_col = _resolve_target_quantity_col(target_columns)
        order_quantity_col = _resolve_order_quantity_col(order_columns)
        order_side_col = _resolve_order_side_col(order_columns)

        order_summary = session.execute(
            text(
                f"""
                select
                    count(*) as order_count,
                    count(*) filter (where {order_side_col} = 'BUY') as buy_order_count,
                    count(*) filter (where {order_side_col} = 'SELL') as sell_order_count,
                    count(*) filter (where coalesce({order_quantity_col}, 0) <= 0) as non_positive_order_count
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

        target_count = session.execute(
            text(
                f"""
                select count(*) as cnt
                from {TARGET_TABLE}
                where run_id = :target_position_run_id
                  and portfolio_id = :portfolio_id
                  and coalesce({target_quantity_col}, 0) >= 0
                """
            ),
            {
                "target_position_run_id": target_position_run_id,
                "portfolio_id": portfolio_id,
            },
        ).mappings().one()

        current_count = session.execute(
            text(
                """
                select count(*) as cnt
                from trading_paper_position
                where run_id = :current_position_run_id
                  and portfolio_id = :portfolio_id
                  and coalesce(quantity, 0) > 0
                """
            ),
            {
                "current_position_run_id": current_position_run_id,
                "portfolio_id": portfolio_id,
            },
        ).mappings().one()

        checks = {
            "current_position_exists": int(current_count["cnt"] or 0) > 0,
            "target_position_exists": int(target_count["cnt"] or 0) > 0,
            "order_quantity_positive_check": int(order_summary["non_positive_order_count"] or 0) == 0,
            "sell_quantity_le_available_check": int(sell_violation["sell_gt_available_count"] or 0) == 0,
        }

        overall_status = "PASS" if all(checks.values()) else "FAIL"

        result = {
            "module": "M7",
            "stage": "M7.2",
            "order_run_id": order_run_id,
            "current_position_run_id": current_position_run_id,
            "target_position_run_id": target_position_run_id,
            "portfolio_id": portfolio_id,
            "overall_status": overall_status,
            "checks": checks,
            "resolved_columns": {
                "security_key": security_key,
                "target_quantity_col": target_quantity_col,
                "order_quantity_col": order_quantity_col,
                "order_side_col": order_side_col,
            },
            "summary": {
                "current_position_count": int(current_count["cnt"] or 0),
                "target_position_count": int(target_count["cnt"] or 0),
                "order_count": int(order_summary["order_count"] or 0),
                "buy_order_count": int(order_summary["buy_order_count"] or 0),
                "sell_order_count": int(order_summary["sell_order_count"] or 0),
                "non_positive_order_count": int(order_summary["non_positive_order_count"] or 0),
                "sell_gt_available_count": int(sell_violation["sell_gt_available_count"] or 0),
            },
        }

        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

        if overall_status != "PASS":
            raise SystemExit(1)

    finally:
        session.close()


if __name__ == "__main__":
    main()