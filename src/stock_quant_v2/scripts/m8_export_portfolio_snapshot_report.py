from __future__ import annotations

from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.ops_domain.services.m8_report_export_service import M8ReportExportService
from stock_quant_v2.scripts._m8_cli_utils import env_date, env_int, env_path, print_json


def main() -> None:
    portfolio_id = env_int("M8_PORTFOLIO_ID", 1)
    snapshot_run_id = env_int("M8_SNAPSHOT_RUN_ID")
    snapshot_date = env_date("M8_SNAPSHOT_DATE")
    output_dir = env_path("M8_REPORT_OUTPUT_DIR", "artifacts/m8/portfolio_snapshot")

    if portfolio_id is None:
        raise RuntimeError("Missing env var: M8_PORTFOLIO_ID")

    session = SessionLocal()
    try:
        result = M8ReportExportService(session).export_portfolio_snapshot_report(
            output_dir=output_dir,
            portfolio_id=portfolio_id,
            snapshot_run_id=snapshot_run_id,
            snapshot_date=snapshot_date,
        )
        print_json(result)
    finally:
        session.close()


if __name__ == "__main__":
    main()