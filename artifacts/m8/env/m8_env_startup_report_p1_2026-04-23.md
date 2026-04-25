# M8.11 Environment / Startup Report

- portfolio_id: `1`
- profile_code: `None`
- exported_at: `2026-04-23T15:46:14.791325`

## Status

- env_status: `FAIL`
- startup_status: `FAIL`
- scheduler_exit_code: `0`
- highest_alert_level: `WARN`

## Checks

- env_not_fail: `False`
- ops_kpi_not_fail: `True`
- scheduler_health_pass: `True`
- scheduler_exit_code_zero: `True`
- alert_no_critical: `True`
- api_import_pass: `False`
- api_app_pass: `False`

## Warnings

- ENV_VARS_WARN: explicit database env var is missing, but SessionLocal database connection passed; likely loaded from project settings or .env
- ENV_VARS_WARN: optional env var not set
- ENV_VARS_WARN: optional env var not set
- ENV_VARS_WARN: optional env var not set
- ALERT_WARN: alert_check returned WARN but no CRITICAL alert.

## Failures

- dependencies_pass: environment check failed
- imports_pass: environment check failed
- env_not_fail: startup check failed
- api_import_pass: startup check failed
- api_app_pass: startup check failed
