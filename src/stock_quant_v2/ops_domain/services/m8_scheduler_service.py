from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from sqlalchemy.orm import Session

from stock_quant_v2.ops_domain.services.m8_daily_ops_service import M8DailyOpsService
from stock_quant_v2.ops_domain.services.m8_ops_hygiene_service import M8OpsHygieneService


class M8SchedulerService:
    def __init__(self, session: Session):
        self.session = session
        self.daily_ops_service = M8DailyOpsService(session)
        self.hygiene_service = M8OpsHygieneService(session)

    def scheduler_plan(
        self,
        *,
        portfolio_id: int,
        profile_code: str | None = None,
        output_dir: Path | None = None,
        task_name: str = "stock_quant_v2_m8_daily_ops",
        schedule_time: str = "18:30",
    ) -> dict[str, Any]:
        output_dir = output_dir or Path("artifacts/m8/daily_ops")

        health = self.scheduler_health_check(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
            output_dir=output_dir,
        )

        actions = [
            {
                "step_no": 10,
                "action_code": "HEALTH_CHECK",
                "title": "检查 Scheduler 前置健康状态",
                "command": "python -m stock_quant_v2.scripts.m8_scheduler_health_check",
                "required": True,
            },
            {
                "step_no": 20,
                "action_code": "DAILY_OPS_ENTRYPOINT",
                "title": "执行每日运维入口并导出日报",
                "command": "python -m stock_quant_v2.scripts.m8_daily_ops_entrypoint",
                "required": True,
            },
            {
                "step_no": 30,
                "action_code": "GENERATE_WINDOWS_TASK_TEMPLATE",
                "title": "生成 Windows Task Scheduler 模板",
                "command": "python -m stock_quant_v2.scripts.m8_windows_task_template",
                "required": False,
            },
        ]

        env = [
            f'$env:M8_PORTFOLIO_ID="{portfolio_id}"',
            *([f'$env:M8_RISK_PROFILE_CODE="{profile_code}"'] if profile_code else []),
            f'$env:M8_REPORT_OUTPUT_DIR="{output_dir.as_posix()}"',
            '$env:M8_EXPORT_DAILY_REPORT="true"',
        ]

        return {
            "module": "M8.5",
            "query": "scheduler_plan",
            "task_name": task_name,
            "schedule_time": schedule_time,
            "portfolio_id": portfolio_id,
            "profile_code": profile_code,
            "output_dir": str(output_dir),
            "health": {
                "overall_status": health["overall_status"],
                "scheduler_exit_code": health["scheduler_exit_code"],
                "warnings": health["warnings"],
                "failures": health["failures"],
            },
            "env": env,
            "actions": actions,
            "notes": [
                "M8.5 只生成调度适配入口和模板，不注册真实定时任务。",
                "daily_ops_check 在 strict profile 下可能返回 WARN，但 scheduler_exit_code 仍为 0，只要 failures 为空。",
                "真实启用 Windows Task Scheduler 前，先人工运行 m8_daily_ops_entrypoint。",
            ],
            "overall_status": "PASS" if health["scheduler_exit_code"] == 0 else "FAIL",
        }

    def scheduler_health_check(
        self,
        *,
        portfolio_id: int,
        profile_code: str | None = None,
        output_dir: Path | None = None,
    ) -> dict[str, Any]:
        output_dir = output_dir or Path("artifacts/m8/daily_ops")

        daily_check = self.daily_ops_service.daily_ops_check(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
            export_report=False,
            output_dir=output_dir,
        )

        hygiene_check = self.hygiene_service.ops_run_hygiene_check(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
            stale_after_hours=12,
            limit=200,
            include_protected=False,
        )

        ops_status = self.daily_ops_service.ops_status_summary(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
        )

        checks = {
            "daily_ops_not_fail": {
                "status": "PASS" if daily_check["overall_status"] in {"PASS", "WARN"} else "FAIL",
                "message": "daily ops check must not FAIL",
            },
            "hygiene_pass": {
                "status": "PASS" if hygiene_check["overall_status"] == "PASS" else "FAIL",
                "message": "ops hygiene should pass before scheduling",
            },
            "ops_status_pass": {
                "status": "PASS" if ops_status["overall_status"] == "PASS" else "FAIL",
                "message": "ops status summary should pass before scheduling",
            },
        }

        failures = [
            {
                "check_code": code,
                "message": item["message"],
            }
            for code, item in checks.items()
            if item["status"] == "FAIL"
        ]

        warnings: list[dict[str, Any]] = []

        if daily_check["overall_status"] == "WARN":
            warnings.append(
                {
                    "warning_code": "DAILY_OPS_WARN",
                    "message": "daily_ops_check 返回 WARN；若是 strict profile 风控拒绝导致，则可接受。",
                }
            )

        if hygiene_check.get("warnings"):
            warnings.append(
                {
                    "warning_code": "HYGIENE_WARNINGS_EXIST",
                    "message": "hygiene_check 存在 warnings，请确认是否可接受。",
                    "items": hygiene_check.get("warnings"),
                }
            )

        scheduler_exit_code = 1 if failures else 0

        return {
            "module": "M8.5",
            "query": "scheduler_health_check",
            "portfolio_id": portfolio_id,
            "profile_code": profile_code,
            "checked_at": datetime.utcnow().isoformat(),
            "daily_ops_status": daily_check["overall_status"],
            "hygiene_status": hygiene_check["overall_status"],
            "ops_status": ops_status["overall_status"],
            "checks": checks,
            "warnings": warnings,
            "failures": failures,
            "scheduler_exit_code": scheduler_exit_code,
            "overall_status": "PASS" if scheduler_exit_code == 0 else "FAIL",
        }

    def daily_ops_entrypoint(
        self,
        *,
        portfolio_id: int,
        profile_code: str | None = None,
        output_dir: Path | None = None,
        fail_on_warn: bool = False,
    ) -> dict[str, Any]:
        output_dir = output_dir or Path("artifacts/m8/daily_ops")

        health = self.scheduler_health_check(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
            output_dir=output_dir,
        )

        if health["scheduler_exit_code"] != 0:
            return {
                "module": "M8.5",
                "query": "daily_ops_entrypoint",
                "portfolio_id": portfolio_id,
                "profile_code": profile_code,
                "output_dir": str(output_dir),
                "health": health,
                "daily_report": None,
                "scheduler_exit_code": 1,
                "overall_status": "FAIL",
            }

        daily_report = self.daily_ops_service.daily_ops_check(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
            export_report=True,
            output_dir=output_dir,
        )

        if daily_report["overall_status"] == "FAIL":
            scheduler_exit_code = 1
        elif daily_report["overall_status"] == "WARN" and fail_on_warn:
            scheduler_exit_code = 2
        else:
            scheduler_exit_code = 0

        return {
            "module": "M8.5",
            "query": "daily_ops_entrypoint",
            "portfolio_id": portfolio_id,
            "profile_code": profile_code,
            "output_dir": str(output_dir),
            "health": health,
            "daily_report": {
                "overall_status": daily_report["overall_status"],
                "checks": daily_report.get("checks"),
                "warnings": daily_report.get("warnings"),
                "failures": daily_report.get("failures"),
                "daily_report": daily_report.get("daily_report"),
            },
            "scheduler_exit_code": scheduler_exit_code,
            "overall_status": "PASS" if scheduler_exit_code == 0 else "FAIL",
        }

    def generate_windows_task_template(
        self,
        *,
        output_dir: Path,
        project_root: Path,
        portfolio_id: int,
        profile_code: str | None = None,
        report_output_dir: Path | None = None,
        task_name: str = "stock_quant_v2_m8_daily_ops",
        schedule_time: str = "18:30",
    ) -> dict[str, Any]:
        output_dir.mkdir(parents=True, exist_ok=True)

        report_output_dir = report_output_dir or Path("artifacts/m8/daily_ops")

        python_exe = self._resolve_python_exe(project_root)
        ps1_path = output_dir / f"{task_name}.ps1"
        xml_path = output_dir / f"{task_name}.xml"
        readme_path = output_dir / f"{task_name}_README.md"

        ps1_content = self._render_windows_task_ps1(
            project_root=project_root,
            python_exe=python_exe,
            portfolio_id=portfolio_id,
            profile_code=profile_code,
            report_output_dir=report_output_dir,
        )

        xml_content = self._render_windows_task_xml(
            task_name=task_name,
            ps1_path=ps1_path,
            schedule_time=schedule_time,
        )

        readme_content = self._render_windows_task_readme(
            task_name=task_name,
            ps1_path=ps1_path,
            xml_path=xml_path,
            schedule_time=schedule_time,
        )

        ps1_path.write_text(ps1_content, encoding="utf-8-sig")
        xml_path.write_text(xml_content, encoding="utf-8")
        readme_path.write_text(readme_content, encoding="utf-8")

        return {
            "module": "M8.5",
            "query": "windows_task_template",
            "task_name": task_name,
            "schedule_time": schedule_time,
            "project_root": str(project_root),
            "python_exe": str(python_exe),
            "files": {
                "powershell": str(ps1_path),
                "xml": str(xml_path),
                "readme": str(readme_path),
            },
            "next_manual_commands": [
                f'powershell -NoProfile -ExecutionPolicy Bypass -File "{ps1_path}"',
                f'schtasks /Create /TN "{task_name}" /XML "{xml_path}"',
            ],
            "overall_status": "PASS",
        }

    @staticmethod
    def _resolve_python_exe(project_root: Path) -> Path:
        venv_python = project_root / ".venv" / "Scripts" / "python.exe"
        if venv_python.exists():
            return venv_python
        return Path(sys.executable)

    @staticmethod
    def _render_windows_task_ps1(
        *,
        project_root: Path,
        python_exe: Path,
        portfolio_id: int,
        profile_code: str | None,
        report_output_dir: Path,
    ) -> str:
        profile_line = (
            f'$env:M8_RISK_PROFILE_CODE = "{profile_code}"'
            if profile_code
            else 'Remove-Item Env:M8_RISK_PROFILE_CODE -ErrorAction SilentlyContinue'
        )

        return f"""# M8.5 Daily Ops Entrypoint
# Generated by stock_quant_v2 M8.5.
# This script does not trigger trading. It only runs ops checks and exports reports.

$ErrorActionPreference = "Stop"

Set-Location "{project_root}"

$env:M8_PORTFOLIO_ID = "{portfolio_id}"
{profile_line}
$env:M8_REPORT_OUTPUT_DIR = "{report_output_dir.as_posix()}"
$env:M8_EXPORT_DAILY_REPORT = "true"
$env:M8_FAIL_ON_WARN = "false"

& "{python_exe}" -m stock_quant_v2.scripts.m8_daily_ops_entrypoint

if ($LASTEXITCODE -ne 0) {{
    Write-Host "M8.5 daily ops entrypoint failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}}

Write-Host "M8.5 daily ops entrypoint completed."
exit 0
"""

    @staticmethod
    def _render_windows_task_xml(
        *,
        task_name: str,
        ps1_path: Path,
        schedule_time: str,
    ) -> str:
        now = datetime.utcnow().replace(microsecond=0).isoformat()
        start_boundary = f"2026-01-01T{schedule_time}:00"

        escaped_task_name = escape(task_name)
        escaped_ps1 = escape(str(ps1_path))

        return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Date>{now}</Date>
    <Author>stock_quant_v2</Author>
    <Description>{escaped_task_name} - M8.5 daily ops check and report export template.</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{start_boundary}</StartBoundary>
      <Enabled>false</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>false</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>false</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <ExecutionTimeLimit>PT2H</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>powershell.exe</Command>
      <Arguments>-NoProfile -ExecutionPolicy Bypass -File "{escaped_ps1}"</Arguments>
    </Exec>
  </Actions>
</Task>
"""

    @staticmethod
    @staticmethod
    def _render_windows_task_readme(
            *,
            task_name: str,
            ps1_path: Path,
            xml_path: Path,
            schedule_time: str,
    ) -> str:
        return "\n".join(
            [
                "# M8.5 Windows Task Scheduler Template",
                "",
                "Task name:",
                "",
                str(task_name),
                "",
                "Schedule time:",
                "",
                str(schedule_time),
                "",
                "Generated files:",
                "",
                str(ps1_path),
                str(xml_path),
                "",
                "## 1. Manual test first",
                "",
                "Run:",
                "",
                f'powershell -NoProfile -ExecutionPolicy Bypass -File "{ps1_path}"',
                "",
                "Expected:",
                "",
                "M8.5 daily ops entrypoint completed.",
                "",
                "## 2. Register task manually",
                "",
                "The generated XML is disabled by default. Register manually only after the manual test passes.",
                "",
                f'schtasks /Create /TN "{task_name}" /XML "{xml_path}"',
                "",
                "## 3. Enable manually in Task Scheduler",
                "",
                "Open Windows Task Scheduler, inspect the task, then enable it manually.",
                "",
                "## 4. Current boundary",
                "",
                "This task only runs:",
                "",
                "python -m stock_quant_v2.scripts.m8_daily_ops_entrypoint",
                "",
                "It does not trigger trading, risk application, stale cleanup, or live orders.",
                "",
            ]
        )