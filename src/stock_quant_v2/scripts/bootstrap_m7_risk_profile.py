from __future__ import annotations

import json
import os

from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.risk_domain.services.risk_profile_seed_service import (
    DEFAULT_PROFILE_CODE,
    RiskProfileSeedService,
)


def main() -> None:
    profile_code = os.getenv("M7_RISK_PROFILE_CODE", DEFAULT_PROFILE_CODE)
    profile_name = os.getenv(
        "M7_RISK_PROFILE_NAME",
        "CN A Paper Trading Default Risk Profile V1",
    )

    session = SessionLocal()
    try:
        result = RiskProfileSeedService(session).seed_default_profile(
            profile_code=profile_code,
            profile_name=profile_name,
        )
        session.commit()
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
