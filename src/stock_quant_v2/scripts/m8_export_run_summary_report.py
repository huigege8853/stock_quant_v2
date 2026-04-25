from __future__ import annotations

from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.ops_domain.services.m8_report_export_service import M8ReportExportService
from stock_quant_v2.scripts._m8_cli_utils import env_int, env_path, print_json


def main() -> None:
    run_id = env_int("M8_RUN_ID")
    output_dir = env_path("M8_REPORT_OUTPUT_DIR", "artifacts/m8/run_summary")

    if run_id is None:
        raise RuntimeError("Missing env var: M8_RUN_ID")

    session = SessionLocal()
    try:
        result = M8ReportExportService(session).export_run_summary_report(
            output_dir=output_dir,
            run_id=run_id,
        )
        print_json(result)
    finally:
        session.close()


if __name__ == "__main__":
    main()