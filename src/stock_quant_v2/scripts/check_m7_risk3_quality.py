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


def _dec(v):
    return str(v) if isinstance(v, Decimal) else v


def main() -> None:
    portfolio_id = _env_int("M7_PORTFOLIO_ID", 1)
    source_target_run_id = _env_int("M7_RISK3_SOURCE_TARGET_RUN_ID", 160)
    adjusted_target_run_id = _env_int("M7_RISK3_ADJUSTED_TARGET_RUN_ID")

    session = SessionLocal()
    try:
        target = session.execute(
            text(
                """
                select
                    count(*) as target_count,
                    coalesce(sum(target_quantity), 0) as target_quantity_total,
                    coalesce(sum(target_amount), 0) as target_amount_total,
                    count(*) filter (where status = 'REJECTED') as rejected_target_count,
                    count(*) filter (where status = 'RISK_ADJUSTED') as adjusted_target_count,
                    count(*) filter (where status = 'RISK3_PASSED') as passed_target_count
                from trading_paper_target_position
                where run_id = :adjusted_target_run_id
                  and portfolio_id = :portfolio_id
                """
            ),
            {"adjusted_target_run_id": adjusted_target_run_id, "portfolio_id": portfolio_id},
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
                "adjusted_target_run_id": adjusted_target_run_id,
                "portfolio_id": portfolio_id,
            },
        ).mappings().one()

        reasons = session.execute(
            text(
                """
                select decision_type, reason_code, count(*) as cnt
                from risk_decision
                where source_target_run_id = :source_target_run_id
                  and adjusted_target_run_id = :adjusted_target_run_id
                  and portfolio_id = :portfolio_id
                  and (
                    reason_code like 'R007%%'
                    or reason_code like 'R009%%'
                    or reason_code like 'R011%%'
                  )
                group by decision_type, reason_code
                order by decision_type, reason_code
                """
            ),
            {
                "source_target_run_id": source_target_run_id,
                "adjusted_target_run_id": adjusted_target_run_id,
                "portfolio_id": portfolio_id,
            },
        ).mappings().all()

        target_dict = {k: _dec(v) for k, v in dict(target).items()}
        decision_dict = {k: _dec(v) for k, v in dict(decisions).items()}
        reason_list = [{k: _dec(v) for k, v in dict(r).items()} for r in reasons]

        result = {
            "portfolio_id": portfolio_id,
            "source_target_run_id": source_target_run_id,
            "adjusted_target_run_id": adjusted_target_run_id,
            "target": target_dict,
            "decisions": decision_dict,
            "reason_summary": reason_list,
            "checks": {
                "adjusted_target_exists": int(target["target_count"] or 0) > 0,
                "decision_exists": int(decisions["decision_count"] or 0) > 0,
                "has_risk3_reason": len(reason_list) > 0,
                "has_warn_or_adjust_or_reject": (
                    int(decisions["warn_count"] or 0)
                    + int(decisions["adjust_count"] or 0)
                    + int(decisions["reject_count"] or 0)
                ) > 0,
            },
        }
        result["overall_status"] = "PASS" if all(result["checks"].values()) else "FAIL"
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    finally:
        session.close()


if __name__ == "__main__":
    main()
