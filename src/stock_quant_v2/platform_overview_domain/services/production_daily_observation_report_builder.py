from __future__ import annotations

import csv
import json
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class WaterlineSpec:
    table_name: str
    date_column: str
    run_id_column: str | None = None
    critical: bool = False


class ProductionDailyObservationReportBuilder:
    """Build the production-side DailyRun observation report.

    This builder is intentionally production-scoped. It reads production DB state,
    active production paper-campaign config, and existing M6.5/M8 artifacts, then
    writes a total observation report under artifacts/production/daily_observation.
    It does not reuse the research portfolio daily report builder because that
    would blur research and production report semantics.
    """

    WATERLINE_SPECS: tuple[WaterlineSpec, ...] = (
        WaterlineSpec("meta_trading_calendar", "trade_date", critical=True),
        WaterlineSpec("core_daily_bar", "trade_date", critical=True),
        WaterlineSpec("core_adjust_factor", "trade_date", critical=True),
        WaterlineSpec("core_price_limit_daily", "trade_date"),
        WaterlineSpec("market_index_bar", "trade_date"),
        WaterlineSpec("analytics_feature_snapshot", "trade_date"),
        WaterlineSpec("analytics_instrument_factor_snapshot", "trade_date"),
        WaterlineSpec("analytics_instrument_indicator_snapshot", "trade_date"),
        WaterlineSpec("strategy_signal", "as_of_date", "run_id", critical=True),
        WaterlineSpec("trading_paper_target_position", "effective_date", "run_id"),
        WaterlineSpec("trading_paper_order", "effective_date", "run_id"),
        WaterlineSpec("trading_paper_fill", "fill_date", "run_id"),
        WaterlineSpec("trading_paper_position", "position_date", "run_id"),
        WaterlineSpec("trading_paper_portfolio_snapshot", "snapshot_date", "run_id", critical=True),
    )

    def __init__(self, session: Session):
        self.session = session

    def build(
        self,
        *,
        project_root: Path,
        report_date: date | None,
        campaign_config_path: Path,
        execution_context: str,
        output_root: Path,
        detail_limit: int = 50,
    ) -> dict[str, Any]:
        project_root = project_root.resolve()
        if not output_root.is_absolute():
            output_root = project_root / output_root
        campaign_config_path = self._resolve_project_path(project_root, campaign_config_path)

        resolved_report_date = report_date or self._resolve_report_date()
        generated_at = datetime.utcnow().isoformat()
        campaigns_all = self._load_campaigns(campaign_config_path)
        production_campaigns = self._filter_campaigns(campaigns_all, execution_context=execution_context)

        waterline = self._build_waterline(resolved_report_date)
        campaign_reports = [
            self._build_campaign_section(
                project_root=project_root,
                campaign=campaign,
                report_date=resolved_report_date,
                detail_limit=detail_limit,
            )
            for campaign in production_campaigns
        ]
        artifact_index = self._build_artifact_index(
            project_root=project_root,
            campaigns=production_campaigns,
            report_date=resolved_report_date,
        )
        checks = self._build_checks(
            waterline=waterline,
            production_campaigns=production_campaigns,
            campaign_reports=campaign_reports,
            artifact_index=artifact_index,
        )
        overall_status = self._derive_overall_status(checks)

        payload = {
            "report_type": "production_daily_observation_report",
            "execution_context": "production_daily_run",
            "report_context": "production_daily_observation",
            "paper_campaign_context": execution_context,
            "report_date": resolved_report_date,
            "generated_at": generated_at,
            "project_root": str(project_root),
            "campaign_config_path": str(campaign_config_path),
            "campaign_count": len(campaigns_all),
            "production_campaign_count": len(production_campaigns),
            "overall_status": overall_status,
            "waterline": waterline,
            "campaigns": campaign_reports,
            "artifact_index": artifact_index,
            "checks": checks,
            "observation_notes": self._build_observation_notes(
                overall_status=overall_status,
                waterline=waterline,
                campaign_reports=campaign_reports,
                artifact_index=artifact_index,
            ),
        }

        output_dir = output_root / resolved_report_date.isoformat()
        latest_dir = output_root / "latest"
        output_dir.mkdir(parents=True, exist_ok=True)
        latest_dir.mkdir(parents=True, exist_ok=True)

        stem = f"production_daily_observation_{resolved_report_date.isoformat()}"
        json_path = output_dir / f"{stem}.json"
        md_path = output_dir / f"{stem}.md"
        sources_path = output_dir / f"{stem}_sources.csv"
        artifacts_path = output_dir / f"{stem}_artifacts.csv"

        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=self._json_default),
            encoding="utf-8",
        )
        md_path.write_text(self._render_markdown(payload), encoding="utf-8")
        self._write_csv(sources_path, self._source_rows(payload))
        self._write_csv(artifacts_path, artifact_index)

        latest_json = latest_dir / "production_daily_observation_latest.json"
        latest_md = latest_dir / "production_daily_observation_latest.md"
        latest_sources = latest_dir / "production_daily_observation_latest_sources.csv"
        latest_artifacts = latest_dir / "production_daily_observation_latest_artifacts.csv"
        shutil.copyfile(json_path, latest_json)
        shutil.copyfile(md_path, latest_md)
        shutil.copyfile(sources_path, latest_sources)
        shutil.copyfile(artifacts_path, latest_artifacts)

        payload["files"] = {
            "json": str(json_path),
            "markdown": str(md_path),
            "sources_csv": str(sources_path),
            "artifacts_csv": str(artifacts_path),
            "latest_json": str(latest_json),
            "latest_markdown": str(latest_md),
            "latest_sources_csv": str(latest_sources),
            "latest_artifacts_csv": str(latest_artifacts),
        }
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=self._json_default),
            encoding="utf-8",
        )
        shutil.copyfile(json_path, latest_json)
        return payload

    def _resolve_report_date(self) -> date:
        candidates = [
            ("trading_paper_portfolio_snapshot", "snapshot_date"),
            ("core_daily_bar", "trade_date"),
        ]
        for table_name, column_name in candidates:
            value = self._safe_scalar(f"select max({column_name}) from public.{table_name}")
            resolved = self._to_date(value)
            if resolved is not None:
                return resolved
        return date.today()

    @staticmethod
    def _resolve_project_path(project_root: Path, path: Path) -> Path:
        return path if path.is_absolute() else project_root / path

    def _load_campaigns(self, campaign_config_path: Path) -> list[dict[str, Any]]:
        if not campaign_config_path.exists():
            return []
        try:
            data = json.loads(campaign_config_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        if isinstance(data, list):
            return [dict(item) for item in data if isinstance(item, dict)]
        if isinstance(data, dict) and isinstance(data.get("campaigns"), list):
            return [dict(item) for item in data["campaigns"] if isinstance(item, dict)]
        return []

    @staticmethod
    def _filter_campaigns(campaigns: list[dict[str, Any]], *, execution_context: str) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        for campaign in campaigns:
            if str(campaign.get("status") or "").upper() != "ACTIVE":
                continue
            if str(campaign.get("execution_context") or "") != execution_context:
                continue
            selected.append(campaign)
        return selected

    def _build_waterline(self, report_date: date) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for spec in self.WATERLINE_SPECS:
            row: dict[str, Any] = {
                "table_name": spec.table_name,
                "date_column": spec.date_column,
                "run_id_column": spec.run_id_column,
                "critical": spec.critical,
                "rows": None,
                "max_date": None,
                "max_run_id": None,
                "status": "WARN",
                "reason": "not_checked",
            }
            try:
                select_parts = ["count(*) as rows", f"max({spec.date_column}) as max_date"]
                if spec.run_id_column:
                    select_parts.append(f"max({spec.run_id_column}) as max_run_id")
                sql = f"select {', '.join(select_parts)} from public.{spec.table_name}"
                db_row = self.session.execute(text(sql)).mappings().one()
                row["rows"] = db_row.get("rows")
                row["max_date"] = self._to_date(db_row.get("max_date"))
                if spec.run_id_column:
                    row["max_run_id"] = db_row.get("max_run_id")
                max_date = row["max_date"]
                if max_date is None:
                    row["status"] = "FAIL" if spec.critical else "WARN"
                    row["reason"] = "no_date"
                elif max_date >= report_date:
                    row["status"] = "PASS"
                    row["reason"] = "fresh_enough"
                else:
                    row["status"] = "FAIL" if spec.critical else "WARN"
                    row["reason"] = f"max_date_before_report_date:{max_date}<{report_date}"
            except Exception as exc:
                row["status"] = "FAIL" if spec.critical else "WARN"
                row["reason"] = f"query_failed:{type(exc).__name__}:{exc}"
            rows.append(row)
        return rows

    def _build_campaign_section(
        self,
        *,
        project_root: Path,
        campaign: dict[str, Any],
        report_date: date,
        detail_limit: int,
    ) -> dict[str, Any]:
        portfolio_id = self._optional_int(campaign.get("portfolio_id"))
        section: dict[str, Any] = {
            "campaign_code": campaign.get("campaign_code"),
            "campaign_name": campaign.get("campaign_name"),
            "strategy_code": campaign.get("strategy_code"),
            "strategy_version_code": campaign.get("strategy_version_code"),
            "execution_context": campaign.get("execution_context"),
            "validation_stage": campaign.get("validation_stage"),
            "validation_scope": campaign.get("validation_scope"),
            "portfolio_id": portfolio_id,
            "target_count": campaign.get("target_count"),
            "status": "WARN",
            "reason": None,
            "selection_summary": None,
            "selected_instruments": [],
            "trade_summary": None,
            "snapshot": None,
            "positions_preview": [],
            "artifact_files": self._campaign_artifacts(project_root, str(campaign.get("campaign_code") or "")),
        }
        if portfolio_id is None:
            section["reason"] = "missing_portfolio_id"
            return section

        section["selection_summary"] = self._latest_selection_summary(
            portfolio_id=portfolio_id,
            report_date=report_date,
            target_count=self._optional_int(campaign.get("target_count")) or 30,
        )
        target_run_id = ((section.get("selection_summary") or {}).get("target_run_id"))
        if target_run_id is not None:
            section["selected_instruments"] = self._selected_instruments(
                portfolio_id=portfolio_id,
                target_run_id=int(target_run_id),
                limit=detail_limit,
            )
        section["trade_summary"] = self._latest_trade_summary(portfolio_id=portfolio_id, report_date=report_date)
        section["snapshot"] = self._latest_snapshot(portfolio_id=portfolio_id, report_date=report_date)
        position_run_id = ((section.get("snapshot") or {}).get("position_run_id"))
        if position_run_id is not None:
            section["positions_preview"] = self._positions_preview(
                portfolio_id=portfolio_id,
                position_run_id=int(position_run_id),
                limit=detail_limit,
            )

        checks = []
        if section["selection_summary"]:
            checks.append("selection")
        if section["snapshot"]:
            checks.append("snapshot")
        if section["trade_summary"]:
            checks.append("trade")
        if len(checks) >= 2:
            section["status"] = "PASS"
            section["reason"] = "production_campaign_observable"
        elif checks:
            section["status"] = "WARN"
            section["reason"] = f"partial_observation:{','.join(checks)}"
        else:
            section["status"] = "FAIL"
            section["reason"] = "no_recent_campaign_runtime_data"
        return section

    def _latest_selection_summary(self, *, portfolio_id: int, report_date: date, target_count: int) -> dict[str, Any] | None:
        sql = """
        select
            t.run_id as target_run_id,
            t.portfolio_id,
            max(t.effective_date) as effective_date,
            max(t.source_signal_run_id) as source_signal_run_id,
            max(t.source_screen_request_id) as source_screen_request_id,
            count(*) as selected_count,
            min(t.rank_no) as min_target_rank,
            max(t.rank_no) as max_target_rank,
            min(t.score) as min_target_score,
            max(t.score) as max_target_score,
            min(ss.rank_in_batch) as min_source_rank,
            max(ss.rank_in_batch) as max_source_rank,
            count(*) filter (where ss.rank_in_batch <= :target_count) as rank_in_scope_rows,
            count(*) filter (where ss.rank_in_batch > :target_count) as rank_out_of_scope_rows
        from public.trading_paper_target_position t
        left join public.strategy_signal ss on ss.id = t.strategy_signal_id
        where t.portfolio_id = :portfolio_id
          and t.effective_date <= :report_date
          and t.run_id = (
              select max(run_id)
              from public.trading_paper_target_position
              where portfolio_id = :portfolio_id
                and effective_date <= :report_date
          )
        group by t.run_id, t.portfolio_id
        """
        return self._one_or_none(sql, {"portfolio_id": portfolio_id, "report_date": report_date, "target_count": target_count})

    def _selected_instruments(self, *, portfolio_id: int, target_run_id: int, limit: int) -> list[dict[str, Any]]:
        sql = """
        select
            t.instrument_id,
            mi.instrument_code,
            mi.symbol,
            mi.display_name,
            t.rank_no,
            t.score,
            t.target_weight,
            t.target_quantity,
            t.reason_code as target_reason_code,
            ss.rank_in_batch as source_rank,
            ss.raw_score as source_raw_score,
            ss.reason_code as signal_reason_code
        from public.trading_paper_target_position t
        left join public.strategy_signal ss on ss.id = t.strategy_signal_id
        left join public.meta_instrument mi on mi.id = t.instrument_id
        where t.portfolio_id = :portfolio_id
          and t.run_id = :target_run_id
        order by t.rank_no nulls last, t.score desc nulls last, t.instrument_id
        limit :limit
        """
        return self._rows(sql, {"portfolio_id": portfolio_id, "target_run_id": target_run_id, "limit": limit})

    def _latest_trade_summary(self, *, portfolio_id: int, report_date: date) -> dict[str, Any] | None:
        order_sql = """
        select run_id as order_run_id, max(effective_date) as effective_date,
               count(*) as order_count,
               count(*) filter (where upper(order_side) = 'BUY') as buy_order_count,
               count(*) filter (where upper(order_side) = 'SELL') as sell_order_count,
               count(*) filter (where upper(status) not in ('CREATED','ACCEPTED','FILLED')) as abnormal_order_count
        from public.trading_paper_order
        where portfolio_id = :portfolio_id
          and effective_date <= :report_date
          and run_id = (
              select max(run_id) from public.trading_paper_order
              where portfolio_id = :portfolio_id and effective_date <= :report_date
          )
        group by run_id
        """
        fill_sql = """
        select run_id as fill_run_id, max(fill_date) as fill_date,
               count(*) as fill_count,
               count(*) filter (where upper(fill_status) not in ('FILLED','SUCCESS')) as abnormal_fill_count,
               sum(gross_amount) as gross_amount,
               sum(total_fee_amount) as total_fee_amount,
               sum(net_amount) as net_amount
        from public.trading_paper_fill
        where portfolio_id = :portfolio_id
          and fill_date <= :report_date
          and run_id = (
              select max(run_id) from public.trading_paper_fill
              where portfolio_id = :portfolio_id and fill_date <= :report_date
          )
        group by run_id
        """
        orders = self._one_or_none(order_sql, {"portfolio_id": portfolio_id, "report_date": report_date})
        fills = self._one_or_none(fill_sql, {"portfolio_id": portfolio_id, "report_date": report_date})
        if not orders and not fills:
            return None
        return {"orders": orders, "fills": fills}

    def _latest_snapshot(self, *, portfolio_id: int, report_date: date) -> dict[str, Any] | None:
        sql = """
        select
            run_id as snapshot_run_id,
            portfolio_id,
            snapshot_date,
            position_run_id,
            fill_run_id,
            cash_balance,
            market_value,
            total_equity,
            gross_exposure,
            net_exposure,
            holding_count,
            daily_pnl,
            daily_return,
            cumulative_pnl,
            cumulative_return,
            turnover_amount,
            turnover_rate,
            cash_delta,
            total_cost,
            unrealized_pnl,
            realized_pnl,
            open_position_count,
            closed_position_count
        from public.trading_paper_portfolio_snapshot
        where portfolio_id = :portfolio_id
          and snapshot_date <= :report_date
        order by snapshot_date desc, run_id desc
        limit 1
        """
        return self._one_or_none(sql, {"portfolio_id": portfolio_id, "report_date": report_date})

    def _positions_preview(self, *, portfolio_id: int, position_run_id: int, limit: int) -> list[dict[str, Any]]:
        sql = """
        select
            p.instrument_id,
            mi.instrument_code,
            mi.symbol,
            mi.display_name,
            p.quantity,
            p.avg_cost,
            p.market_price,
            p.market_value,
            p.unrealized_pnl,
            p.realized_pnl,
            p.total_pnl,
            p.position_status
        from public.trading_paper_position p
        left join public.meta_instrument mi on mi.id = p.instrument_id
        where p.portfolio_id = :portfolio_id
          and p.run_id = :position_run_id
        order by p.market_value desc nulls last, p.instrument_id
        limit :limit
        """
        return self._rows(sql, {"portfolio_id": portfolio_id, "position_run_id": position_run_id, "limit": limit})

    def _campaign_artifacts(self, project_root: Path, campaign_code: str) -> list[dict[str, Any]]:
        if not campaign_code:
            return []
        artifact_dirs = [
            ("m6_5_daily", project_root / "artifacts/m6_5/paper_campaign_daily"),
            ("m6_5_summary", project_root / "artifacts/m6_5/paper_campaign_summary"),
            ("m8_paper_chain", project_root / "artifacts/m8/paper_chain"),
            ("m8_portfolio_snapshot", project_root / "artifacts/m8/portfolio_snapshot"),
        ]
        rows: list[dict[str, Any]] = []
        for artifact_type, directory in artifact_dirs:
            if not directory.exists():
                rows.append({"artifact_type": artifact_type, "path": str(directory), "exists": False, "kind": "directory"})
                continue
            for path in sorted(directory.glob(f"*{campaign_code}*"))[-20:]:
                rows.append({
                    "artifact_type": artifact_type,
                    "path": str(path.relative_to(project_root)),
                    "exists": path.exists(),
                    "kind": "file",
                })
        return rows

    def _build_artifact_index(self, *, project_root: Path, campaigns: list[dict[str, Any]], report_date: date) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for campaign in campaigns:
            campaign_code = str(campaign.get("campaign_code") or "")
            portfolio_id = campaign.get("portfolio_id")
            for artifact in self._campaign_artifacts(project_root, campaign_code):
                rows.append({"campaign_code": campaign_code, "portfolio_id": portfolio_id, **artifact})
            # Include latest portfolio-specific M8 artifacts even when filenames do not contain campaign_code.
            if portfolio_id is not None:
                for directory in [project_root / "artifacts/m8/paper_chain", project_root / "artifacts/m8/portfolio_snapshot"]:
                    if not directory.exists():
                        continue
                    for path in sorted(directory.glob(f"*p{portfolio_id}_*"))[-20:]:
                        rows.append({
                            "campaign_code": campaign_code,
                            "portfolio_id": portfolio_id,
                            "artifact_type": "m8_portfolio_related",
                            "path": str(path.relative_to(project_root)),
                            "exists": path.exists(),
                            "kind": "file",
                        })
        # Dedupe while preserving order.
        unique: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for row in rows:
            key = (str(row.get("campaign_code")), str(row.get("path")))
            if key in seen:
                continue
            seen.add(key)
            unique.append(row)
        return unique

    def _build_checks(
        self,
        *,
        waterline: list[dict[str, Any]],
        production_campaigns: list[dict[str, Any]],
        campaign_reports: list[dict[str, Any]],
        artifact_index: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        checks: list[dict[str, Any]] = []
        failed_critical = [row for row in waterline if row.get("critical") and row.get("status") == "FAIL"]
        warn_waterline = [row for row in waterline if row.get("status") == "WARN"]
        checks.append({
            "check_name": "critical_waterline_ready",
            "status": "PASS" if not failed_critical else "FAIL",
            "reason": "all_critical_waterlines_ready" if not failed_critical else ",".join(str(x.get("table_name")) for x in failed_critical),
        })
        checks.append({
            "check_name": "noncritical_waterline_warning",
            "status": "PASS" if not warn_waterline else "WARN",
            "reason": "no_noncritical_warning" if not warn_waterline else ",".join(str(x.get("table_name")) for x in warn_waterline),
        })
        checks.append({
            "check_name": "active_production_campaign_exists",
            "status": "PASS" if production_campaigns else "FAIL",
            "reason": f"production_campaign_count={len(production_campaigns)}",
        })
        failed_campaigns = [row for row in campaign_reports if row.get("status") == "FAIL"]
        warn_campaigns = [row for row in campaign_reports if row.get("status") == "WARN"]
        checks.append({
            "check_name": "production_campaign_observable",
            "status": "PASS" if not failed_campaigns and not warn_campaigns else ("FAIL" if failed_campaigns else "WARN"),
            "reason": f"pass={len([x for x in campaign_reports if x.get('status') == 'PASS'])},warn={len(warn_campaigns)},fail={len(failed_campaigns)}",
        })
        checks.append({
            "check_name": "production_artifacts_present",
            "status": "PASS" if artifact_index else "WARN",
            "reason": f"artifact_count={len(artifact_index)}",
        })
        return checks

    @staticmethod
    def _derive_overall_status(checks: list[dict[str, Any]]) -> str:
        statuses = [str(check.get("status") or "WARN") for check in checks]
        if any(status == "FAIL" for status in statuses):
            return "FAIL"
        if any(status == "WARN" for status in statuses):
            return "WARN"
        return "PASS"

    @staticmethod
    def _build_observation_notes(
        *,
        overall_status: str,
        waterline: list[dict[str, Any]],
        campaign_reports: list[dict[str, Any]],
        artifact_index: list[dict[str, Any]],
    ) -> list[str]:
        notes = [
            "本报告是 production_daily_observation_report，不是 research report，也不是 M8 full ops report。",
            f"overall_status={overall_status}。",
        ]
        warn_or_fail = [row for row in waterline if row.get("status") != "PASS"]
        if warn_or_fail:
            notes.append("存在水位 WARN/FAIL，需优先检查：" + ", ".join(str(x.get("table_name")) for x in warn_or_fail[:10]))
        for campaign in campaign_reports:
            notes.append(
                f"campaign={campaign.get('campaign_code')} portfolio_id={campaign.get('portfolio_id')} status={campaign.get('status')} reason={campaign.get('reason')}"
            )
        if not artifact_index:
            notes.append("未发现相关 M6.5/M8 产物索引，需检查 daily run 是否生成报告产物。")
        return notes

    def _render_markdown(self, payload: dict[str, Any]) -> str:
        lines: list[str] = []
        lines.extend([
            "# Production Daily Observation Report",
            "",
            f"- report_date: `{self._json_default(payload.get('report_date'))}`",
            f"- generated_at: `{payload.get('generated_at')}`",
            f"- execution_context: `{payload.get('execution_context')}`",
            f"- report_context: `{payload.get('report_context')}`",
            f"- paper_campaign_context: `{payload.get('paper_campaign_context')}`",
            f"- overall_status: `{payload.get('overall_status')}`",
            "",
            "> 这是一份生产端 daily run 观察报告，不是研究报告，不是 M8 full ops 报告，也不是正式实盘交易报告。",
            "",
            "## 1. 数据水位",
            "",
            "| table | max_date | rows | max_run_id | status | reason |",
            "|---|---:|---:|---:|---|---|",
        ])
        for row in payload.get("waterline") or []:
            lines.append(
                f"| {row.get('table_name')} | {self._json_default(row.get('max_date'))} | {row.get('rows')} | {row.get('max_run_id')} | {row.get('status')} | {row.get('reason')} |"
            )
        lines.extend(["", "## 2. Production Paper Campaigns", ""])
        for campaign in payload.get("campaigns") or []:
            snapshot = campaign.get("snapshot") or {}
            selection = campaign.get("selection_summary") or {}
            trade = campaign.get("trade_summary") or {}
            orders = trade.get("orders") if isinstance(trade, dict) else {}
            fills = trade.get("fills") if isinstance(trade, dict) else {}
            lines.extend([
                f"### {campaign.get('campaign_code')}",
                "",
                f"- status: `{campaign.get('status')}` / reason: `{campaign.get('reason')}`",
                f"- strategy: `{campaign.get('strategy_code')}` / `{campaign.get('strategy_version_code')}`",
                f"- portfolio_id: `{campaign.get('portfolio_id')}`",
                f"- validation_stage: `{campaign.get('validation_stage')}`",
                f"- target_run_id: `{selection.get('target_run_id')}`",
                f"- source_signal_run_id: `{selection.get('source_signal_run_id')}`",
                f"- selected_count: `{selection.get('selected_count')}`",
                f"- source_rank_range: `{selection.get('min_source_rank')}` - `{selection.get('max_source_rank')}`",
                f"- rank_out_of_scope_rows: `{selection.get('rank_out_of_scope_rows')}`",
                f"- order_run_id: `{(orders or {}).get('order_run_id')}` / order_count: `{(orders or {}).get('order_count')}` / buy: `{(orders or {}).get('buy_order_count')}` / sell: `{(orders or {}).get('sell_order_count')}`",
                f"- fill_run_id: `{(fills or {}).get('fill_run_id')}` / fill_count: `{(fills or {}).get('fill_count')}`",
                f"- snapshot_run_id: `{snapshot.get('snapshot_run_id')}` / snapshot_date: `{snapshot.get('snapshot_date')}`",
                f"- holding_count: `{snapshot.get('holding_count')}`",
                f"- cash_balance: `{snapshot.get('cash_balance')}`",
                f"- market_value: `{snapshot.get('market_value')}`",
                f"- total_equity: `{snapshot.get('total_equity')}`",
                f"- daily_return: `{snapshot.get('daily_return')}`",
                f"- turnover_rate: `{snapshot.get('turnover_rate')}`",
                "",
                "#### 入选股票预览",
                "",
                "| rank | code | name | weight | score | source_rank | reason |",
                "|---:|---|---|---:|---:|---:|---|",
            ])
            for item in (campaign.get("selected_instruments") or [])[:30]:
                code = item.get("instrument_code") or item.get("symbol") or item.get("instrument_id")
                lines.append(
                    f"| {item.get('rank_no')} | {code} | {item.get('display_name')} | {item.get('target_weight')} | {item.get('score')} | {item.get('source_rank')} | {item.get('target_reason_code') or item.get('signal_reason_code')} |"
                )
            lines.extend(["", "#### 持仓预览", "", "| code | name | quantity | avg_cost | market_price | market_value | total_pnl | status |", "|---|---|---:|---:|---:|---:|---:|---|"])
            for item in (campaign.get("positions_preview") or [])[:30]:
                code = item.get("instrument_code") or item.get("symbol") or item.get("instrument_id")
                lines.append(
                    f"| {code} | {item.get('display_name')} | {item.get('quantity')} | {item.get('avg_cost')} | {item.get('market_price')} | {item.get('market_value')} | {item.get('total_pnl')} | {item.get('position_status')} |"
                )
            lines.append("")
        lines.extend(["## 3. 风险 / 异常检查", "", "| check | status | reason |", "|---|---|---|"])
        for check in payload.get("checks") or []:
            lines.append(f"| {check.get('check_name')} | {check.get('status')} | {check.get('reason')} |")
        lines.extend(["", "## 4. 产物索引", "", "| campaign | type | path | exists |", "|---|---|---|---|"])
        for row in payload.get("artifact_index") or []:
            lines.append(f"| {row.get('campaign_code')} | {row.get('artifact_type')} | `{row.get('path')}` | {row.get('exists')} |")
        lines.extend(["", "## 5. 观察提示", ""])
        for note in payload.get("observation_notes") or []:
            lines.append(f"- {note}")
        lines.append("")
        return "\n".join(lines)

    def _source_rows(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        rows.append({"section": "metadata", "source": "campaign_config", "value": payload.get("campaign_config_path")})
        for item in payload.get("waterline") or []:
            rows.append({"section": "waterline", "source": item.get("table_name"), "value": item.get("max_date"), "status": item.get("status")})
        for campaign in payload.get("campaigns") or []:
            rows.append({"section": "campaign", "source": campaign.get("campaign_code"), "value": campaign.get("portfolio_id"), "status": campaign.get("status")})
        return rows

    def _rows(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        result = self.session.execute(text(sql), params).mappings().all()
        return [dict(row) for row in result]

    def _one_or_none(self, sql: str, params: dict[str, Any]) -> dict[str, Any] | None:
        result = self.session.execute(text(sql), params).mappings().first()
        return dict(result) if result is not None else None

    def _safe_scalar(self, sql: str, params: dict[str, Any] | None = None) -> Any:
        try:
            return self.session.execute(text(sql), params or {}).scalar()
        except Exception:
            return None

    def _write_csv(self, path: Path, rows: list[dict[str, Any]]) -> None:
        if not rows:
            path.write_text("", encoding="utf-8-sig")
            return
        fields: list[str] = []
        seen: set[str] = set()
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

    @classmethod
    def _csv_cell(cls, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, default=cls._json_default)
        return str(cls._json_default(value))

    @staticmethod
    def _json_default(value: Any) -> Any:
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        return value

    @staticmethod
    def _to_date(value: Any) -> date | None:
        if value is None:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        return None

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None or value == "":
            return None
        return int(value)
