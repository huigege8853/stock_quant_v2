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
from stock_quant_v2.ops_domain.services.m8_ops_hygiene_service import M8OpsHygieneService
from stock_quant_v2.ops_domain.services.m8_query_service import M8QueryService
from stock_quant_v2.ops_domain.services.m8_report_export_service import M8ReportExportService
from stock_quant_v2.ops_domain.services.m8_scheduler_service import M8SchedulerService


class M8HumanReviewService:
    def __init__(self, session: Session):
        self.session = session
        self.query_service = M8QueryService(session)
        self.daily_ops_service = M8DailyOpsService(session)
        self.hygiene_service = M8OpsHygieneService(session)
        self.scheduler_service = M8SchedulerService(session)
        self.report_service = M8ReportExportService(session)

    def query_ops_kpi(
        self,
        *,
        portfolio_id: int,
        profile_code: str | None = None,
    ) -> dict[str, Any]:
        latest = self.query_service.query_latest_runs(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
        )

        trading_chain = latest.get("trading_chain") or {}
        risk_chain = latest.get("risk_chain") or {}

        paper_chain = None
        risk_decision = None
        target_diff = None
        snapshot = None
        scheduler_health = None
        hygiene = None

        if self._has_all(
            trading_chain,
            ["target_run_id", "order_run_id", "fill_run_id", "position_run_id", "snapshot_run_id"],
        ):
            paper_chain = self.query_service.query_paper_chain(
                portfolio_id=portfolio_id,
                target_run_id=int(trading_chain["target_run_id"]),
                order_run_id=int(trading_chain["order_run_id"]),
                fill_run_id=int(trading_chain["fill_run_id"]),
                position_run_id=int(trading_chain["position_run_id"]),
                snapshot_run_id=int(trading_chain["snapshot_run_id"]),
            )
            snapshot = self.query_service.query_portfolio_snapshot(
                portfolio_id=portfolio_id,
                snapshot_run_id=int(trading_chain["snapshot_run_id"]),
            )

        if self._has_all(
            risk_chain,
            ["risk_run_id", "source_target_run_id", "adjusted_target_run_id"],
        ):
            risk_decision = self.query_service.query_risk_decision(
                portfolio_id=portfolio_id,
                source_target_run_id=int(risk_chain["source_target_run_id"]),
                adjusted_target_run_id=int(risk_chain["adjusted_target_run_id"]),
                risk_run_id=int(risk_chain["risk_run_id"]),
                limit=200,
            )
            target_diff = self.query_service.query_target_diff(
                portfolio_id=portfolio_id,
                source_target_run_id=int(risk_chain["source_target_run_id"]),
                adjusted_target_run_id=int(risk_chain["adjusted_target_run_id"]),
                risk_run_id=int(risk_chain["risk_run_id"]),
                limit=200,
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

        run_status_counts = self._rows(
            """
            select status, count(*) as cnt
            from ops_run
            group by status
            order by status
            """,
            {},
        )

        latest_snapshot = ((latest.get("details") or {}).get("latest_snapshot")) or {}
        risk_summary = (risk_decision or {}).get("summary") or {}
        diff_summary = (target_diff or {}).get("diff_summary") or {}
        paper_snapshot = (paper_chain or {}).get("snapshot") or {}
        paper_order = (paper_chain or {}).get("order") or {}
        paper_fill = (paper_chain or {}).get("fill") or {}
        paper_position = (paper_chain or {}).get("position") or {}

        kpi = {
            "portfolio_id": portfolio_id,
            "profile_code": profile_code,
            "snapshot_date": latest_snapshot.get("snapshot_date"),
            "total_equity": latest_snapshot.get("total_equity"),
            "holding_count": latest_snapshot.get("holding_count"),
            "order_count": paper_order.get("order_count"),
            "fill_count": paper_fill.get("fill_count"),
            "position_count": paper_position.get("position_count"),
            "snapshot_count": paper_snapshot.get("snapshot_count"),
            "risk_decision_count": risk_summary.get("decision_count"),
            "risk_pass_count": risk_summary.get("pass_count"),
            "risk_warn_count": risk_summary.get("warn_count"),
            "risk_reject_count": risk_summary.get("reject_count"),
            "risk_adjust_count": risk_summary.get("adjust_count"),
            "target_quantity_delta": diff_summary.get("target_quantity_delta"),
            "target_amount_delta": diff_summary.get("target_amount_delta"),
            "scheduler_exit_code": scheduler_health.get("scheduler_exit_code"),
            "scheduler_status": scheduler_health.get("overall_status"),
            "hygiene_status": hygiene.get("overall_status"),
            "running_count": self._count_status(run_status_counts, "RUNNING"),
            "stale_count": self._count_status(run_status_counts, "STALE"),
            "failed_count": self._count_status(run_status_counts, "FAILED"),
            "success_count": self._count_status(run_status_counts, "SUCCESS"),
        }

        checks = {
            "latest_runs_pass": latest.get("overall_status") == "PASS",
            "paper_chain_pass": paper_chain is not None and paper_chain.get("overall_status") == "PASS",
            "risk_decision_pass": risk_decision is not None and risk_decision.get("overall_status") == "PASS",
            "target_diff_pass": target_diff is not None and target_diff.get("overall_status") == "PASS",
            "snapshot_pass": snapshot is not None and snapshot.get("overall_status") == "PASS",
            "scheduler_health_pass": scheduler_health.get("overall_status") == "PASS",
            "hygiene_pass": hygiene.get("overall_status") == "PASS",
            "no_running_runs": int(kpi["running_count"] or 0) == 0,
        }

        warnings: list[dict[str, Any]] = []
        if int(kpi.get("risk_reject_count") or 0) > 0:
            warnings.append(
                {
                    "warning_code": "RISK_REJECT_EXISTS",
                    "message": f"risk decision 存在 REJECT：{kpi.get('risk_reject_count')}",
                }
            )

        if self._decimal_not_zero(kpi.get("target_quantity_delta")):
            warnings.append(
                {
                    "warning_code": "TARGET_QUANTITY_DIFF_EXISTS",
                    "message": f"target quantity delta：{kpi.get('target_quantity_delta')}",
                }
            )

        if self._decimal_not_zero(kpi.get("target_amount_delta")):
            warnings.append(
                {
                    "warning_code": "TARGET_AMOUNT_DIFF_EXISTS",
                    "message": f"target amount delta：{kpi.get('target_amount_delta')}",
                }
            )

        failures = [
            {"check_code": key, "message": "KPI check failed"}
            for key, ok in checks.items()
            if not ok
        ]

        return {
            "module": "M8.6",
            "query": "ops_kpi",
            "portfolio_id": portfolio_id,
            "profile_code": profile_code,
            "checked_at": datetime.utcnow().isoformat(),
            "kpi": kpi,
            "chains": {
                "trading_chain": trading_chain,
                "risk_chain": risk_chain,
            },
            "run_status_counts": run_status_counts,
            "checks": checks,
            "warnings": warnings,
            "failures": failures,
            "overall_status": "FAIL" if failures else ("WARN" if warnings else "PASS"),
        }

    def export_human_review_pack(
        self,
        *,
        output_dir: Path,
        portfolio_id: int,
        profile_code: str | None = None,
    ) -> dict[str, Any]:
        output_dir.mkdir(parents=True, exist_ok=True)

        ops_kpi = self.query_ops_kpi(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
        )

        latest = self.query_service.query_latest_runs(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
        )

        trading_chain = latest.get("trading_chain") or {}
        risk_chain = latest.get("risk_chain") or {}

        daily_ops = self.daily_ops_service.daily_ops_check(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
            export_report=True,
            output_dir=output_dir,
        )

        scheduler_health = self.scheduler_service.scheduler_health_check(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
            output_dir=output_dir,
        )

        hygiene = self.hygiene_service.ops_run_hygiene_check(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
            stale_after_hours=12,
            limit=200,
            include_protected=False,
        )

        paper_chain = None
        risk_decision = None
        target_diff = None
        snapshot = None

        if self._has_all(
            trading_chain,
            ["target_run_id", "order_run_id", "fill_run_id", "position_run_id", "snapshot_run_id"],
        ):
            paper_chain = self.query_service.query_paper_chain(
                portfolio_id=portfolio_id,
                target_run_id=int(trading_chain["target_run_id"]),
                order_run_id=int(trading_chain["order_run_id"]),
                fill_run_id=int(trading_chain["fill_run_id"]),
                position_run_id=int(trading_chain["position_run_id"]),
                snapshot_run_id=int(trading_chain["snapshot_run_id"]),
            )
            snapshot = self.query_service.query_portfolio_snapshot(
                portfolio_id=portfolio_id,
                snapshot_run_id=int(trading_chain["snapshot_run_id"]),
            )

        if self._has_all(
            risk_chain,
            ["risk_run_id", "source_target_run_id", "adjusted_target_run_id"],
        ):
            risk_decision = self.query_service.query_risk_decision(
                portfolio_id=portfolio_id,
                source_target_run_id=int(risk_chain["source_target_run_id"]),
                adjusted_target_run_id=int(risk_chain["adjusted_target_run_id"]),
                risk_run_id=int(risk_chain["risk_run_id"]),
                limit=500,
            )
            target_diff = self.query_service.query_target_diff(
                portfolio_id=portfolio_id,
                source_target_run_id=int(risk_chain["source_target_run_id"]),
                adjusted_target_run_id=int(risk_chain["adjusted_target_run_id"]),
                risk_run_id=int(risk_chain["risk_run_id"]),
                limit=500,
            )

        snapshot_date = (ops_kpi.get("kpi") or {}).get("snapshot_date") or "latest"
        stem = f"m8_human_review_pack_p{portfolio_id}_{snapshot_date}"

        json_path = output_dir / f"{stem}.json"
        md_path = output_dir / f"{stem}.md"
        kpi_csv_path = output_dir / f"{stem}_kpi.csv"
        reason_csv_path = output_dir / f"{stem}_risk_reasons.csv"
        run_status_csv_path = output_dir / f"{stem}_run_status.csv"

        payload = {
            "module": "M8.6",
            "query": "export_human_review_pack",
            "portfolio_id": portfolio_id,
            "profile_code": profile_code,
            "exported_at": datetime.utcnow().isoformat(),
            "ops_kpi": ops_kpi,
            "latest_runs": latest,
            "daily_ops": self._compact_daily_ops(daily_ops),
            "scheduler_health": scheduler_health,
            "hygiene": self._compact_hygiene(hygiene),
            "paper_chain": paper_chain,
            "risk_decision": self._compact_risk_decision(risk_decision),
            "target_diff": self._compact_target_diff(target_diff),
            "snapshot": snapshot,
        }

        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=self._json_default),
            encoding="utf-8",
        )
        md_path.write_text(
            self._render_human_review_md(payload),
            encoding="utf-8",
        )

        self._write_csv(kpi_csv_path, [ops_kpi.get("kpi") or {}])
        self._write_csv(reason_csv_path, (risk_decision or {}).get("reason_summary") or [])
        self._write_csv(run_status_csv_path, ops_kpi.get("run_status_counts") or [])

        files = {
            "json": str(json_path),
            "markdown": str(md_path),
            "kpi_csv": str(kpi_csv_path),
            "risk_reasons_csv": str(reason_csv_path),
            "run_status_csv": str(run_status_csv_path),
        }

        return {
            "module": "M8.6",
            "query": "export_human_review_pack",
            "portfolio_id": portfolio_id,
            "profile_code": profile_code,
            "files": files,
            "ops_kpi_status": ops_kpi.get("overall_status"),
            "daily_ops_status": daily_ops.get("overall_status"),
            "scheduler_health_status": scheduler_health.get("overall_status"),
            "hygiene_status": hygiene.get("overall_status"),
            "overall_status": "PASS"
            if ops_kpi.get("overall_status") in {"PASS", "WARN"}
            and daily_ops.get("overall_status") in {"PASS", "WARN"}
            and scheduler_health.get("overall_status") == "PASS"
            and hygiene.get("overall_status") == "PASS"
            else "FAIL",
        }

    def export_ops_summary_pack(
        self,
        *,
        output_dir: Path,
        portfolio_id: int,
        profile_code: str | None = None,
    ) -> dict[str, Any]:
        output_dir.mkdir(parents=True, exist_ok=True)

        ops_kpi = self.query_ops_kpi(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
        )

        recent_runs = self._rows(
            """
            select
                id,
                run_type,
                run_name,
                status,
                trigger_type,
                requested_at,
                started_at,
                ended_at,
                created_at,
                updated_at,
                error_message
            from ops_run
            order by id desc
            limit 50
            """,
            {},
        )

        snapshot_date = (ops_kpi.get("kpi") or {}).get("snapshot_date") or "latest"
        stem = f"m8_ops_summary_pack_p{portfolio_id}_{snapshot_date}"

        json_path = output_dir / f"{stem}.json"
        md_path = output_dir / f"{stem}.md"
        recent_runs_csv_path = output_dir / f"{stem}_recent_runs.csv"

        payload = {
            "module": "M8.6",
            "query": "export_ops_summary_pack",
            "portfolio_id": portfolio_id,
            "profile_code": profile_code,
            "exported_at": datetime.utcnow().isoformat(),
            "ops_kpi": ops_kpi,
            "recent_runs": recent_runs,
        }

        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=self._json_default),
            encoding="utf-8",
        )
        md_path.write_text(
            self._render_ops_summary_md(payload),
            encoding="utf-8",
        )
        self._write_csv(recent_runs_csv_path, recent_runs)

        return {
            "module": "M8.6",
            "query": "export_ops_summary_pack",
            "portfolio_id": portfolio_id,
            "profile_code": profile_code,
            "files": {
                "json": str(json_path),
                "markdown": str(md_path),
                "recent_runs_csv": str(recent_runs_csv_path),
            },
            "ops_kpi_status": ops_kpi.get("overall_status"),
            "overall_status": "PASS" if ops_kpi.get("overall_status") in {"PASS", "WARN"} else "FAIL",
        }

    def _render_human_review_md(self, payload: dict[str, Any]) -> str:
        ops_kpi = payload.get("ops_kpi") or {}
        kpi = ops_kpi.get("kpi") or {}
        chains = ops_kpi.get("chains") or {}
        trading_chain = chains.get("trading_chain") or {}
        risk_chain = chains.get("risk_chain") or {}
        warnings = ops_kpi.get("warnings") or []
        failures = ops_kpi.get("failures") or []

        lines = [
            "# M8.6 Human Review Pack",
            "",
            f"- portfolio_id: `{payload.get('portfolio_id')}`",
            f"- profile_code: `{payload.get('profile_code')}`",
            f"- snapshot_date: `{kpi.get('snapshot_date')}`",
            f"- exported_at: `{payload.get('exported_at')}`",
            "",
            "## 1. Overall",
            "",
            f"- ops_kpi_status: `{ops_kpi.get('overall_status')}`",
            f"- daily_ops_status: `{(payload.get('daily_ops') or {}).get('overall_status')}`",
            f"- scheduler_health_status: `{(payload.get('scheduler_health') or {}).get('overall_status')}`",
            f"- hygiene_status: `{(payload.get('hygiene') or {}).get('overall_status')}`",
            "",
            "## 2. Portfolio KPI",
            "",
            f"- total_equity: `{kpi.get('total_equity')}`",
            f"- holding_count: `{kpi.get('holding_count')}`",
            f"- order_count: `{kpi.get('order_count')}`",
            f"- fill_count: `{kpi.get('fill_count')}`",
            f"- position_count: `{kpi.get('position_count')}`",
            "",
            "## 3. Risk KPI",
            "",
            f"- risk_decision_count: `{kpi.get('risk_decision_count')}`",
            f"- risk_pass_count: `{kpi.get('risk_pass_count')}`",
            f"- risk_warn_count: `{kpi.get('risk_warn_count')}`",
            f"- risk_reject_count: `{kpi.get('risk_reject_count')}`",
            f"- risk_adjust_count: `{kpi.get('risk_adjust_count')}`",
            "",
            "## 4. Target Diff",
            "",
            f"- target_quantity_delta: `{kpi.get('target_quantity_delta')}`",
            f"- target_amount_delta: `{kpi.get('target_amount_delta')}`",
            "",
            "## 5. Trading Chain",
            "",
            f"- target_run_id: `{trading_chain.get('target_run_id')}`",
            f"- order_run_id: `{trading_chain.get('order_run_id')}`",
            f"- fill_run_id: `{trading_chain.get('fill_run_id')}`",
            f"- position_run_id: `{trading_chain.get('position_run_id')}`",
            f"- snapshot_run_id: `{trading_chain.get('snapshot_run_id')}`",
            "",
            "## 6. Risk Chain",
            "",
            f"- risk_run_id: `{risk_chain.get('risk_run_id')}`",
            f"- source_target_run_id: `{risk_chain.get('source_target_run_id')}`",
            f"- adjusted_target_run_id: `{risk_chain.get('adjusted_target_run_id')}`",
            "",
            "## 7. Run Status",
            "",
            f"- RUNNING: `{kpi.get('running_count')}`",
            f"- SUCCESS: `{kpi.get('success_count')}`",
            f"- STALE: `{kpi.get('stale_count')}`",
            f"- FAILED: `{kpi.get('failed_count')}`",
            "",
            "## 8. Warnings",
            "",
        ]

        if warnings:
            for item in warnings:
                lines.append(f"- {item.get('warning_code')}: {item.get('message')}")
        else:
            lines.append("- None")

        lines.extend(["", "## 9. Failures", ""])

        if failures:
            for item in failures:
                lines.append(f"- {item.get('check_code')}: {item.get('message')}")
        else:
            lines.append("- None")

        lines.extend(
            [
                "",
                "## 10. Human Decision",
                "",
                "- [ ] 复核 portfolio snapshot",
                "- [ ] 复核 paper chain",
                "- [ ] 复核 risk decision",
                "- [ ] 复核 target diff",
                "- [ ] 复核 scheduler health",
                "- [ ] 复核 run hygiene",
                "- [ ] 决定是否进入下一阶段",
                "",
            ]
        )

        return "\n".join(lines)

    def _render_ops_summary_md(self, payload: dict[str, Any]) -> str:
        ops_kpi = payload.get("ops_kpi") or {}
        kpi = ops_kpi.get("kpi") or {}
        recent_runs = payload.get("recent_runs") or []

        lines = [
            "# M8.6 Ops Summary Pack",
            "",
            f"- portfolio_id: `{payload.get('portfolio_id')}`",
            f"- profile_code: `{payload.get('profile_code')}`",
            f"- snapshot_date: `{kpi.get('snapshot_date')}`",
            f"- ops_kpi_status: `{ops_kpi.get('overall_status')}`",
            "",
            "## KPI",
            "",
            f"- total_equity: `{kpi.get('total_equity')}`",
            f"- running_count: `{kpi.get('running_count')}`",
            f"- success_count: `{kpi.get('success_count')}`",
            f"- stale_count: `{kpi.get('stale_count')}`",
            f"- failed_count: `{kpi.get('failed_count')}`",
            f"- scheduler_exit_code: `{kpi.get('scheduler_exit_code')}`",
            "",
            "## Recent Runs",
            "",
            "| id | run_type | status | run_name |",
            "|---:|---|---|---|",
        ]

        for row in recent_runs[:20]:
            lines.append(
                f"| {row.get('id')} | {row.get('run_type')} | {row.get('status')} | {row.get('run_name')} |"
            )

        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _compact_daily_ops(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "overall_status": payload.get("overall_status"),
            "checks": payload.get("checks"),
            "warnings": payload.get("warnings"),
            "failures": payload.get("failures"),
            "daily_report": payload.get("daily_report"),
        }

    @staticmethod
    def _compact_hygiene(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "overall_status": payload.get("overall_status"),
            "status_counts": payload.get("status_counts"),
            "stale_summary": payload.get("stale_summary"),
            "warnings": payload.get("warnings"),
            "failures": payload.get("failures"),
        }

    @staticmethod
    def _compact_risk_decision(payload: dict[str, Any] | None) -> dict[str, Any] | None:
        if payload is None:
            return None
        return {
            "overall_status": payload.get("overall_status"),
            "summary": payload.get("summary"),
            "reason_summary": payload.get("reason_summary"),
            "limit": payload.get("limit"),
        }

    @staticmethod
    def _compact_target_diff(payload: dict[str, Any] | None) -> dict[str, Any] | None:
        if payload is None:
            return None
        return {
            "overall_status": payload.get("overall_status"),
            "source": payload.get("source"),
            "adjusted": payload.get("adjusted"),
            "diff_summary": payload.get("diff_summary"),
            "risk_summary": payload.get("risk_summary"),
            "reason_summary": payload.get("reason_summary"),
            "limit": payload.get("limit"),
        }

    @staticmethod
    def _has_all(payload: dict[str, Any], keys: list[str]) -> bool:
        return all(payload.get(key) is not None for key in keys)

    @staticmethod
    def _count_status(rows: list[dict[str, Any]], status: str) -> int:
        for row in rows:
            if row.get("status") == status:
                return int(row.get("cnt") or 0)
        return 0

    @staticmethod
    def _decimal_not_zero(value: Any) -> bool:
        if value is None:
            return False
        try:
            return Decimal(str(value)) != Decimal("0")
        except Exception:
            return False

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