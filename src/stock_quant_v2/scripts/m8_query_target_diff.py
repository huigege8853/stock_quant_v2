from __future__ import annotations

from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.ops_domain.services.m8_query_service import M8QueryService
from stock_quant_v2.scripts._m8_cli_utils import env_int, print_json


def main() -> None:
    portfolio_id = env_int("M8_PORTFOLIO_ID", 1)
    source_target_run_id = env_int("M8_SOURCE_TARGET_RUN_ID")
    adjusted_target_run_id = env_int("M8_ADJUSTED_TARGET_RUN_ID")
    risk_run_id = env_int("M8_RISK_RUN_ID")
    limit = env_int("M8_LIMIT", 200)

    if portfolio_id is None:
        raise RuntimeError("Missing env var: M8_PORTFOLIO_ID")
    if source_target_run_id is None:
        raise RuntimeError("Missing env var: M8_SOURCE_TARGET_RUN_ID")
    if adjusted_target_run_id is None:
        raise RuntimeError("Missing env var: M8_ADJUSTED_TARGET_RUN_ID")
    if limit is None:
        limit = 200

    session = SessionLocal()
    try:
        result = M8QueryService(session).query_target_diff(
            portfolio_id=portfolio_id,
            source_target_run_id=source_target_run_id,
            adjusted_target_run_id=adjusted_target_run_id,
            risk_run_id=risk_run_id,
            limit=limit,
        )
        print_json(result)
    finally:
        session.close()


if __name__ == "__main__":
    main()