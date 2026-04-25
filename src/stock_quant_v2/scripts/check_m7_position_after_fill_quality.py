from __future__ import annotations

import json
import os
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from stock_quant_v2.db.session import SessionLocal


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


def _resolve_order_side_col(order_columns: list[str]) -> str:
    for col in ["order_side", "side", "direction", "order_direction"]:
        if col in order_columns:
            return col
    raise RuntimeError("order 表无法识别 side 字段")


def _resolve_fill_quantity_col(fill_columns: list[str]) -> str:
    for col in ["fill_quantity", "quantity", "filled_quantity"]:
        if col in fill_columns:
            return col
    raise RuntimeError("fill 表无法识别 quantity 字段")


def _resolve_order_id_col(fill_columns: list[str]) -> str:
    for col in ["order_id", "paper_order_id"]:
        if col in fill_columns:
            return col
    raise RuntimeError("fill 表缺少 order_id / paper_order_id，无法关联 order 解析买卖方向")


def _summary_position(session, *, run_id: int, portfolio_id: int) -> dict[str, Any]:
    row = session.execute(
        text(
            f"""
            select
                count(*) as position_count,
                count(*) filter (where coalesce(quantity, 0) > 0) as open_position_count,
                count(*) filter (where coalesce(quantity, 0) = 0) as closed_position_count,
                coalesce(sum(quantity), 0) as quantity_total,
                coalesce(sum(available_quantity), 0) as available_quantity_total,
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
        "negative_quantity_count": int(row["negative_quantity_count"] or 0),
        "negative_available_quantity_count": int(row["negative_available_quantity_count"] or 0),
        "available_gt_quantity_count": int(row["available_gt_quantity_count"] or 0),
    }


def main() -> None:
    current_position_run_id = _env_int("M7_CURRENT_POSITION_RUN_ID", 116)
    new_position_run_id = _env_int("M7_NEW_POSITION_RUN_ID")
    fill_run_id = _env_int("M7_FILL_RUN_ID")
    portfolio_id = _env_int("M7_PORTFOLIO_ID", 1)

    session = SessionLocal()

    try:
        fill_columns = _columns(session, FILL_TABLE)
        order_columns = _columns(session, ORDER_TABLE)

        order_id_col = _resolve_order_id_col(fill_columns)
        side_col = _resolve_order_side_col(order_columns)
        quantity_col = _resolve_fill_quantity_col(fill_columns)

        current_summary = _summary_position(
            session,
            run_id=current_position_run_id,
            portfolio_id=portfolio_id,
        )
        new_summary = _summary_position(
            session,
            run_id=new_position_run_id,
            portfolio_id=portfolio_id,
        )

        fill_summary = session.execute(
            text(
                f"""
                select
                    count(*) as fill_count,
                    count(*) filter (where o.{side_col} = 'BUY') as buy_fill_count,
                    count(*) filter (where o.{side_col} = 'SELL') as sell_fill_count,
                    coalesce(sum(case when o.{side_col} = 'BUY' then f.{quantity_col} else 0 end), 0) as buy_quantity_total,
                    coalesce(sum(case when o.{side_col} = 'SELL' then f.{quantity_col} else 0 end), 0) as sell_quantity_total,
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

        buy_quantity_total = _to_decimal(fill_summary["buy_quantity_total"])
        sell_quantity_total = _to_decimal(fill_summary["sell_quantity_total"])

        expected_new_quantity_total = (
            current_summary["quantity_total"]
            + buy_quantity_total
            - sell_quantity_total
        )

        # A 股 T+1：当日 BUY 不增加 available_quantity。
        expected_available_gap_from_today_buy = buy_quantity_total
        actual_available_gap = (
            new_summary["quantity_total"] - new_summary["available_quantity_total"]
        )

        checks = {
            "current_position_exists": current_summary["position_count"] > 0,
            "new_position_exists": new_summary["position_count"] > 0,
            "fill_exists": int(fill_summary["fill_count"] or 0) > 0,
            "fill_order_join_check": int(fill_summary["missing_order_count"] or 0) == 0,
            "quantity_total_check": new_summary["quantity_total"] == expected_new_quantity_total,
            "negative_quantity_check": new_summary["negative_quantity_count"] == 0,
            "negative_available_quantity_check": new_summary["negative_available_quantity_count"] == 0,
            "available_quantity_le_quantity_check": new_summary["available_gt_quantity_count"] == 0,
            "t_plus_1_buy_not_available_check": actual_available_gap == expected_available_gap_from_today_buy,
        }

        overall_status = "PASS" if all(checks.values()) else "FAIL"

        result = {
            "module": "M7",
            "stage": "M7.3-B",
            "current_position_run_id": current_position_run_id,
            "new_position_run_id": new_position_run_id,
            "fill_run_id": fill_run_id,
            "portfolio_id": portfolio_id,
            "overall_status": overall_status,
            "checks": checks,
            "resolved_columns": {
                "fill_order_id_col": order_id_col,
                "order_side_col": side_col,
                "fill_quantity_col": quantity_col,
            },
            "current_position": {
                **current_summary,
                "quantity_total": str(current_summary["quantity_total"]),
                "available_quantity_total": str(current_summary["available_quantity_total"]),
            },
            "new_position": {
                **new_summary,
                "quantity_total": str(new_summary["quantity_total"]),
                "available_quantity_total": str(new_summary["available_quantity_total"]),
            },
            "fill": {
                "fill_count": int(fill_summary["fill_count"] or 0),
                "buy_fill_count": int(fill_summary["buy_fill_count"] or 0),
                "sell_fill_count": int(fill_summary["sell_fill_count"] or 0),
                "buy_quantity_total": str(buy_quantity_total),
                "sell_quantity_total": str(sell_quantity_total),
                "missing_order_count": int(fill_summary["missing_order_count"] or 0),
            },
            "expected_new_quantity_total": str(expected_new_quantity_total),
            "actual_available_gap": str(actual_available_gap),
            "expected_available_gap_from_today_buy": str(expected_available_gap_from_today_buy),
        }

        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

        if overall_status != "PASS":
            raise SystemExit(1)

    finally:
        session.close()


if __name__ == "__main__":
    main()