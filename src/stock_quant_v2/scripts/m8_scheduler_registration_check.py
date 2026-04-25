from __future__ import annotations

from pathlib import Path

from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.ops_domain.services.m8_scheduler_registration_service import (
    M8SchedulerRegistrationService,
)
from stock_quant_v2.scripts._m8_cli_utils import env_int, env_path, env_str, print_json


def main() -> None:
    portfolio_id = env_int("M8_PORTFOLIO_ID", 1)
    profile_code = env_str("M8_RISK_PROFILE_CODE")
    project_root = env_path("M8_PROJECT_ROOT", str(Path.cwd()))
    scheduler_dir = env_path("M8_SCHEDULER_TEMPLATE_OUTPUT_DIR", "artifacts/m8/scheduler")
    task_name = env_str("M8_SCHEDULER_TASK_NAME", "stock_quant_v2_m8_daily_ops")

    if portfolio_id is None:
        raise RuntimeError("Missing env var: M8_PORTFOLIO_ID")
    if task_name is None:
        task_name = "stock_quant_v2_m8_daily_ops"

    session = SessionLocal()
    try:
        result = M8SchedulerRegistrationService(session).scheduler_registration_check(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
            project_root=project_root,
            scheduler_dir=scheduler_dir,
            task_name=task_name,
        )
        print_json(result)

        if result["overall_status"] == "FAIL":
            raise SystemExit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()