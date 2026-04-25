from __future__ import annotations

from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.ops_domain.services.m8_query_service import M8QueryService
from stock_quant_v2.scripts._m8_cli_utils import env_int, print_json


def main() -> None:
    run_id = env_int("M8_RUN_ID")
    if run_id is None:
        raise RuntimeError("Missing env var: M8_RUN_ID")

    session = SessionLocal()
    try:
        result = M8QueryService(session).query_run(run_id=run_id)
        print_json(result)
    finally:
        session.close()


if __name__ == "__main__":
    main()