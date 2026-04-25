from __future__ import annotations

import csv
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from stock_quant_v2.ops_domain.services.m8_alert_log_audit_service import M8AlertLogAuditService
from stock_quant_v2.ops_domain.services.m8_env_startup_service import M8EnvStartupService
from stock_quant_v2.ops_domain.services.m8_human_review_service import M8HumanReviewService
from stock_quant_v2.ops_domain.services.m8_scheduler_service import M8SchedulerService


class M8SchedulerRegistrationService:
    def __init__(self, session: Session):
        self.session = session
        self.scheduler_service = M8SchedulerService(session)
        self.env_service = M8EnvStartupService(session)
        self.alert_service = M8AlertLogAuditService(session)
        self.human_review_service = M8HumanReviewService(session)

    def scheduler_registration_check(
        self,
        *,
        portfolio_id: int,
        profile_code: str | None = None,
        project_root: Path | None = None,
        scheduler_dir: Path | None = None,
        task_name: str = "stock_quant_v2_m8_daily_ops",
    ) -> dict[str, Any]:
        project_root = project_root or Path.cwd()
        scheduler_dir = scheduler_dir or Path("artifacts/m8/scheduler")

        ps1_path = scheduler_dir / f"{task_name}.ps1"
        xml_path = scheduler_dir / f"{task_name}.xml"
        readme_path = scheduler_dir / f"{task_name}_README.md"

        files = [
            self._file_check("powershell", ps1_path, required=True),
            self._file_check("xml", xml_path, required=True),
            self._file_check("readme", readme_path, required=True),
        ]

        ps1_content = self._safe_read_text(ps1_path)
        xml_content = self._safe_read_text(xml_path)
        readme_content = self._safe_read_text(readme_path)

        template_checks = [
            self._content_check(
                check_code="PS1_HAS_DAILY_OPS_ENTRYPOINT",
                target="powershell",
                condition="m8_daily_ops_entrypoint" in ps1_content,
                message="PS1 should call m8_daily_ops_entrypoint",
            ),
            self._content_check(
                check_code="PS1_HAS_FAIL_ON_WARN_FALSE",
                target="powershell",
                condition='M8_FAIL_ON_WARN = "false"' in ps1_content or 'M8_FAIL_ON_WARN="false"' in ps1_content,
                message="PS1 should keep M8_FAIL_ON_WARN=false for strict profile",
            ),
            self._content_check(
                check_code="PS1_HAS_PORTFOLIO_ID",
                target="powershell",
                condition="M8_PORTFOLIO_ID" in ps1_content,
                message="PS1 should set M8_PORTFOLIO_ID",
            ),
            self._content_check(
                check_code="PS1_HAS_PROFILE_CODE",
                target="powershell",
                condition="M8_RISK_PROFILE_CODE" in ps1_content,
                message="PS1 should set or clear M8_RISK_PROFILE_CODE",
            ),
            self._content_check(
                check_code="XML_HAS_POWERSHELL_COMMAND",
                target="xml",
                condition="powershell.exe" in xml_content,
                message="XML should call powershell.exe",
            ),
            self._content_check(
                check_code="XML_HAS_PS1_PATH",
                target="xml",
                condition=str(ps1_path) in xml_content or ps1_path.as_posix() in xml_content,
                message="XML should reference generated PS1 file",
            ),
            self._content_check(
                check_code="XML_DISABLED_BY_DEFAULT",
                target="xml",
                condition="<Enabled>false</Enabled>" in xml_content,
                message="XML should be disabled by default before manual approval",
            ),
            self._content_check(
                check_code="README_EXISTS_AND_HAS_REGISTER_COMMAND",
                target="readme",
                condition="schtasks /Create" in readme_content,
                message="README should include manual registration command",
            ),
        ]

        scheduler_health = self.scheduler_service.scheduler_health_check(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
            output_dir=Path("artifacts/m8/daily_ops"),
        )

        startup = self.env_service.startup_check(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
            project_root=project_root,
        )

        alert = self.alert_service.ops_alert_check(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
        )

        file_failures = [
            item for item in files
            if item.get("status") == "FAIL"
        ]
        template_failures = [
            item for item in template_checks
            if item.get("status") == "FAIL"
        ]

        checks = {
            "scheduler_files_pass": len(file_failures) == 0,
            "template_checks_pass": len(template_failures) == 0,
            "scheduler_health_pass": scheduler_health.get("overall_status") == "PASS",
            "scheduler_exit_code_zero": scheduler_health.get("scheduler_exit_code") == 0,
            "startup_not_fail": startup.get("overall_status") in {"PASS", "WARN"},
            "alert_no_critical": alert.get("highest_level") != "CRITICAL",
        }

        failures = [
            {"check_code": key, "message": "scheduler registration check failed"}
            for key, ok in checks.items()
            if not ok
        ]

        warnings: list[dict[str, Any]] = []

        if startup.get("overall_status") == "WARN":
            warnings.append(
                {
                    "warning_code": "STARTUP_WARN",
                    "message": "startup_check returned WARN but no failures.",
                }
            )

        if alert.get("overall_status") == "WARN":
            warnings.append(
                {
                    "warning_code": "ALERT_WARN",
                    "message": "alert_check returned WARN but highest level is not CRITICAL.",
                    "highest_level": alert.get("highest_level"),
                    "alert_counts": alert.get("alert_counts"),
                }
            )

        manual_commands = [
            {
                "step_no": 10,
                "title": "手动测试 PS1",
                "command": f'powershell -NoProfile -ExecutionPolicy Bypass -File "{ps1_path}"',
                "required": True,
            },
            {
                "step_no": 20,
                "title": "注册 Windows Task Scheduler 任务",
                "command": f'schtasks /Create /TN "{task_name}" /XML "{xml_path}"',
                "required": False,
            },
            {
                "step_no": 30,
                "title": "人工检查后启用任务",
                "command": f'schtasks /Change /TN "{task_name}" /ENABLE',
                "required": False,
            },
            {
                "step_no": 40,
                "title": "人工禁用任务",
                "command": f'schtasks /Change /TN "{task_name}" /DISABLE',
                "required": False,
            },
            {
                "step_no": 50,
                "title": "人工删除任务",
                "command": f'schtasks /Delete /TN "{task_name}" /F',
                "required": False,
            },
        ]

        return {
            "module": "M8.12",
            "query": "scheduler_registration_check",
            "portfolio_id": portfolio_id,
            "profile_code": profile_code,
            "project_root": str(project_root),
            "scheduler_dir": str(scheduler_dir),
            "task_name": task_name,
            "checked_at": datetime.utcnow().isoformat(),
            "files": files,
            "template_checks": template_checks,
            "scheduler_health_status": scheduler_health.get("overall_status"),
            "scheduler_exit_code": scheduler_health.get("scheduler_exit_code"),
            "startup_status": startup.get("overall_status"),
            "alert_status": alert.get("overall_status"),
            "highest_alert_level": alert.get("highest_level"),
            "checks": checks,
            "warnings": warnings,
            "failures": failures,
            "manual_commands": manual_commands,
            "overall_status": "FAIL" if failures else ("WARN" if warnings else "PASS"),
        }

    def enhanced_final_check(
        self,
        *,
        portfolio_id: int,
        profile_code: str | None = None,
        project_root: Path | None = None,
        scheduler_dir: Path | None = None,
        task_name: str = "stock_quant_v2_m8_daily_ops",
    ) -> dict[str, Any]:
        project_root = project_root or Path.cwd()
        scheduler_dir = scheduler_dir or Path("artifacts/m8/scheduler")

        ops_kpi = self.human_review_service.query_ops_kpi(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
        )
        startup = self.env_service.startup_check(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
            project_root=project_root,
        )
        registration = self.scheduler_registration_check(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
            project_root=project_root,
            scheduler_dir=scheduler_dir,
            task_name=task_name,
        )
        alert = self.alert_service.ops_alert_check(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
        )

        kpi = ops_kpi.get("kpi") or {}

        db_counts = self._rows(
            """
            select status, count(*) as cnt
            from ops_run
            group by status
            order by status
            """,
            {},
        )

        checks = {
            "ops_kpi_not_fail": ops_kpi.get("overall_status") in {"PASS", "WARN"},
            "startup_not_fail": startup.get("overall_status") in {"PASS", "WARN"},
            "registration_not_fail": registration.get("overall_status") in {"PASS", "WARN"},
            "alert_no_critical": alert.get("highest_level") != "CRITICAL",
            "scheduler_exit_code_zero": startup.get("scheduler_exit_code") == 0,
            "running_zero": int(kpi.get("running_count") or 0) == 0,
            "api_app_pass": (startup.get("api_app") or {}).get("status") == "PASS",
            "route_count_positive": int((startup.get("api_app") or {}).get("route_count") or 0) > 0,
            "risk_decision_count_ok": int(kpi.get("risk_decision_count") or 0) == 90,
            "risk_reject_expected": int(kpi.get("risk_reject_count") or 0) == 30,
        }

        failures = [
            {"check_code": key, "message": "M8 enhanced final check failed"}
            for key, ok in checks.items()
            if not ok
        ]

        warnings: list[dict[str, Any]] = []

        for source_name, payload in [
            ("ops_kpi", ops_kpi),
            ("startup", startup),
            ("registration", registration),
            ("alert", alert),
        ]:
            if payload.get("overall_status") == "WARN":
                warnings.append(
                    {
                        "warning_code": f"{source_name.upper()}_WARN",
                        "message": f"{source_name} returned WARN; inspect details.",
                    }
                )

        return {
            "module": "M8.12",
            "query": "enhanced_final_check",
            "portfolio_id": portfolio_id,
            "profile_code": profile_code,
            "checked_at": datetime.utcnow().isoformat(),
            "ops_kpi_status": ops_kpi.get("overall_status"),
            "startup_status": startup.get("overall_status"),
            "registration_status": registration.get("overall_status"),
            "alert_status": alert.get("overall_status"),
            "highest_alert_level": alert.get("highest_level"),
            "scheduler_exit_code": startup.get("scheduler_exit_code"),
            "api_route_count": (startup.get("api_app") or {}).get("route_count"),
            "run_status_counts": db_counts,
            "kpi": kpi,
            "checks": checks,
            "warnings": warnings,
            "failures": failures,
            "overall_status": "FAIL" if failures else ("WARN" if warnings else "PASS"),
        }

    def export_scheduler_registration_pack(
        self,
        *,
        output_dir: Path,
        portfolio_id: int,
        profile_code: str | None = None,
        project_root: Path | None = None,
        scheduler_dir: Path | None = None,
        task_name: str = "stock_quant_v2_m8_daily_ops",
    ) -> dict[str, Any]:
        output_dir.mkdir(parents=True, exist_ok=True)

        registration = self.scheduler_registration_check(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
            project_root=project_root,
            scheduler_dir=scheduler_dir,
            task_name=task_name,
        )
        final_check = self.enhanced_final_check(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
            project_root=project_root,
            scheduler_dir=scheduler_dir,
            task_name=task_name,
        )

        snapshot_date = (final_check.get("kpi") or {}).get("snapshot_date") or "2026-04-23"
        stem = f"m8_scheduler_registration_pack_p{portfolio_id}_{snapshot_date}"

        payload = {
            "module": "M8.12",
            "query": "export_scheduler_registration_pack",
            "portfolio_id": portfolio_id,
            "profile_code": profile_code,
            "exported_at": datetime.utcnow().isoformat(),
            "registration_check": registration,
            "enhanced_final_check": final_check,
        }

        json_path = output_dir / f"{stem}.json"
        md_path = output_dir / f"{stem}.md"
        commands_csv_path = output_dir / f"{stem}_commands.csv"
        checklist_csv_path = output_dir / f"{stem}_checklist.csv"

        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=self._json_default),
            encoding="utf-8",
        )
        md_path.write_text(
            self._render_registration_pack_md(payload),
            encoding="utf-8",
        )
        self._write_csv(commands_csv_path, registration.get("manual_commands") or [])
        self._write_csv(
            checklist_csv_path,
            self._checks_to_rows(registration.get("checks") or {}, prefix="registration")
            + self._checks_to_rows(final_check.get("checks") or {}, prefix="enhanced_final"),
        )

        return {
            "module": "M8.12",
            "query": "export_scheduler_registration_pack",
            "portfolio_id": portfolio_id,
            "profile_code": profile_code,
            "files": {
                "json": str(json_path),
                "markdown": str(md_path),
                "commands_csv": str(commands_csv_path),
                "checklist_csv": str(checklist_csv_path),
            },
            "registration_status": registration.get("overall_status"),
            "enhanced_final_status": final_check.get("overall_status"),
            "overall_status": "PASS"
            if registration.get("overall_status") in {"PASS", "WARN"}
            and final_check.get("overall_status") in {"PASS", "WARN"}
            else "FAIL",
        }

    @staticmethod
    def _file_check(name: str, path: Path, required: bool) -> dict[str, Any]:
        exists = path.exists()
        return {
            "name": name,
            "path": str(path),
            "required": required,
            "exists": exists,
            "status": "PASS" if exists else ("FAIL" if required else "WARN"),
            "message": "available" if exists else "file missing",
        }

    @staticmethod
    def _content_check(
        *,
        check_code: str,
        target: str,
        condition: bool,
        message: str,
    ) -> dict[str, Any]:
        return {
            "check_code": check_code,
            "target": target,
            "status": "PASS" if condition else "FAIL",
            "message": message,
        }

    @staticmethod
    def _safe_read_text(path: Path) -> str:
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            return path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""

    def _render_registration_pack_md(self, payload: dict[str, Any]) -> str:
        registration = payload.get("registration_check") or {}
        final_check = payload.get("enhanced_final_check") or {}

        lines = [
            "# M8.12 Scheduler Registration Pack",
            "",
            f"- portfolio_id: `{payload.get('portfolio_id')}`",
            f"- profile_code: `{payload.get('profile_code')}`",
            f"- exported_at: `{payload.get('exported_at')}`",
            "",
            "## 1. Status",
            "",
            f"- registration_status: `{registration.get('overall_status')}`",
            f"- enhanced_final_status: `{final_check.get('overall_status')}`",
            f"- scheduler_exit_code: `{registration.get('scheduler_exit_code')}`",
            f"- highest_alert_level: `{registration.get('highest_alert_level')}`",
            "",
            "## 2. Manual Commands",
            "",
        ]

        for item in registration.get("manual_commands") or []:
            lines.append(f"{item.get('step_no')}. {item.get('title')}")
            lines.append("")
            lines.append(f"```powershell\n{item.get('command')}\n```")
            lines.append("")

        lines.extend(
            [
                "## 3. Registration Checklist",
                "",
            ]
        )

        for key, value in (registration.get("checks") or {}).items():
            lines.append(f"- [ ] {key}: `{value}`")

        lines.extend(
            [
                "",
                "## 4. Enhanced Final Checklist",
                "",
            ]
        )

        for key, value in (final_check.get("checks") or {}).items():
            lines.append(f"- [ ] {key}: `{value}`")

        lines.extend(
            [
                "",
                "## 5. Boundary",
                "",
                "当前文档只提供注册命令和检查清单，不自动注册或启用 Windows Task Scheduler。",
                "",
            ]
        )

        return "\n".join(lines)

    @staticmethod
    def _checks_to_rows(checks: dict[str, Any], *, prefix: str) -> list[dict[str, Any]]:
        return [
            {
                "section": prefix,
                "check_code": key,
                "passed": bool(value),
            }
            for key, value in checks.items()
        ]

    def _rows(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        rows = self.session.execute(text(sql), params).mappings().all()
        return [dict(row) for row in rows]

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