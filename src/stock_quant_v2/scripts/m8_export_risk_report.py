from __future__ import annotations

from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.ops_domain.services.m8_query_service import M8QueryService
from stock_quant_v2.scripts._m8_cli_utils import env_int, env_path, print_json


def main() -> None:
    portfolio_id = env_int("M8_PORTFOLIO_ID", 1)
    source_target_run_id = env_int("M8_SOURCE_TARGET_RUN_ID")
    adjusted_target_run_id = env_int("M8_ADJUSTED_TARGET_RUN_ID")
    risk_run_id = env_int("M8_RISK_RUN_ID")
    output_dir = env_path("M8_REPORT_OUTPUT_DIR", "artifacts/m8/risk")

    if portfolio_id is None:
        raise RuntimeError("Missing env var: M8_PORTFOLIO_ID")
    if source_target_run_id is None:
        raise RuntimeError("Missing env var: M8_SOURCE_TARGET_RUN_ID")
    if adjusted_target_run_id is None:
        raise RuntimeError("Missing env var: M8_ADJUSTED_TARGET_RUN_ID")

    session = SessionLocal()
    try:
        result = M8QueryService(session).export_risk_report(
            output_dir=output_dir,
            portfolio_id=portfolio_id,
            source_target_run_id=source_target_run_id,
            adjusted_target_run_id=adjusted_target_run_id,
            risk_run_id=risk_run_id,
        )
        print_json(result)
    finally:
        session.close()


if __name__ == "__main__":
    main()