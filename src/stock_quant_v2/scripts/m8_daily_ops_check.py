from __future__ import annotations

from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.ops_domain.services.m8_daily_ops_service import M8DailyOpsService
from stock_quant_v2.scripts._m8_cli_utils import env_int, env_path, env_str, print_json


def _env_bool(name: str, default: bool = False) -> bool:
    import os

    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y"}


def main() -> None:
    portfolio_id = env_int("M8_PORTFOLIO_ID", 1)
    profile_code = env_str("M8_RISK_PROFILE_CODE")
    export_report = _env_bool("M8_EXPORT_DAILY_REPORT", False)
    output_dir = env_path("M8_REPORT_OUTPUT_DIR", "artifacts/m8/daily_ops")

    if portfolio_id is None:
        raise RuntimeError("Missing env var: M8_PORTFOLIO_ID")

    session = SessionLocal()
    try:
        result = M8DailyOpsService(session).daily_ops_check(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
            export_report=export_report,
            output_dir=output_dir,
        )
        print_json(result)

        if result["overall_status"] == "FAIL":
            raise SystemExit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()