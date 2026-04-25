from __future__ import annotations

from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.ops_domain.services.m8_report_export_service import M8ReportExportService
from stock_quant_v2.scripts._m8_cli_utils import env_int, env_path, print_json


def main() -> None:
    portfolio_id = env_int("M8_PORTFOLIO_ID", 1)
    target_run_id = env_int("M8_TARGET_RUN_ID")
    order_run_id = env_int("M8_ORDER_RUN_ID")
    fill_run_id = env_int("M8_FILL_RUN_ID")
    position_run_id = env_int("M8_POSITION_RUN_ID")
    snapshot_run_id = env_int("M8_SNAPSHOT_RUN_ID")
    detail_limit = env_int("M8_DETAIL_LIMIT", 5000)
    output_dir = env_path("M8_REPORT_OUTPUT_DIR", "artifacts/m8/paper_chain")

    if portfolio_id is None:
        raise RuntimeError("Missing env var: M8_PORTFOLIO_ID")
    if target_run_id is None:
        raise RuntimeError("Missing env var: M8_TARGET_RUN_ID")
    if order_run_id is None:
        raise RuntimeError("Missing env var: M8_ORDER_RUN_ID")
    if fill_run_id is None:
        raise RuntimeError("Missing env var: M8_FILL_RUN_ID")
    if position_run_id is None:
        raise RuntimeError("Missing env var: M8_POSITION_RUN_ID")
    if snapshot_run_id is None:
        raise RuntimeError("Missing env var: M8_SNAPSHOT_RUN_ID")
    if detail_limit is None:
        detail_limit = 5000

    session = SessionLocal()
    try:
        result = M8ReportExportService(session).export_paper_chain_report(
            output_dir=output_dir,
            portfolio_id=portfolio_id,
            target_run_id=target_run_id,
            order_run_id=order_run_id,
            fill_run_id=fill_run_id,
            position_run_id=position_run_id,
            snapshot_run_id=snapshot_run_id,
            detail_limit=detail_limit,
        )
        print_json(result)
    finally:
        session.close()


if __name__ == "__main__":
    main()