from __future__ import annotations

import json

from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.risk_domain.services.risk3_profile_seed_service import Risk3ProfileSeedService


def main() -> None:
    session = SessionLocal()
    try:
        result = Risk3ProfileSeedService(session).seed()
        session.commit()
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
