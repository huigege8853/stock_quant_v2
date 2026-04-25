from __future__ import annotations

import csv
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from stock_quant_v2.ops_domain.services.m8_daily_ops_service import M8DailyOpsService
from stock_quant_v2.ops_domain.services.m8_human_review_service import M8HumanReviewService
from stock_quant_v2.ops_domain.services.m8_ops_hygiene_service import M8OpsHygieneService
from stock_quant_v2.ops_domain.services.m8_query_service import M8QueryService
from stock_quant_v2.ops_domain.services.m8_scheduler_service import M8SchedulerService


class M8AlertLogAuditService:
    def __init__(self, session: Session):
        self.session = session
        self.query_service = M8QueryService(session)
        self.daily_ops_service = M8DailyOpsService(session)
        self.human_review_service = M8HumanReviewService(session)
        self.scheduler_service = M8SchedulerService(session)
        self.hygiene_service = M8OpsHygieneService(session)

    def ops_alert_check(
        self,
        *,
        portfolio_id: int,
        profile_code: str | None = None,
    ) -> dict[str, Any]:
        ops_kpi = self.human_review_service.query_ops_kpi(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
        )
        daily_ops = self.daily_ops_service.daily_ops_check(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
            export_report=False,
        )
        scheduler_health = self.scheduler_service.scheduler_health_check(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
            output_dir=Path("artifacts/m8/daily_ops"),
        )
        hygiene = self.hygiene_service.ops_run_hygiene_check(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
            stale_after_hours=12,
            limit=200,
            include_protected=False,
        )

        kpi = ops_kpi.get("kpi") or {}
        alerts: list[dict[str, Any]] = []

        self._add_alert(
            alerts,
            condition=ops_kpi.get("overall_status") == "FAIL",
            level="CRITICAL",
            alert_code="OPS_KPI_FAIL",
            title="Ops KPI failed",
            message="M8 ops KPI returned FAIL.",
            source="m8_query_ops_kpi",
            payload={"failures": ops_kpi.get("failures")},
        )

        self._add_alert(
            alerts,
            condition=daily_ops.get("overall_status") == "FAIL",
            level="CRITICAL",
            alert_code="DAILY_OPS_FAIL",
            title="Daily ops failed",
            message="M8 daily ops check returned FAIL.",
            source="m8_daily_ops_check",
            payload={"failures": daily_ops.get("failures")},
        )

        self._add_alert(
            alerts,
            condition=scheduler_health.get("scheduler_exit_code") not in {0, None},
            level="CRITICAL",
            alert_code="SCHEDULER_EXIT_NON_ZERO",
            title="Scheduler health exit code is non-zero",
            message=f"scheduler_exit_code={scheduler_health.get('scheduler_exit_code')}",
            source="m8_scheduler_health_check",
            payload={"scheduler_health": scheduler_health},
        )

        self._add_alert(
            alerts,
            condition=hygiene.get("overall_status") == "FAIL",
            level="CRITICAL",
            alert_code="HYGIENE_FAIL",
            title="Ops hygiene failed",
            message="M8 hygiene check returned FAIL.",
            source="m8_ops_run_hygiene_check",
            payload={"failures": hygiene.get("failures")},
        )

        running_count = int(kpi.get("running_count") or 0)
        self._add_alert(
            alerts,
            condition=running_count > 0,
            level="CRITICAL",
            alert_code="RUNNING_RUNS_EXIST",
            title="RUNNING ops_run exists",
            message=f"RUNNING count = {running_count}",
            source="ops_run",
            payload={"running_count": running_count},
        )

        failed_count = int(kpi.get("failed_count") or 0)
        self._add_alert(
            alerts,
            condition=failed_count > 0,
            level="WARN",
            alert_code="FAILED_RUNS_EXIST",
            title="FAILED ops_run exists",
            message=f"FAILED count = {failed_count}",
            source="ops_run",
            payload={"failed_count": failed_count},
        )

        stale_count = int(kpi.get("stale_count") or 0)
        self._add_alert(
            alerts,
            condition=stale_count > 0,
            level="INFO",
            alert_code="STALE_RUNS_EXIST",
            title="STALE ops_run exists",
            message=f"STALE count = {stale_count}",
            source="ops_run",
            payload={"stale_count": stale_count},
        )

        risk_reject_count = int(kpi.get("risk_reject_count") or 0)
        self._add_alert(
            alerts,
            condition=risk_reject_count > 0,
            level="WARN",
            alert_code="RISK_REJECT_EXISTS",
            title="Risk reject exists",
            message=f"risk_reject_count = {risk_reject_count}",
            source="risk_decision",
            payload={"risk_reject_count": risk_reject_count},
        )

        risk_warn_count = int(kpi.get("risk_warn_count") or 0)
        self._add_alert(
            alerts,
            condition=risk_warn_count > 0,
            level="WARN",
            alert_code="RISK_WARN_EXISTS",
            title="Risk warn exists",
            message=f"risk_warn_count = {risk_warn_count}",
            source="risk_decision",
            payload={"risk_warn_count": risk_warn_count},
        )

        risk_adjust_count = int(kpi.get("risk_adjust_count") or 0)
        self._add_alert(
            alerts,
            condition=risk_adjust_count > 0,
            level="WARN",
            alert_code="RISK_ADJUST_EXISTS",
            title="Risk adjust exists",
            message=f"risk_adjust_count = {risk_adjust_count}",
            source="risk_decision",
            payload={"risk_adjust_count": risk_adjust_count},
        )

        target_quantity_delta = kpi.get("target_quantity_delta")
        self._add_alert(
            alerts,
            condition=self._decimal_not_zero(target_quantity_delta),
            level="WARN",
            alert_code="TARGET_QUANTITY_DIFF_EXISTS",
            title="Target quantity changed after risk overlay",
            message=f"target_quantity_delta = {target_quantity_delta}",
            source="target_diff",
            payload={"target_quantity_delta": target_quantity_delta},
        )

        target_amount_delta = kpi.get("target_amount_delta")
        self._add_alert(
            alerts,
            condition=self._decimal_not_zero(target_amount_delta),
            level="WARN",
            alert_code="TARGET_AMOUNT_DIFF_EXISTS",
            title="Target amount changed after risk overlay",
            message=f"target_amount_delta = {target_amount_delta}",
            source="target_diff",
            payload={"target_amount_delta": target_amount_delta},
        )

        alert_counts = self._alert_counts(alerts)
        highest_level = self._highest_level(alerts)

        return {
            "module": "M8.10",
            "query": "ops_alert_check",
            "portfolio_id": portfolio_id,
            "profile_code": profile_code,
            "checked_at": datetime.utcnow().isoformat(),
            "highest_level": highest_level,
            "alert_counts": alert_counts,
            "alerts": alerts,
            "source_status": {
                "ops_kpi_status": ops_kpi.get("overall_status"),
                "daily_ops_status": daily_ops.get("overall_status"),
                "scheduler_health_status": scheduler_health.get("overall_status"),
                "scheduler_exit_code": scheduler_health.get("scheduler_exit_code"),
                "hygiene_status": hygiene.get("overall_status"),
            },
            "kpi": kpi,
            "overall_status": "FAIL" if highest_level == "CRITICAL" else ("WARN" if highest_level == "WARN" else "PASS"),
        }

    def export_alert_report(
        self,
        *,
        output_dir: Path,
        portfolio_id: int,
        profile_code: str | None = None,
    ) -> dict[str, Any]:
        output_dir.mkdir(parents=True, exist_ok=True)

        alert_check = self.ops_alert_check(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
        )
        snapshot_date = (alert_check.get("kpi") or {}).get("snapshot_date") or "latest"
        stem = f"m8_alert_report_p{portfolio_id}_{snapshot_date}"

        json_path = output_dir / f"{stem}.json"
        md_path = output_dir / f"{stem}.md"
        csv_path = output_dir / f"{stem}_alerts.csv"

        json_path.write_text(
            json.dumps(alert_check, ensure_ascii=False, indent=2, default=self._json_default),
            encoding="utf-8",
        )
        md_path.write_text(
            self._render_alert_report_md(alert_check),
            encoding="utf-8",
        )
        self._write_csv(csv_path, alert_check.get("alerts") or [])

        return {
            "module": "M8.10",
            "query": "export_alert_report",
            "portfolio_id": portfolio_id,
            "profile_code": profile_code,
            "files": {
                "json": str(json_path),
                "markdown": str(md_path),
                "alerts_csv": str(csv_path),
            },
            "alert_status": alert_check.get("overall_status"),
            "highest_level": alert_check.get("highest_level"),
            "overall_status": "PASS" if alert_check.get("overall_status") in {"PASS", "WARN"} else "FAIL",
        }

    def query_ops_logs(
        self,
        *,
        status: str | None = None,
        run_type: str | None = None,
        limit: int = 100,
        include_error_only: bool = False,
    ) -> dict[str, Any]:
        rows = self._rows(
            """
            select
                id,
                run_uid,
                run_type,
                run_name,
                status,
                trigger_type,
                parent_run_id,
                requested_at,
                started_at,
                ended_at,
                created_at,
                updated_at,
                error_message,
                case
                    when status = 'FAILED' then 'ERROR'
                    when status = 'STALE' then 'WARN'
                    when status = 'RUNNING' then 'WARN'
                    else 'INFO'
                end as log_level
            from ops_run
            where (
                    cast(:status as text) is null
                    or status = cast(:status as text)
                  )
              and (
                    cast(:run_type as text) is null
                    or run_type = cast(:run_type as text)
                  )
              and (
                    cast(:include_error_only as boolean) = false
                    or coalesce(error_message, '') <> ''
                    or status in ('FAILED', 'STALE', 'RUNNING')
                  )
            order by id desc
            limit cast(:limit as bigint)
            """,
            {
                "status": status,
                "run_type": run_type,
                "include_error_only": include_error_only,
                "limit": limit,
            },
        )

        return {
            "module": "M8.10",
            "query": "ops_logs",
            "status": status,
            "run_type": run_type,
            "limit": limit,
            "include_error_only": include_error_only,
            "log_count": len(rows),
            "logs": rows,
            "overall_status": "PASS",
        }

    def export_audit_snapshot(
        self,
        *,
        output_dir: Path,
        portfolio_id: int,
        profile_code: str | None = None,
    ) -> dict[str, Any]:
        output_dir.mkdir(parents=True, exist_ok=True)

        latest = self.query_service.query_latest_runs(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
        )
        ops_kpi = self.human_review_service.query_ops_kpi(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
        )
        alert_check = self.ops_alert_check(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
        )
        logs = self.query_ops_logs(
            limit=100,
            include_error_only=True,
        )

        run_status_counts = self._rows(
            """
            select status, count(*) as cnt
            from ops_run
            group by status
            order by status
            """,
            {},
        )

        run_type_counts = self._rows(
            """
            select run_type, status, count(*) as cnt
            from ops_run
            group by run_type, status
            order by run_type, status
            """,
            {},
        )

        latest_snapshot = ((latest.get("details") or {}).get("latest_snapshot") or {})
        snapshot_date = latest_snapshot.get("snapshot_date") or (ops_kpi.get("kpi") or {}).get("snapshot_date") or "latest"
        stem = f"m8_audit_snapshot_p{portfolio_id}_{snapshot_date}"

        payload = {
            "module": "M8.10",
            "query": "audit_snapshot",
            "portfolio_id": portfolio_id,
            "profile_code": profile_code,
            "exported_at": datetime.utcnow().isoformat(),
            "latest_runs": latest,
            "ops_kpi": ops_kpi,
            "alert_check": alert_check,
            "run_status_counts": run_status_counts,
            "run_type_counts": run_type_counts,
            "error_logs_preview": logs.get("logs") or [],
        }

        json_path = output_dir / f"{stem}.json"
        md_path = output_dir / f"{stem}.md"
        status_csv_path = output_dir / f"{stem}_run_status.csv"
        run_type_csv_path = output_dir / f"{stem}_run_type_status.csv"
        logs_csv_path = output_dir / f"{stem}_error_logs.csv"

        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=self._json_default),
            encoding="utf-8",
        )
        md_path.write_text(
            self._render_audit_snapshot_md(payload),
            encoding="utf-8",
        )
        self._write_csv(status_csv_path, run_status_counts)
        self._write_csv(run_type_csv_path, run_type_counts)
        self._write_csv(logs_csv_path, logs.get("logs") or [])

        return {
            "module": "M8.10",
            "query": "export_audit_snapshot",
            "portfolio_id": portfolio_id,
            "profile_code": profile_code,
            "files": {
                "json": str(json_path),
                "markdown": str(md_path),
                "run_status_csv": str(status_csv_path),
                "run_type_status_csv": str(run_type_csv_path),
                "error_logs_csv": str(logs_csv_path),
            },
            "alert_status": alert_check.get("overall_status"),
            "overall_status": "PASS" if alert_check.get("overall_status") in {"PASS", "WARN"} else "FAIL",
        }

    @staticmethod
    def _add_alert(
        alerts: list[dict[str, Any]],
        *,
        condition: bool,
        level: str,
        alert_code: str,
        title: str,
        message: str,
        source: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        if not condition:
            return

        alerts.append(
            {
                "level": level,
                "alert_code": alert_code,
                "title": title,
                "message": message,
                "source": source,
                "payload": payload or {},
            }
        )

    @staticmethod
    def _alert_counts(alerts: list[dict[str, Any]]) -> dict[str, int]:
        result = {"CRITICAL": 0, "WARN": 0, "INFO": 0}
        for alert in alerts:
            level = str(alert.get("level") or "INFO")
            result[level] = result.get(level, 0) + 1
        return result

    @staticmethod
    def _highest_level(alerts: list[dict[str, Any]]) -> str:
        levels = [str(alert.get("level") or "INFO") for alert in alerts]
        if "CRITICAL" in levels:
            return "CRITICAL"
        if "WARN" in levels:
            return "WARN"
        if "INFO" in levels:
            return "INFO"
        return "NONE"

    @staticmethod
    def _decimal_not_zero(value: Any) -> bool:
        if value is None:
            return False
        try:
            return Decimal(str(value)) != Decimal("0")
        except Exception:
            return False

    def _render_alert_report_md(self, payload: dict[str, Any]) -> str:
        lines = [
            "# M8.10 Alert Report",
            "",
            f"- portfolio_id: `{payload.get('portfolio_id')}`",
            f"- profile_code: `{payload.get('profile_code')}`",
            f"- checked_at: `{payload.get('checked_at')}`",
            f"- overall_status: `{payload.get('overall_status')}`",
            f"- highest_level: `{payload.get('highest_level')}`",
            "",
            "## Alert Counts",
            "",
        ]

        for key, value in (payload.get("alert_counts") or {}).items():
            lines.append(f"- {key}: `{value}`")

        lines.extend(["", "## Alerts", ""])

        alerts = payload.get("alerts") or []
        if not alerts:
            lines.append("- None")
        else:
            for item in alerts:
                lines.append(
                    f"- `{item.get('level')}` `{item.get('alert_code')}` "
                    f"{item.get('title')}｜{item.get('message')}"
                )

        lines.extend(
            [
                "",
                "## Source Status",
                "",
            ]
        )
        for key, value in (payload.get("source_status") or {}).items():
            lines.append(f"- {key}: `{value}`")

        lines.append("")
        return "\n".join(lines)

    def _render_audit_snapshot_md(self, payload: dict[str, Any]) -> str:
        ops_kpi = payload.get("ops_kpi") or {}
        kpi = ops_kpi.get("kpi") or {}
        alert_check = payload.get("alert_check") or {}

        lines = [
            "# M8.10 Audit Snapshot",
            "",
            f"- portfolio_id: `{payload.get('portfolio_id')}`",
            f"- profile_code: `{payload.get('profile_code')}`",
            f"- exported_at: `{payload.get('exported_at')}`",
            "",
            "## Summary",
            "",
            f"- ops_kpi_status: `{ops_kpi.get('overall_status')}`",
            f"- alert_status: `{alert_check.get('overall_status')}`",
            f"- highest_alert_level: `{alert_check.get('highest_level')}`",
            f"- scheduler_exit_code: `{kpi.get('scheduler_exit_code')}`",
            f"- running_count: `{kpi.get('running_count')}`",
            f"- stale_count: `{kpi.get('stale_count')}`",
            f"- failed_count: `{kpi.get('failed_count')}`",
            f"- success_count: `{kpi.get('success_count')}`",
            "",
            "## Trading / Risk Chain",
            "",
            f"- trading_chain: `{json.dumps((payload.get('latest_runs') or {}).get('trading_chain') or {}, ensure_ascii=False, default=str)}`",
            f"- risk_chain: `{json.dumps((payload.get('latest_runs') or {}).get('risk_chain') or {}, ensure_ascii=False, default=str)}`",
            "",
            "## Alert Counts",
            "",
        ]

        for key, value in (alert_check.get("alert_counts") or {}).items():
            lines.append(f"- {key}: `{value}`")

        lines.append("")
        return "\n".join(lines)

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