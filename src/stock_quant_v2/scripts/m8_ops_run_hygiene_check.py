from __future__ import annotations

from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.ops_domain.services.m8_ops_hygiene_service import M8OpsHygieneService
from stock_quant_v2.scripts._m8_cli_utils import env_bool, env_int, env_str, print_json


def main() -> None:
    portfolio_id = env_int("M8_PORTFOLIO_ID", 1)
    profile_code = env_str("M8_RISK_PROFILE_CODE")
    stale_after_hours = env_int("M8_STALE_AFTER_HOURS", 12)
    limit = env_int("M8_LIMIT", 200)
    include_protected = env_bool("M8_INCLUDE_PROTECTED", False)

    if portfolio_id is None:
        raise RuntimeError("Missing env var: M8_PORTFOLIO_ID")
    if stale_after_hours is None:
        stale_after_hours = 12
    if limit is None:
        limit = 200

    session = SessionLocal()
    try:
        result = M8OpsHygieneService(session).ops_run_hygiene_check(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
            stale_after_hours=stale_after_hours,
            limit=limit,
            include_protected=include_protected,
        )
        print_json(result)

        if result["overall_status"] == "FAIL":
            raise SystemExit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()