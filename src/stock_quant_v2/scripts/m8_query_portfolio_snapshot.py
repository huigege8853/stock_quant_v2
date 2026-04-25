from __future__ import annotations

from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.ops_domain.services.m8_query_service import M8QueryService
from stock_quant_v2.scripts._m8_cli_utils import env_date, env_int, print_json


def main() -> None:
    portfolio_id = env_int("M8_PORTFOLIO_ID", 1)
    snapshot_run_id = env_int("M8_SNAPSHOT_RUN_ID")
    snapshot_date = env_date("M8_SNAPSHOT_DATE")

    if portfolio_id is None:
        raise RuntimeError("Missing env var: M8_PORTFOLIO_ID")

    session = SessionLocal()
    try:
        result = M8QueryService(session).query_portfolio_snapshot(
            portfolio_id=portfolio_id,
            snapshot_run_id=snapshot_run_id,
            snapshot_date=snapshot_date,
        )
        print_json(result)
    finally:
        session.close()


if __name__ == "__main__":
    main()