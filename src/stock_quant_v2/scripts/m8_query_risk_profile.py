from __future__ import annotations

from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.ops_domain.services.m8_query_service import M8QueryService
from stock_quant_v2.scripts._m8_cli_utils import env_str, print_json


def main() -> None:
    profile_code = env_str("M8_RISK_PROFILE_CODE")

    session = SessionLocal()
    try:
        result = M8QueryService(session).query_risk_profile(
            profile_code=profile_code,
        )
        print_json(result)
    finally:
        session.close()


if __name__ == "__main__":
    main()