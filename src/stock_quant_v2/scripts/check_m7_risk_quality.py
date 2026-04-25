from __future__ import annotations

import json
import os

from sqlalchemy import text

from stock_quant_v2.db.session import SessionLocal


def _env_int(name: str, default: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        if default is None:
            raise RuntimeError(f"Missing env var: {name}")
        return default
    return int(raw)


def main() -> None:
    source_target_run_id = _env_int("M7_RISK_SOURCE_TARGET_RUN_ID", 155)
    adjusted_target_run_id = _env_int("M7_RISK_ADJUSTED_TARGET_RUN_ID")
    portfolio_id = _env_int("M7_PORTFOLIO_ID", 1)

    session = SessionLocal()
    try:
        source = session.execute(
            text(
                """
                select
                    count(*) as target_count,
                    coalesce(sum(target_quantity), 0) as target_quantity_total,
                    coalesce(sum(target_amount), 0) as target_amount_total
                from trading_paper_target_position
                where run_id = :run_id
                  and portfolio_id = :portfolio_id
                """
            ),
            {"run_id": source_target_run_id, "portfolio_id": portfolio_id},
        ).mappings().one()

        adjusted = session.execute(
            text(
                """
                select
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
            {"run_id": adjusted_target_run_id, "portfolio_id": portfolio_id},
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

        reason_rows = session.execute(
            text(
                """
                select reason_code, decision_type, count(*) as cnt
                from risk_decision
                where source_target_run_id = :source_target_run_id
                  and adjusted_target_run_id = :adjusted_target_run_id
                  and portfolio_id = :portfolio_id
                group by reason_code, decision_type
                order by decision_type, reason_code
                """
            ),
            {
                "source_target_run_id": source_target_run_id,
                "adjusted_target_run_id": adjusted_target_run_id,
                "portfolio_id": portfolio_id,
            },
        ).mappings().all()

        decision_count = int(decisions["decision_count"] or 0)
        source_count = int(source["target_count"] or 0)
        adjusted_count = int(adjusted["target_count"] or 0)

        result = {
            "source_target_run_id": source_target_run_id,
            "adjusted_target_run_id": adjusted_target_run_id,
            "portfolio_id": portfolio_id,
            "source": dict(source),
            "adjusted": dict(adjusted),
            "decisions": dict(decisions),
            "reason_summary": [dict(r) for r in reason_rows],
            "checks": {
                "source_target_exists": source_count > 0,
                "adjusted_target_exists": adjusted_count > 0,
                "decision_exists": decision_count > 0,
                "same_target_row_count": source_count == adjusted_count,
                "has_reject_or_adjust_or_warn": (
                    int(decisions["reject_count"] or 0)
                    + int(decisions["adjust_count"] or 0)
                    + int(decisions["warn_count"] or 0)
                ) > 0,
            },
        }
        result["overall_status"] = "PASS" if all(result["checks"].values()) else "FAIL"

        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    finally:
        session.close()


if __name__ == "__main__":
    main()
