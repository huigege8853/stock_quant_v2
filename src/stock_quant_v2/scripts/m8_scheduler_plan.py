from __future__ import annotations

from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.ops_domain.services.m8_scheduler_service import M8SchedulerService
from stock_quant_v2.scripts._m8_cli_utils import env_int, env_path, env_str, print_json


def main() -> None:
    portfolio_id = env_int("M8_PORTFOLIO_ID", 1)
    profile_code = env_str("M8_RISK_PROFILE_CODE")
    output_dir = env_path("M8_REPORT_OUTPUT_DIR", "artifacts/m8/daily_ops")
    task_name = env_str("M8_SCHEDULER_TASK_NAME", "stock_quant_v2_m8_daily_ops")
    schedule_time = env_str("M8_SCHEDULER_TIME", "18:30")

    if portfolio_id is None:
        raise RuntimeError("Missing env var: M8_PORTFOLIO_ID")
    if task_name is None:
        task_name = "stock_quant_v2_m8_daily_ops"
    if schedule_time is None:
        schedule_time = "18:30"

    session = SessionLocal()
    try:
        result = M8SchedulerService(session).scheduler_plan(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
            output_dir=output_dir,
            task_name=task_name,
            schedule_time=schedule_time,
        )
        print_json(result)
    finally:
        session.close()


if __name__ == "__main__":
    main()