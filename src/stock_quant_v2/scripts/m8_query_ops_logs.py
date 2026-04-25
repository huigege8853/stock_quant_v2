from __future__ import annotations

from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.ops_domain.services.m8_alert_log_audit_service import M8AlertLogAuditService
from stock_quant_v2.scripts._m8_cli_utils import env_bool, env_int, env_str, print_json


def main() -> None:
    status = env_str("M8_LOG_STATUS")
    run_type = env_str("M8_LOG_RUN_TYPE")
    limit = env_int("M8_LIMIT", 100)
    include_error_only = env_bool("M8_LOG_ERROR_ONLY", False)

    if limit is None:
        limit = 100

    session = SessionLocal()
    try:
        result = M8AlertLogAuditService(session).query_ops_logs(
            status=status,
            run_type=run_type,
            limit=limit,
            include_error_only=include_error_only,
        )
        print_json(result)
    finally:
        session.close()


if __name__ == "__main__":
    main()