from __future__ import annotations

import csv
import importlib
import json
import os
import platform
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from stock_quant_v2.ops_domain.services.m8_alert_log_audit_service import M8AlertLogAuditService
from stock_quant_v2.ops_domain.services.m8_human_review_service import M8HumanReviewService
from stock_quant_v2.ops_domain.services.m8_query_service import M8QueryService
from stock_quant_v2.ops_domain.services.m8_scheduler_service import M8SchedulerService


class M8EnvStartupService:
    def __init__(self, session: Session):
        self.session = session
        self.query_service = M8QueryService(session)
        self.human_review_service = M8HumanReviewService(session)
        self.scheduler_service = M8SchedulerService(session)
        self.alert_service = M8AlertLogAuditService(session)

    def env_check(
        self,
        *,
        portfolio_id: int,
        profile_code: str | None = None,
        project_root: Path | None = None,
    ) -> dict[str, Any]:
        project_root = project_root or Path.cwd()

        env_vars = self._check_env_vars()
        dependency_checks = self._check_dependencies()
        path_checks = self._check_paths(project_root)
        artifact_checks = self._check_artifacts(project_root)
        import_checks = self._check_imports()
        db_check = self._check_db_connection()

        if db_check.get("status") == "PASS":
            self._downgrade_missing_db_env_if_session_works(env_vars)

        latest_runs_check = self._check_latest_runs(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
        )

        checks = {
            "env_vars_pass": self._all_status_pass_or_warn(env_vars),
            "dependencies_pass": self._all_status_pass(dependency_checks),
            "paths_pass": self._all_status_pass(path_checks),
            "artifacts_pass": self._all_status_pass_or_warn(artifact_checks),
            "imports_pass": self._all_status_pass(import_checks),
            "db_connection_pass": db_check.get("status") == "PASS",
            "latest_runs_pass": latest_runs_check.get("status") == "PASS",
        }

        failures = [
            {"check_code": key, "message": "environment check failed"}
            for key, ok in checks.items()
            if not ok
        ]

        warnings: list[dict[str, Any]] = []
        for section_name, section_rows in [
            ("env_vars", env_vars),
            ("artifacts", artifact_checks),
        ]:
            for item in section_rows:
                if item.get("status") == "WARN":
                    warnings.append(
                        {
                            "warning_code": f"{section_name.upper()}_WARN",
                            "message": item.get("message"),
                            "item": item,
                        }
                    )

        return {
            "module": "M8.11",
            "query": "env_check",
            "portfolio_id": portfolio_id,
            "profile_code": profile_code,
            "project_root": str(project_root),
            "checked_at": datetime.utcnow().isoformat(),
            "runtime": {
                "python": sys.version,
                "platform": platform.platform(),
                "executable": sys.executable,
                "cwd": str(Path.cwd()),
            },
            "env_vars": env_vars,
            "dependencies": dependency_checks,
            "paths": path_checks,
            "artifacts": artifact_checks,
            "imports": import_checks,
            "db_connection": db_check,
            "latest_runs": latest_runs_check,
            "checks": checks,
            "warnings": warnings,
            "failures": failures,
            "overall_status": "FAIL" if failures else ("WARN" if warnings else "PASS"),
        }

    def startup_check(
        self,
        *,
        portfolio_id: int,
        profile_code: str | None = None,
        project_root: Path | None = None,
    ) -> dict[str, Any]:
        project_root = project_root or Path.cwd()

        env = self.env_check(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
            project_root=project_root,
        )

        ops_kpi = self.human_review_service.query_ops_kpi(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
        )

        scheduler_health = self.scheduler_service.scheduler_health_check(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
            output_dir=Path("artifacts/m8/daily_ops"),
        )

        alert_check = self.alert_service.ops_alert_check(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
        )

        api_import = self._import_check("stock_quant_v2.api.app")
        api_app_check = self._check_api_app_import()

        checks = {
            "env_not_fail": env.get("overall_status") in {"PASS", "WARN"},
            "ops_kpi_not_fail": ops_kpi.get("overall_status") in {"PASS", "WARN"},
            "scheduler_health_pass": scheduler_health.get("overall_status") == "PASS",
            "scheduler_exit_code_zero": scheduler_health.get("scheduler_exit_code") == 0,
            "alert_no_critical": alert_check.get("highest_level") != "CRITICAL",
            "api_import_pass": api_import.get("status") == "PASS",
            "api_app_pass": api_app_check.get("status") == "PASS",
        }

        failures = [
            {"check_code": key, "message": "startup check failed"}
            for key, ok in checks.items()
            if not ok
        ]

        warnings: list[dict[str, Any]] = []

        if env.get("overall_status") == "WARN":
            warnings.append(
                {
                    "warning_code": "ENV_WARN",
                    "message": "env_check returned WARN; inspect env warnings.",
                }
            )

        if ops_kpi.get("overall_status") == "WARN":
            warnings.append(
                {
                    "warning_code": "OPS_KPI_WARN",
                    "message": "ops_kpi returned WARN; strict profile risk reject / target diff may be expected.",
                }
            )

        if alert_check.get("overall_status") == "WARN":
            warnings.append(
                {
                    "warning_code": "ALERT_WARN",
                    "message": "alert_check returned WARN but no CRITICAL alert.",
                    "highest_level": alert_check.get("highest_level"),
                    "alert_counts": alert_check.get("alert_counts"),
                }
            )

        return {
            "module": "M8.11",
            "query": "startup_check",
            "portfolio_id": portfolio_id,
            "profile_code": profile_code,
            "project_root": str(project_root),
            "checked_at": datetime.utcnow().isoformat(),
            "env_status": env.get("overall_status"),
            "ops_kpi_status": ops_kpi.get("overall_status"),
            "scheduler_health_status": scheduler_health.get("overall_status"),
            "scheduler_exit_code": scheduler_health.get("scheduler_exit_code"),
            "alert_status": alert_check.get("overall_status"),
            "highest_alert_level": alert_check.get("highest_level"),
            "api_import": api_import,
            "api_app": api_app_check,
            "checks": checks,
            "warnings": warnings,
            "failures": failures,
            "overall_status": "FAIL" if failures else ("WARN" if warnings else "PASS"),
        }

    def export_env_report(
        self,
        *,
        output_dir: Path,
        portfolio_id: int,
        profile_code: str | None = None,
        project_root: Path | None = None,
    ) -> dict[str, Any]:
        output_dir.mkdir(parents=True, exist_ok=True)

        env = self.env_check(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
            project_root=project_root,
        )
        startup = self.startup_check(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
            project_root=project_root,
        )

        snapshot_date = self._resolve_snapshot_date(portfolio_id=portfolio_id, profile_code=profile_code)
        stem = f"m8_env_startup_report_p{portfolio_id}_{snapshot_date}"

        payload = {
            "module": "M8.11",
            "query": "export_env_report",
            "portfolio_id": portfolio_id,
            "profile_code": profile_code,
            "exported_at": datetime.utcnow().isoformat(),
            "env_check": env,
            "startup_check": startup,
        }

        json_path = output_dir / f"{stem}.json"
        md_path = output_dir / f"{stem}.md"
        env_csv_path = output_dir / f"{stem}_env_vars.csv"
        dependency_csv_path = output_dir / f"{stem}_dependencies.csv"
        path_csv_path = output_dir / f"{stem}_paths.csv"
        artifact_csv_path = output_dir / f"{stem}_artifacts.csv"

        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=self._json_default),
            encoding="utf-8",
        )
        md_path.write_text(
            self._render_env_report_md(payload),
            encoding="utf-8",
        )

        self._write_csv(env_csv_path, env.get("env_vars") or [])
        self._write_csv(dependency_csv_path, env.get("dependencies") or [])
        self._write_csv(path_csv_path, env.get("paths") or [])
        self._write_csv(artifact_csv_path, env.get("artifacts") or [])

        return {
            "module": "M8.11",
            "query": "export_env_report",
            "portfolio_id": portfolio_id,
            "profile_code": profile_code,
            "files": {
                "json": str(json_path),
                "markdown": str(md_path),
                "env_vars_csv": str(env_csv_path),
                "dependencies_csv": str(dependency_csv_path),
                "paths_csv": str(path_csv_path),
                "artifacts_csv": str(artifact_csv_path),
            },
            "env_status": env.get("overall_status"),
            "startup_status": startup.get("overall_status"),
            "overall_status": "PASS"
            if env.get("overall_status") in {"PASS", "WARN"}
            and startup.get("overall_status") in {"PASS", "WARN"}
            else "FAIL",
        }

    def _check_env_vars(self) -> list[dict[str, Any]]:
        required_or_alias = [
            {
                "name": "V2_SQLALCHEMY_URL",
                "aliases": ["SQLALCHEMY_URL", "DATABASE_URL"],
                "required": True,
                "purpose": "database connection",
            },
        ]

        optional = [
            {
                "name": "M8_PORTFOLIO_ID",
                "required": False,
                "purpose": "default M8 portfolio id",
            },
            {
                "name": "M8_RISK_PROFILE_CODE",
                "required": False,
                "purpose": "default M8 risk profile code",
            },
            {
                "name": "M8_REPORT_OUTPUT_DIR",
                "required": False,
                "purpose": "daily ops report output dir",
            },
            {
                "name": "M8_EXCEL_OUTPUT_DIR",
                "required": False,
                "purpose": "Excel output dir",
            },
        ]

        rows: list[dict[str, Any]] = []

        for item in required_or_alias:
            name = item["name"]
            aliases = item.get("aliases") or []
            value = os.getenv(name)
            matched_alias = None
            if not value:
                for alias in aliases:
                    alias_value = os.getenv(alias)
                    if alias_value:
                        value = alias_value
                        matched_alias = alias
                        break

            rows.append(
                {
                    "name": name,
                    "required": item["required"],
                    "purpose": item["purpose"],
                    "present": bool(value),
                    "alias_used": matched_alias,
                    "masked_value": self._mask_env_value(value),
                    "status": "PASS" if value else "FAIL",
                    "message": "available" if value else f"missing required env var or aliases: {name}, {aliases}",
                }
            )

        for item in optional:
            value = os.getenv(item["name"])
            rows.append(
                {
                    "name": item["name"],
                    "required": item["required"],
                    "purpose": item["purpose"],
                    "present": bool(value),
                    "alias_used": None,
                    "masked_value": self._mask_env_value(value),
                    "status": "PASS" if value else "WARN",
                    "message": "available" if value else "optional env var not set",
                }
            )

        return rows

    @staticmethod
    def _downgrade_missing_db_env_if_session_works(rows: list[dict[str, Any]]) -> None:
        for row in rows:
            if row.get("name") != "V2_SQLALCHEMY_URL":
                continue

            if row.get("status") == "FAIL":
                row["status"] = "WARN"
                row["message"] = (
                    "explicit database env var is missing, but SessionLocal database "
                    "connection passed; likely loaded from project settings or .env"
                )

    def _check_dependencies(self) -> list[dict[str, Any]]:
        dependencies = [
            ("sqlalchemy", "database ORM"),
            ("psycopg", "PostgreSQL driver"),
            ("fastapi", "API framework"),
            ("uvicorn", "ASGI server"),
            ("openpyxl", "Excel export"),
            ("pydantic_settings", "settings support"),
        ]

        rows = []
        for module_name, purpose in dependencies:
            item = self._import_check(module_name)
            rows.append(
                {
                    "module": module_name,
                    "purpose": purpose,
                    "status": item["status"],
                    "message": item["message"],
                }
            )
        return rows

    def _check_paths(self, project_root: Path) -> list[dict[str, Any]]:
        paths = [
            ("project_root", project_root, True),
            ("src", project_root / "src", True),
            ("artifacts", project_root / "artifacts", False),
            ("artifacts_m8", project_root / "artifacts" / "m8", False),
            ("docs_runbooks", project_root / "docs" / "runbooks", False),
            ("docs_modules_m8", project_root / "docs" / "modules" / "m8", False),
        ]

        rows = []
        for name, path, required in paths:
            exists = path.exists()
            writable = self._is_writable_dir(path)
            status = "PASS" if exists and (writable or not path.is_dir()) else ("FAIL" if required else "WARN")
            rows.append(
                {
                    "name": name,
                    "path": str(path),
                    "required": required,
                    "exists": exists,
                    "writable": writable,
                    "status": status,
                    "message": "ok" if status == "PASS" else "path missing or not writable",
                }
            )
        return rows

    def _check_artifacts(self, project_root: Path) -> list[dict[str, Any]]:
        files = [
            "artifacts/m8/api/m8_openapi.json",
            "artifacts/m8/api/m8_api_endpoints.md",
            "artifacts/m8/excel/m8_human_review_pack_p1_2026-04-23.xlsx",
            "artifacts/m8/excel/m8_daily_ops_p1_2026-04-23.xlsx",
            "artifacts/m8/excel/m8_ops_summary_p1_2026-04-23.xlsx",
            "artifacts/m8/alert/m8_alert_report_p1_2026-04-23.json",
            "artifacts/m8/alert/m8_alert_report_p1_2026-04-23.md",
            "artifacts/m8/alert/m8_alert_report_p1_2026-04-23_alerts.csv",
            "artifacts/m8/audit/m8_audit_snapshot_p1_2026-04-23.json",
            "artifacts/m8/audit/m8_audit_snapshot_p1_2026-04-23.md",
            "artifacts/m8/audit/m8_audit_snapshot_p1_2026-04-23_run_status.csv",
            "artifacts/m8/audit/m8_audit_snapshot_p1_2026-04-23_run_type_status.csv",
            "artifacts/m8/audit/m8_audit_snapshot_p1_2026-04-23_error_logs.csv",
        ]

        rows = []
        for rel in files:
            path = project_root / rel
            exists = path.exists()
            rows.append(
                {
                    "artifact": rel,
                    "path": str(path),
                    "exists": exists,
                    "status": "PASS" if exists else "WARN",
                    "message": "available" if exists else "artifact missing; regenerate if needed",
                }
            )
        return rows

    def _check_imports(self) -> list[dict[str, Any]]:
        modules = [
            "stock_quant_v2.api.app",
            "stock_quant_v2.ops_domain.services.m8_query_service",
            "stock_quant_v2.ops_domain.services.m8_report_export_service",
            "stock_quant_v2.ops_domain.services.m8_daily_ops_service",
            "stock_quant_v2.ops_domain.services.m8_scheduler_service",
            "stock_quant_v2.ops_domain.services.m8_human_review_service",
            "stock_quant_v2.ops_domain.services.m8_excel_export_service",
            "stock_quant_v2.ops_domain.services.m8_alert_log_audit_service",
        ]

        rows = []
        for module_name in modules:
            item = self._import_check(module_name)
            rows.append(
                {
                    "module": module_name,
                    "status": item["status"],
                    "message": item["message"],
                }
            )
        return rows

    def _check_db_connection(self) -> dict[str, Any]:
        try:
            value = self.session.execute(text("select 1 as ok")).scalar()
            return {
                "status": "PASS" if value == 1 else "FAIL",
                "message": "database connection ok" if value == 1 else "database select returned unexpected value",
                "value": value,
            }
        except Exception as exc:
            return {
                "status": "FAIL",
                "message": str(exc),
                "value": None,
            }

    def _check_latest_runs(
        self,
        *,
        portfolio_id: int,
        profile_code: str | None,
    ) -> dict[str, Any]:
        try:
            latest = self.query_service.query_latest_runs(
                portfolio_id=portfolio_id,
                profile_code=profile_code,
            )
            return {
                "status": "PASS" if latest.get("overall_status") == "PASS" else "FAIL",
                "message": "latest runs ok",
                "overall_status": latest.get("overall_status"),
                "trading_chain": latest.get("trading_chain"),
                "risk_chain": latest.get("risk_chain"),
            }
        except Exception as exc:
            return {
                "status": "FAIL",
                "message": str(exc),
            }

    def _check_api_app_import(self) -> dict[str, Any]:
        try:
            from stock_quant_v2.api.app import create_app

            app = create_app()
            route_count = len(app.routes)
            return {
                "status": "PASS" if route_count > 0 else "FAIL",
                "message": f"api app import ok; route_count={route_count}",
                "route_count": route_count,
            }
        except Exception as exc:
            return {
                "status": "FAIL",
                "message": str(exc),
                "route_count": 0,
            }

    def _resolve_snapshot_date(self, *, portfolio_id: int, profile_code: str | None) -> str:
        try:
            latest = self.query_service.query_latest_runs(
                portfolio_id=portfolio_id,
                profile_code=profile_code,
            )
            snapshot = ((latest.get("details") or {}).get("latest_snapshot") or {})
            return str(snapshot.get("snapshot_date") or "2026-04-23")
        except Exception:
            return "latest"

    @staticmethod
    def _import_check(module_name: str) -> dict[str, Any]:
        try:
            importlib.import_module(module_name)
            return {
                "status": "PASS",
                "message": "import ok",
            }
        except Exception as exc:
            return {
                "status": "FAIL",
                "message": str(exc),
            }

    @staticmethod
    def _mask_env_value(value: str | None) -> str | None:
        if not value:
            return None
        if len(value) <= 12:
            return "***"
        return value[:6] + "***" + value[-6:]

    @staticmethod
    def _is_writable_dir(path: Path) -> bool:
        try:
            path.mkdir(parents=True, exist_ok=True)
            test_file = path / ".m8_write_test"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink(missing_ok=True)
            return True
        except Exception:
            return False

    @staticmethod
    def _all_status_pass(rows: list[dict[str, Any]]) -> bool:
        return all(row.get("status") == "PASS" for row in rows)

    @staticmethod
    def _all_status_pass_or_warn(rows: list[dict[str, Any]]) -> bool:
        return all(row.get("status") in {"PASS", "WARN"} for row in rows)

    def _render_env_report_md(self, payload: dict[str, Any]) -> str:
        env = payload.get("env_check") or {}
        startup = payload.get("startup_check") or {}

        lines = [
            "# M8.11 Environment / Startup Report",
            "",
            f"- portfolio_id: `{payload.get('portfolio_id')}`",
            f"- profile_code: `{payload.get('profile_code')}`",
            f"- exported_at: `{payload.get('exported_at')}`",
            "",
            "## Status",
            "",
            f"- env_status: `{env.get('overall_status')}`",
            f"- startup_status: `{startup.get('overall_status')}`",
            f"- scheduler_exit_code: `{startup.get('scheduler_exit_code')}`",
            f"- highest_alert_level: `{startup.get('highest_alert_level')}`",
            "",
            "## Checks",
            "",
        ]

        for key, value in (startup.get("checks") or {}).items():
            lines.append(f"- {key}: `{value}`")

        lines.extend(["", "## Warnings", ""])

        warnings = (env.get("warnings") or []) + (startup.get("warnings") or [])
        if warnings:
            for item in warnings:
                lines.append(f"- {item.get('warning_code')}: {item.get('message')}")
        else:
            lines.append("- None")

        lines.extend(["", "## Failures", ""])

        failures = (env.get("failures") or []) + (startup.get("failures") or [])
        if failures:
            for item in failures:
                lines.append(f"- {item.get('check_code')}: {item.get('message')}")
        else:
            lines.append("- None")

        lines.append("")
        return "\n".join(lines)

    def _write_csv(self, path: Path, rows: list[dict[str, Any]]) -> None:
        if not rows:
            path.write_text("", encoding="utf-8-sig")
            return

        fields: list[str] = []
        seen = set()
        for row in rows:
            for key in row.keys():
                if key not in seen:
                    fields.append(key)
                    seen.add(key)

        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({key: self._csv_cell(row.get(key)) for key in fields})

    @staticmethod
    def _json_default(value: Any) -> Any:
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        return str(value)

    @classmethod
    def _csv_cell(cls, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, default=cls._json_default)
        return str(cls._json_default(value))