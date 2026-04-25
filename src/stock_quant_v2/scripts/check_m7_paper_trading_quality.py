from __future__ import annotations

import json
import os
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from stock_quant_v2.db.session import SessionLocal


POSITION_TABLE = "trading_paper_position"


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


def _summary(session, *, run_id: int, portfolio_id: int) -> dict[str, Any]:
    row = session.execute(
        text(
            f"""
            select
                count(*) as position_count,
                coalesce(sum(quantity), 0) as quantity_total,
                coalesce(sum(available_quantity), 0) as available_quantity_total,
                sum(case when quantity < 0 then 1 else 0 end) as negative_quantity_count,
                sum(case when available_quantity < 0 then 1 else 0 end) as negative_available_quantity_count,
                sum(case when available_quantity > quantity then 1 else 0 end) as available_gt_quantity_count
            from {POSITION_TABLE}
            where run_id = :run_id
              and portfolio_id = :portfolio_id
            """
        ),
        {"run_id": run_id, "portfolio_id": portfolio_id},
    ).mappings().one()

    return {
        "position_count": int(row["position_count"] or 0),
        "quantity_total": _to_decimal(row["quantity_total"]),
        "available_quantity_total": _to_decimal(row["available_quantity_total"]),
        "negative_quantity_count": int(row["negative_quantity_count"] or 0),
        "negative_available_quantity_count": int(
            row["negative_available_quantity_count"] or 0
        ),
        "available_gt_quantity_count": int(row["available_gt_quantity_count"] or 0),
    }


def main() -> None:
    source_position_run_id = _env_int("M7_SOURCE_POSITION_RUN_ID", 114)
    target_position_run_id = _env_int("M7_TARGET_POSITION_RUN_ID")
    portfolio_id = _env_int("M7_PORTFOLIO_ID", 1)

    session = SessionLocal()
    try:
        source = _summary(
            session,
            run_id=source_position_run_id,
            portfolio_id=portfolio_id,
        )
        target = _summary(
            session,
            run_id=target_position_run_id,
            portfolio_id=portfolio_id,
        )

        checks = {
            "source_position_exists": source["position_count"] > 0,
            "target_position_exists": target["position_count"] > 0,
            "position_count_check": source["position_count"] == target["position_count"],
            "quantity_total_check": source["quantity_total"] == target["quantity_total"],
            "t_plus_1_available_quantity_check": (
                target["available_quantity_total"] == target["quantity_total"]
            ),
            "negative_quantity_check": target["negative_quantity_count"] == 0,
            "negative_available_quantity_check": (
                target["negative_available_quantity_count"] == 0
            ),
            "available_quantity_le_quantity_check": (
                target["available_gt_quantity_count"] == 0
            ),
        }

        overall_status = "PASS" if all(checks.values()) else "FAIL"

        result = {
            "module": "M7",
            "stage": "M7.1",
            "source_position_run_id": source_position_run_id,
            "target_position_run_id": target_position_run_id,
            "portfolio_id": portfolio_id,
            "overall_status": overall_status,
            "checks": checks,
            "source": {
                **source,
                "quantity_total": str(source["quantity_total"]),
                "available_quantity_total": str(source["available_quantity_total"]),
            },
            "target": {
                **target,
                "quantity_total": str(target["quantity_total"]),
                "available_quantity_total": str(target["available_quantity_total"]),
            },
        }

        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

        if overall_status != "PASS":
            raise SystemExit(1)

    finally:
        session.close()


if __name__ == "__main__":
    main()