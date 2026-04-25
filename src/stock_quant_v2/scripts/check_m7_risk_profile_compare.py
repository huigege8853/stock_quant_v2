from __future__ import annotations

import json
import os
from decimal import Decimal

from sqlalchemy import text

from stock_quant_v2.db.session import SessionLocal


def _env_int(name: str, default: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        if default is None:
            raise RuntimeError(f"Missing env var: {name}")
        return default
    return int(raw)


def _env_runs(name: str) -> list[int]:
    raw = os.getenv(name)
    if not raw:
        raise RuntimeError(f"Missing env var: {name}")
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def _row_to_dict(row) -> dict:
    out = dict(row)
    for k, v in list(out.items()):
        if isinstance(v, Decimal):
            out[k] = str(v)
    return out


def main() -> None:
    source_target_run_id = _env_int("M7_RISK_SOURCE_TARGET_RUN_ID", 155)
    adjusted_run_ids = _env_runs("M7_RISK_COMPARE_ADJUSTED_RUN_IDS")
    portfolio_id = _env_int("M7_PORTFOLIO_ID", 1)

    session = SessionLocal()
    try:
        rows = []
        for run_id in adjusted_run_ids:
            summary = session.execute(
                text(
                    """
                    select
                        :run_id as adjusted_target_run_id,
                        count(*) as target_count,
                        coalesce(sum(target_quantity), 0) as target_quantity_total,
                        coalesce(sum(target_amount), 0) as target_amount_total,
                        count(*) filter (where status = 'REJECTED') as rejected_target_count,
                        count(*) filter (where status = 'RISK_ADJUSTED') as adjusted_target_count,
                        count(*) filter (where status = 'RISK_PASSED') as passed_target_count
                    from trading_paper_target_position
                    where run_id = :run_id
                      and portfolio_id = :portfolio_id
                    """
                ),
                {"run_id": run_id, "portfolio_id": portfolio_id},
            ).mappings().one()

            decisions = session.execute(
                text(
                    """
                    select
                        count(*) as decision_count,
                        count(*) filter (where decision_type = 'PASS') as pass_count,
                        count(*) filter (where decision_type = 'WARN') as warn_count,
                        count(*) filter (where decision_type = 'REJECT') as reject_count,
                        count(*) filter (where decision_type = 'ADJUST') as adjust_count
                    from risk_decision
                    where source_target_run_id = :source_target_run_id
                      and adjusted_target_run_id = :adjusted_target_run_id
                      and portfolio_id = :portfolio_id
                    """
                ),
                {
                    "source_target_run_id": source_target_run_id,
                    "adjusted_target_run_id": run_id,
                    "portfolio_id": portfolio_id,
                },
            ).mappings().one()

            rows.append({"target": _row_to_dict(summary), "decisions": _row_to_dict(decisions)})

        totals = [r["target"]["target_quantity_total"] for r in rows]
        reject_counts = [int(r["decisions"]["reject_count"]) for r in rows]
        adjust_counts = [int(r["decisions"]["adjust_count"]) for r in rows]

        result = {
            "source_target_run_id": source_target_run_id,
            "portfolio_id": portfolio_id,
            "adjusted_run_ids": adjusted_run_ids,
            "profiles": rows,
            "checks": {
                "has_multiple_profiles": len(adjusted_run_ids) >= 2,
                "all_have_targets": all(int(r["target"]["target_count"]) > 0 for r in rows),
                "all_have_decisions": all(int(r["decisions"]["decision_count"]) > 0 for r in rows),
                "different_target_quantity_totals": len(set(totals)) > 1,
                "has_reject_or_adjust_profile": any(x > 0 for x in reject_counts + adjust_counts),
            },
        }
        result["overall_status"] = "PASS" if all(result["checks"].values()) else "FAIL"

        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    finally:
        session.close()


if __name__ == "__main__":
    main()
