from __future__ import annotations

from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.ops_domain.services.m8_daily_ops_service import M8DailyOpsService
from stock_quant_v2.scripts._m8_cli_utils import env_int, env_str, print_json


def main() -> None:
    portfolio_id = env_int("M8_PORTFOLIO_ID", 1)
    profile_code = env_str("M8_RISK_PROFILE_CODE")

    if portfolio_id is None:
        raise RuntimeError("Missing env var: M8_PORTFOLIO_ID")

    session = SessionLocal()
    try:
        result = M8DailyOpsService(session).daily_ops_plan(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
        )
        print_json(result)
    finally:
        session.close()


if __name__ == "__main__":
    main()