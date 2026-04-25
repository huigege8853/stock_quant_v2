from __future__ import annotations

from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.ops_domain.services.m8_scheduler_service import M8SchedulerService
from stock_quant_v2.scripts._m8_cli_utils import env_int, env_path, env_str, print_json


def main() -> None:
    portfolio_id = env_int("M8_PORTFOLIO_ID", 1)
    profile_code = env_str("M8_RISK_PROFILE_CODE")
    output_dir = env_path("M8_REPORT_OUTPUT_DIR", "artifacts/m8/daily_ops")

    if portfolio_id is None:
        raise RuntimeError("Missing env var: M8_PORTFOLIO_ID")

    session = SessionLocal()
    try:
        result = M8SchedulerService(session).scheduler_health_check(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
            output_dir=output_dir,
        )
        print_json(result)

        if result["scheduler_exit_code"] != 0:
            raise SystemExit(result["scheduler_exit_code"])
    finally:
        session.close()


if __name__ == "__main__":
    main()