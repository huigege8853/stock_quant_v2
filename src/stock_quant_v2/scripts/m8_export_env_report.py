from __future__ import annotations

from pathlib import Path

from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.ops_domain.services.m8_env_startup_service import M8EnvStartupService
from stock_quant_v2.scripts._m8_cli_utils import env_int, env_path, env_str, print_json


def main() -> None:
    portfolio_id = env_int("M8_PORTFOLIO_ID", 1)
    profile_code = env_str("M8_RISK_PROFILE_CODE")
    project_root = env_path("M8_PROJECT_ROOT", str(Path.cwd()))
    output_dir = env_path("M8_ENV_OUTPUT_DIR", "artifacts/m8/env")

    if portfolio_id is None:
        raise RuntimeError("Missing env var: M8_PORTFOLIO_ID")

    session = SessionLocal()
    try:
        result = M8EnvStartupService(session).export_env_report(
            output_dir=output_dir,
            portfolio_id=portfolio_id,
            profile_code=profile_code,
            project_root=project_root,
        )
        print_json(result)

        if result["overall_status"] == "FAIL":
            raise SystemExit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()