from __future__ import annotations

from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.ops_domain.services.m8_query_service import M8QueryService
from stock_quant_v2.scripts._m8_cli_utils import env_int, print_json


def main() -> None:
    portfolio_id = env_int("M8_PORTFOLIO_ID", 1)
    target_run_id = env_int("M8_TARGET_RUN_ID")
    order_run_id = env_int("M8_ORDER_RUN_ID")
    fill_run_id = env_int("M8_FILL_RUN_ID")
    position_run_id = env_int("M8_POSITION_RUN_ID")
    snapshot_run_id = env_int("M8_SNAPSHOT_RUN_ID")

    if portfolio_id is None:
        raise RuntimeError("Missing env var: M8_PORTFOLIO_ID")
    if target_run_id is None:
        raise RuntimeError("Missing env var: M8_TARGET_RUN_ID")

    session = SessionLocal()
    try:
        result = M8QueryService(session).query_paper_chain(
            portfolio_id=portfolio_id,
            target_run_id=target_run_id,
            order_run_id=order_run_id,
            fill_run_id=fill_run_id,
            position_run_id=position_run_id,
            snapshot_run_id=snapshot_run_id,
        )
        print_json(result)
    finally:
        session.close()


if __name__ == "__main__":
    main()