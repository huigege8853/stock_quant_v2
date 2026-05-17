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
    freshness_basis: str = "report_date"


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
        WaterlineSpec("core_price_limit_daily", "trade_date", freshness_basis="signal_as_of_date"),
        WaterlineSpec("market_index_bar", "trade_date", freshness_basis="signal_as_of_date"),
        WaterlineSpec("analytics_feature_snapshot", "trade_date", freshness_basis="signal_as_of_date"),
        WaterlineSpec("analytics_instrument_factor_snapshot", "trade_date", freshness_basis="signal_as_of_date"),
        WaterlineSpec("analytics_instrument_indicator_snapshot", "trade_date", freshness_basis="signal_as_of_date"),
        WaterlineSpec("strategy_signal", "as_of_date", "run_id", critical=True, freshness_basis="signal_as_of_date"),
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

        signal_as_of_date = self._resolve_signal_as_of_date(resolved_report_date)
        waterline = self._build_waterline(
            report_date=resolved_report_date,
            signal_as_of_date=signal_as_of_date,
        )
        campaign_reports = [
            self._build_campaign_section(
                project_root=project_root,
                campaign=campaign,
                report_date=resolved_report_date,
                detail_limit=detail_limit,
            )
            for campaign in production_campaigns
        ]
        market_context = self._build_market_context(
            report_date=resolved_report_date,
            campaign_reports=campaign_reports,
            detail_limit=detail_limit,
        )
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
            "signal_as_of_date": signal_as_of_date,
            "waterline": waterline,
            "market_context": market_context,
            "campaigns": campaign_reports,
            "artifact_index": artifact_index,
            "checks": checks,
            "observation_notes": self._build_observation_notes(
                overall_status=overall_status,
                waterline=waterline,
                market_context=market_context,
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

    def _resolve_signal_as_of_date(self, report_date: date) -> date:
        previous_trade_date = self._safe_scalar(
            """
            select previous_trade_date
            from public.meta_trading_calendar
            where trade_date = :report_date
            limit 1
            """,
            {"report_date": report_date},
        )
        resolved = self._to_date(previous_trade_date)
        if resolved is not None:
            return resolved

        fallback = self._safe_scalar(
            """
            select max(trade_date)
            from public.meta_trading_calendar
            where is_open = true
              and trade_date < :report_date
            """,
            {"report_date": report_date},
        )
        resolved = self._to_date(fallback)
        return resolved or report_date

    def _build_waterline(self, *, report_date: date, signal_as_of_date: date) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for spec in self.WATERLINE_SPECS:
            row: dict[str, Any] = {
                "table_name": spec.table_name,
                "date_column": spec.date_column,
                "run_id_column": spec.run_id_column,
                "critical": spec.critical,
                "freshness_basis": spec.freshness_basis,
                "expected_date": signal_as_of_date if spec.freshness_basis == "signal_as_of_date" else report_date,
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
                expected_date = row["expected_date"]
                if max_date is None:
                    row["status"] = "FAIL" if spec.critical else "WARN"
                    row["reason"] = "no_date"
                elif max_date >= expected_date:
                    row["status"] = "PASS"
                    row["reason"] = f"fresh_for_{spec.freshness_basis}:{max_date}>={expected_date}"
                else:
                    row["status"] = "FAIL" if spec.critical else "WARN"
                    row["reason"] = f"max_date_before_{spec.freshness_basis}:{max_date}<{expected_date}"
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
            "trade_details": [],
            "ledger_summary": [],
            "runtime_observation": {},
            "snapshot": None,
            "positions_preview": [],
            "top_gainers": [],
            "top_losers": [],
            "risk_metrics": {},
            "campaign_risk_checks": [],
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
        trade_summary = section.get("trade_summary") or {}
        orders = trade_summary.get("orders") if isinstance(trade_summary, dict) else {}
        fills = trade_summary.get("fills") if isinstance(trade_summary, dict) else {}
        order_run_id = (orders or {}).get("order_run_id")
        fill_run_id = (fills or {}).get("fill_run_id")
        if order_run_id is not None:
            section["trade_details"] = self._trade_details(
                portfolio_id=portfolio_id,
                order_run_id=int(order_run_id),
                fill_run_id=self._optional_int(fill_run_id),
                limit=detail_limit,
            )
        section["ledger_summary"] = self._ledger_summary(portfolio_id=portfolio_id, report_date=report_date)

        section["snapshot"] = self._latest_snapshot(portfolio_id=portfolio_id, report_date=report_date)
        snapshot = section.get("snapshot") or {}
        position_run_id = snapshot.get("position_run_id") or snapshot.get("snapshot_run_id")
        if position_run_id is not None:
            section["positions_preview"] = self._positions_preview(
                portfolio_id=portfolio_id,
                position_run_id=int(position_run_id),
                total_equity=snapshot.get("total_equity"),
                limit=detail_limit,
            )
            section["risk_metrics"] = self._position_risk_metrics(
                portfolio_id=portfolio_id,
                position_run_id=int(position_run_id),
                total_equity=snapshot.get("total_equity"),
            )
            section["top_gainers"] = self._position_extremes(
                portfolio_id=portfolio_id,
                position_run_id=int(position_run_id),
                order="gain",
                limit=5,
            )
            section["top_losers"] = self._position_extremes(
                portfolio_id=portfolio_id,
                position_run_id=int(position_run_id),
                order="loss",
                limit=5,
            )

        section["runtime_observation"] = self._campaign_runtime_observation(
            project_root=project_root,
            campaign_code=str(campaign.get("campaign_code") or ""),
            report_date=report_date,
            selection_summary=section.get("selection_summary") or {},
            trade_summary=section.get("trade_summary") or {},
            snapshot=section.get("snapshot") or {},
        )

        section["campaign_risk_checks"] = self._campaign_risk_checks(section)

        checks = []
        if section["selection_summary"]:
            checks.append("selection")
        if section["snapshot"]:
            checks.append("snapshot")
        if section["trade_summary"]:
            checks.append("trade")
        risk_statuses = [str(item.get("status") or "WARN") for item in section.get("campaign_risk_checks") or []]
        if len(checks) >= 2:
            section["status"] = "PASS"
            section["reason"] = "production_campaign_observable"
        elif checks:
            section["status"] = "WARN"
            section["reason"] = f"partial_observation:{','.join(checks)}"
        else:
            section["status"] = "FAIL"
            section["reason"] = "no_recent_campaign_runtime_data"

        if section["status"] == "PASS" and any(status == "WARN" for status in risk_statuses):
            section["status"] = "WARN"
            section["reason"] = "production_campaign_observable_with_risk_warning"
        if any(status == "FAIL" for status in risk_statuses):
            section["status"] = "FAIL"
            section["reason"] = "production_campaign_risk_check_failed"
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
               count(*) filter (where upper(status) not in ('CREATED','ACCEPTED','FILLED')) as abnormal_order_count,
               sum(order_quantity) as total_order_quantity,
               sum(estimated_gross_amount) as total_estimated_gross_amount,
               sum(estimated_fee) as total_estimated_fee,
               sum(estimated_net_amount) as total_estimated_net_amount
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
               count(*) filter (where upper(fill_status) not in ('FILLED','SUCCESS','COMPLETED')) as abnormal_fill_count,
               sum(fill_quantity) as total_fill_quantity,
               sum(gross_amount) as gross_amount,
               sum(total_fee_amount) as total_fee_amount,
               sum(net_amount) as net_amount,
               sum(cash_delta) as cash_delta
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

    def _positions_preview(self, *, portfolio_id: int, position_run_id: int, total_equity: Any, limit: int) -> list[dict[str, Any]]:
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
        rows = self._rows(sql, {"portfolio_id": portfolio_id, "position_run_id": position_run_id, "limit": limit})
        for row in rows:
            row["position_weight"] = self._safe_ratio(row.get("market_value"), total_equity)
        return rows

    def _trade_details(self, *, portfolio_id: int, order_run_id: int, fill_run_id: int | None, limit: int) -> list[dict[str, Any]]:
        sql = """
        select
            o.id as order_id,
            o.run_id as order_run_id,
            o.order_date,
            o.effective_date,
            o.instrument_id,
            mi.instrument_code,
            mi.symbol,
            mi.display_name,
            o.order_side,
            o.order_type,
            o.price_fill_rule,
            o.target_quantity,
            o.order_quantity,
            o.estimated_price,
            o.estimated_gross_amount,
            o.estimated_fee,
            o.estimated_net_amount,
            o.status as order_status,
            o.reject_reason,
            f.id as fill_id,
            f.run_id as fill_run_id,
            f.fill_date,
            f.fill_price,
            f.fill_quantity,
            f.gross_amount,
            f.total_fee_amount,
            f.net_amount,
            f.cash_delta,
            f.price_source,
            f.fill_rule,
            f.fill_status,
            t.rank_no,
            t.target_weight,
            t.reason_code as target_reason_code,
            t.status_reason as target_status_reason,
            ss.rank_in_batch as source_rank,
            ss.reason_code as signal_reason_code
        from public.trading_paper_order o
        left join public.trading_paper_fill f
          on f.order_id = o.id
         and (:fill_run_id is null or f.run_id = :fill_run_id)
        left join public.trading_paper_target_position t on t.id = o.target_position_id
        left join public.strategy_signal ss on ss.id = t.strategy_signal_id
        left join public.meta_instrument mi on mi.id = o.instrument_id
        where o.portfolio_id = :portfolio_id
          and o.run_id = :order_run_id
        order by o.id
        limit :limit
        """
        rows = self._rows(
            sql,
            {
                "portfolio_id": portfolio_id,
                "order_run_id": order_run_id,
                "fill_run_id": fill_run_id,
                "limit": limit,
            },
        )
        for row in rows:
            reason_parts = self._trade_reason_parts(row)
            row["trade_reason_parts"] = reason_parts
            row["trade_reason_summary"] = self._trade_reason_summary(reason_parts)
            row["trade_reason"] = self._trade_reason(row)
        return rows

    def _campaign_runtime_observation(
        self,
        *,
        project_root: Path,
        campaign_code: str,
        report_date: date,
        selection_summary: dict[str, Any],
        trade_summary: dict[str, Any],
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        orders = trade_summary.get("orders") if isinstance(trade_summary, dict) else {}
        fills = trade_summary.get("fills") if isinstance(trade_summary, dict) else {}
        daily_artifact = project_root / "artifacts/m6_5/paper_campaign_daily" / f"{campaign_code}_{report_date.isoformat()}.json"
        artifact_payload: dict[str, Any] = {}
        artifact_campaign: dict[str, Any] = {}
        if daily_artifact.exists():
            try:
                artifact_payload = json.loads(daily_artifact.read_text(encoding="utf-8"))
                artifact_campaign = self._find_campaign_payload(artifact_payload, campaign_code) or {}
            except Exception as exc:
                artifact_payload = {"parse_error": f"{type(exc).__name__}:{exc}"}

        snapshot_date = self._to_date(snapshot.get("snapshot_date"))
        effective_date = self._to_date(selection_summary.get("effective_date"))
        fill_date = self._to_date((fills or {}).get("fill_date"))
        order_date = self._to_date((orders or {}).get("effective_date"))
        date_candidates = [x for x in (snapshot_date, effective_date, fill_date, order_date) if x is not None]
        latest_campaign_date = max(date_candidates) if date_candidates else None

        if latest_campaign_date == report_date:
            campaign_data_status = "CURRENT_REPORT_DATE"
        elif latest_campaign_date is None:
            campaign_data_status = "NO_RUNTIME_DATA"
        else:
            campaign_data_status = f"LATEST_CAMPAIGN_DATE_{latest_campaign_date.isoformat()}"

        artifact_action = self._first_present(
            artifact_campaign,
            artifact_payload,
            keys=("action", "planned_action", "runtime_action"),
        )
        artifact_status = self._first_present(
            artifact_campaign,
            artifact_payload,
            keys=("status", "overall_status", "daily_status"),
        )
        artifact_reason = self._first_present(
            artifact_campaign,
            artifact_payload,
            keys=("reason", "message", "status_reason"),
        )

        if not daily_artifact.exists():
            runtime_action = "NO_DAILY_ARTIFACT"
        elif artifact_action:
            runtime_action = str(artifact_action)
        elif latest_campaign_date == report_date:
            runtime_action = "OBSERVED_REPORT_DATE_DATA"
        else:
            runtime_action = "ARTIFACT_PRESENT"

        return {
            "runtime_action": runtime_action,
            "campaign_data_status": campaign_data_status,
            "latest_campaign_date": latest_campaign_date,
            "daily_artifact_path": str(daily_artifact.relative_to(project_root)) if daily_artifact.exists() else str(daily_artifact),
            "daily_artifact_exists": daily_artifact.exists(),
            "daily_artifact_status": artifact_status,
            "daily_artifact_reason": artifact_reason,
            "target_run_id": selection_summary.get("target_run_id"),
            "order_run_id": (orders or {}).get("order_run_id"),
            "fill_run_id": (fills or {}).get("fill_run_id"),
            "snapshot_run_id": snapshot.get("snapshot_run_id"),
            "position_run_id": snapshot.get("position_run_id") or snapshot.get("snapshot_run_id"),
            "note": "Campaign run ids are portfolio/campaign scoped. Waterline max_run_id is table-global and may belong to another portfolio or runtime step.",
        }

    @classmethod
    def _find_campaign_payload(cls, value: Any, campaign_code: str) -> dict[str, Any] | None:
        if not campaign_code:
            return None
        if isinstance(value, dict):
            if str(value.get("campaign_code") or "") == campaign_code:
                return value
            for child in value.values():
                found = cls._find_campaign_payload(child, campaign_code)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = cls._find_campaign_payload(child, campaign_code)
                if found is not None:
                    return found
        return None

    @staticmethod
    def _first_present(*payloads: dict[str, Any], keys: tuple[str, ...]) -> Any:
        for payload in payloads:
            if not isinstance(payload, dict):
                continue
            for key in keys:
                value = payload.get(key)
                if value not in (None, ""):
                    return value
        return None

    def _ledger_summary(self, *, portfolio_id: int, report_date: date) -> list[dict[str, Any]]:
        sql = """
        select
            event_type,
            reason_code,
            count(*) as rows,
            sum(quantity_delta) as total_quantity_delta,
            sum(cash_delta) as total_cash_delta,
            sum(amount_delta) as total_amount_delta
        from public.trading_paper_trade_ledger
        where portfolio_id = :portfolio_id
          and event_date = :report_date
        group by event_type, reason_code
        order by event_type, reason_code
        """
        return self._rows(sql, {"portfolio_id": portfolio_id, "report_date": report_date})

    def _position_risk_metrics(self, *, portfolio_id: int, position_run_id: int, total_equity: Any) -> dict[str, Any]:
        sql = """
        select
            count(*) as position_rows,
            count(*) filter (where upper(position_status) = 'OPEN') as open_position_rows,
            sum(case when total_pnl > 0 then 1 else 0 end) as profitable_position_rows,
            sum(case when total_pnl < 0 then 1 else 0 end) as losing_position_rows,
            max(market_value) as max_market_value,
            sum(market_value) as total_market_value,
            sum(total_pnl) as total_position_pnl,
            min(total_pnl) as min_position_pnl,
            max(total_pnl) as max_position_pnl
        from public.trading_paper_position
        where portfolio_id = :portfolio_id
          and run_id = :position_run_id
        """
        row = self._one_or_none(sql, {"portfolio_id": portfolio_id, "position_run_id": position_run_id}) or {}
        row["max_position_weight"] = self._safe_ratio(row.get("max_market_value"), total_equity)
        row["stock_exposure"] = self._safe_ratio(row.get("total_market_value"), total_equity)
        return row

    def _position_extremes(self, *, portfolio_id: int, position_run_id: int, order: str, limit: int) -> list[dict[str, Any]]:
        direction = "desc" if order == "gain" else "asc"
        sql = f"""
        select
            p.instrument_id,
            mi.instrument_code,
            mi.symbol,
            mi.display_name,
            p.quantity,
            p.market_value,
            p.total_pnl,
            p.position_status
        from public.trading_paper_position p
        left join public.meta_instrument mi on mi.id = p.instrument_id
        where p.portfolio_id = :portfolio_id
          and p.run_id = :position_run_id
        order by p.total_pnl {direction} nulls last, p.market_value desc nulls last
        limit :limit
        """
        return self._rows(sql, {"portfolio_id": portfolio_id, "position_run_id": position_run_id, "limit": limit})

    def _campaign_risk_checks(self, section: dict[str, Any]) -> list[dict[str, Any]]:
        selection = section.get("selection_summary") or {}
        trade = section.get("trade_summary") or {}
        orders = trade.get("orders") if isinstance(trade, dict) else {}
        fills = trade.get("fills") if isinstance(trade, dict) else {}
        snapshot = section.get("snapshot") or {}
        risk = section.get("risk_metrics") or {}

        selected_count = self._optional_int(selection.get("selected_count"))
        order_count = self._optional_int((orders or {}).get("order_count"))
        fill_count = self._optional_int((fills or {}).get("fill_count"))
        holding_count = self._optional_int(snapshot.get("holding_count"))
        rank_out = self._optional_int(selection.get("rank_out_of_scope_rows")) or 0
        abnormal_order_count = self._optional_int((orders or {}).get("abnormal_order_count")) or 0
        abnormal_fill_count = self._optional_int((fills or {}).get("abnormal_fill_count")) or 0
        cash_balance = self._to_decimal_value(snapshot.get("cash_balance"))
        turnover_rate = self._to_decimal_value(snapshot.get("turnover_rate"))
        max_position_weight = self._to_decimal_value(risk.get("max_position_weight"))

        checks: list[dict[str, Any]] = []
        checks.append({
            "check_name": "rank_scope",
            "status": "PASS" if rank_out == 0 else "FAIL",
            "reason": f"rank_out_of_scope_rows={rank_out}",
        })
        order_fill_match = order_count is not None and order_count == fill_count
        checks.append({
            "check_name": "order_fill_consistency",
            "status": "PASS" if order_fill_match else "WARN",
            "reason": f"order={order_count},fill={fill_count}",
        })
        holding_target_match = selected_count is not None and holding_count == selected_count
        checks.append({
            "check_name": "holding_count_vs_selected_count",
            "status": "PASS" if holding_target_match else "WARN",
            "reason": f"selected={selected_count},holding={holding_count}",
        })
        checks.append({
            "check_name": "abnormal_orders",
            "status": "PASS" if abnormal_order_count == 0 else "FAIL",
            "reason": f"abnormal_order_count={abnormal_order_count}",
        })
        checks.append({
            "check_name": "abnormal_fills",
            "status": "PASS" if abnormal_fill_count == 0 else "FAIL",
            "reason": f"abnormal_fill_count={abnormal_fill_count}",
        })
        checks.append({
            "check_name": "cash_non_negative",
            "status": "PASS" if cash_balance is None or cash_balance >= Decimal("0") else "FAIL",
            "reason": f"cash_balance={snapshot.get('cash_balance')}",
        })
        checks.append({
            "check_name": "max_single_position_weight",
            "status": "WARN" if max_position_weight is not None and max_position_weight > Decimal("0.10") else "PASS",
            "reason": f"max_position_weight={risk.get('max_position_weight')}",
        })
        checks.append({
            "check_name": "turnover_rate",
            "status": "WARN" if turnover_rate is not None and turnover_rate > Decimal("1.20") else "PASS",
            "reason": f"turnover_rate={snapshot.get('turnover_rate')}",
        })
        return checks

    @staticmethod
    def _trade_reason(row: dict[str, Any]) -> str:
        parts = ProductionDailyObservationReportBuilder._trade_reason_parts(row)
        values: list[str] = []
        for key in ("strategy_reason", "sizing_reason", "price_reason", "fill_reason"):
            value = parts.get(key)
            if value:
                values.append(str(value))
        return ";".join(values) if values else "not_available"

    @staticmethod
    def _trade_reason_parts(row: dict[str, Any]) -> dict[str, str | None]:
        raw_reasons: list[str] = []
        for key in ("target_reason_code", "signal_reason_code"):
            value = row.get(key)
            if value:
                raw_reasons.append(str(value))
        status_reason = str(row.get("target_status_reason") or "")
        if status_reason:
            raw_reasons.extend([part for part in status_reason.split(";") if part])

        strategy_reason = ProductionDailyObservationReportBuilder._dedupe_join(
            part for part in raw_reasons
            if part and not part.startswith(("M7_", "price_", "raw_target_", "cash_buffer_", "lot_size="))
        )
        sizing_reason = ProductionDailyObservationReportBuilder._dedupe_join(
            part for part in raw_reasons
            if part.startswith(("M7_", "raw_target_", "cash_buffer_", "lot_size="))
        )
        price_context = ProductionDailyObservationReportBuilder._dedupe_join(
            part for part in raw_reasons if part.startswith("price_")
        )
        if row.get("price_source"):
            price_context = ProductionDailyObservationReportBuilder._dedupe_join(
                [price_context, f"fill_price_source={row.get('price_source')}"]
            )
        fill_reason = ProductionDailyObservationReportBuilder._dedupe_join(
            [
                f"fill_rule={row.get('fill_rule')}" if row.get("fill_rule") else None,
                f"fill_status={row.get('fill_status')}" if row.get("fill_status") else None,
                f"order_status={row.get('order_status')}" if row.get("order_status") else None,
            ]
        )
        return {
            "strategy_reason": strategy_reason,
            "sizing_reason": sizing_reason,
            "price_reason": price_context,
            "fill_reason": fill_reason,
        }

    @staticmethod
    def _trade_reason_summary(parts: dict[str, Any]) -> str:
        strategy = parts.get("strategy_reason") or "strategy_reason=not_available"
        sizing = parts.get("sizing_reason") or "sizing_reason=not_available"
        fill = parts.get("fill_reason") or "fill_reason=not_available"
        return f"{strategy}; {sizing}; {fill}"

    @staticmethod
    def _dedupe_join(values: Any, separator: str = ";") -> str | None:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            if value is None:
                continue
            text_value = str(value).strip()
            if not text_value or text_value in seen:
                continue
            seen.add(text_value)
            ordered.append(text_value)
        return separator.join(ordered) if ordered else None

    def _build_market_context(
        self,
        *,
        report_date: date,
        campaign_reports: list[dict[str, Any]],
        detail_limit: int,
    ) -> dict[str, Any]:
        """Build market-wide context for production daily observation.

        This is production observation context, not a research conclusion. It uses
        stable production base-data tables and gracefully degrades when industry or
        concept tags are unavailable.
        """
        breadth = self._market_breadth(report_date=report_date)
        index_overview = self._market_index_overview(report_date=report_date, limit=20)
        strong_stocks = self._market_stock_extremes(report_date=report_date, order="strong", limit=min(detail_limit, 30))
        weak_stocks = self._market_stock_extremes(report_date=report_date, order="weak", limit=min(detail_limit, 30))
        industry_strength = self._tag_strength_summary(
            report_date=report_date,
            tag_type_pattern="SW_INDUSTRY_L2%",
            limit=15,
        )
        concept_strength = self._tag_strength_summary(
            report_date=report_date,
            tag_type_pattern="%CONCEPT%",
            limit=15,
        )
        strategy_alignment = self._strategy_market_alignment(
            report_date=report_date,
            campaign_reports=campaign_reports,
        )
        return {
            "report_date": report_date,
            "status": self._derive_market_context_status(
                breadth=breadth,
                index_overview=index_overview,
                strong_stocks=strong_stocks,
            ),
            "summary": self._market_context_summary(
                breadth=breadth,
                index_overview=index_overview,
                industry_strength=industry_strength,
                strategy_alignment=strategy_alignment,
            ),
            "breadth": breadth,
            "index_overview": index_overview,
            "strong_stocks": strong_stocks,
            "weak_stocks": weak_stocks,
            "industry_strength": industry_strength,
            "concept_strength": concept_strength,
            "strategy_alignment": strategy_alignment,
        }

    def _market_breadth(self, *, report_date: date) -> dict[str, Any]:
        sql = """
        with base as (
            select
                b.instrument_id,
                b.close,
                b.pre_close,
                b.amount,
                b.volume,
                b.turnover_rate,
                b.is_suspended,
                case
                    when b.pct_change is null then
                        case when b.pre_close is null or b.pre_close = 0 then null else b.close / b.pre_close - 1 end
                    when abs(b.pct_change) > 1 then b.pct_change / 100.0
                    else b.pct_change
                end as pct_change,
                l.up_limit,
                l.down_limit
            from public.core_daily_bar b
            left join public.core_price_limit_daily l
              on l.instrument_id = b.instrument_id
             and l.trade_date = b.trade_date
            where b.trade_date = :report_date
              and coalesce(b.is_suspended, false) = false
        )
        select
            count(*) as total_rows,
            count(*) filter (where pct_change > 0) as up_rows,
            count(*) filter (where pct_change < 0) as down_rows,
            count(*) filter (where pct_change = 0) as flat_rows,
            count(*) filter (where pct_change >= 0.03) as up_3pct_rows,
            count(*) filter (where pct_change >= 0.05) as up_5pct_rows,
            count(*) filter (where pct_change <= -0.03) as down_3pct_rows,
            count(*) filter (where pct_change <= -0.05) as down_5pct_rows,
            count(*) filter (where up_limit is not null and close >= up_limit) as limit_up_rows,
            count(*) filter (where down_limit is not null and close <= down_limit) as limit_down_rows,
            count(*) filter (where up_limit is not null and close < up_limit and close >= up_limit * 0.98) as near_limit_up_rows,
            count(*) filter (where down_limit is not null and close > down_limit and close <= down_limit * 1.02) as near_limit_down_rows,
            avg(pct_change) as avg_pct_change,
            percentile_cont(0.5) within group (order by pct_change) as median_pct_change,
            sum(amount) as total_amount
        from base
        """
        row = self._one_or_none(sql, {"report_date": report_date}) or {}
        total = self._to_decimal_value(row.get("total_rows"))
        up = self._to_decimal_value(row.get("up_rows"))
        down = self._to_decimal_value(row.get("down_rows"))
        row["up_ratio"] = (up / total) if total and up is not None else None
        row["down_ratio"] = (down / total) if total and down is not None else None
        row["market_breadth_state"] = self._classify_breadth(row)
        return row

    def _market_index_overview(self, *, report_date: date, limit: int) -> list[dict[str, Any]]:
        sql_with_dim = """
        with curr as (
            select * from public.market_index_bar where trade_date = :report_date
        ), prev as (
            select distinct on (market_index_id)
                market_index_id,
                close as prev_close
            from public.market_index_bar
            where trade_date < :report_date
            order by market_index_id, trade_date desc
        )
        select
            c.market_index_id,
            coalesce(mi.index_code, mi.symbol, ('index_' || c.market_index_id::text)) as index_code,
            coalesce(mi.display_name, mi.index_name, mi.name, ('index_' || c.market_index_id::text)) as index_name,
            c.close,
            p.prev_close,
            case when p.prev_close is null or p.prev_close = 0 then null else c.close / p.prev_close - 1 end as pct_change,
            c.volume,
            c.turnover
        from curr c
        left join prev p on p.market_index_id = c.market_index_id
        left join public.market_index mi on mi.id = c.market_index_id
        order by c.market_index_id
        limit :limit
        """
        fallback_sql = """
        with curr as (
            select * from public.market_index_bar where trade_date = :report_date
        ), prev as (
            select distinct on (market_index_id)
                market_index_id,
                close as prev_close
            from public.market_index_bar
            where trade_date < :report_date
            order by market_index_id, trade_date desc
        )
        select
            c.market_index_id,
            ('index_' || c.market_index_id::text) as index_code,
            ('index_' || c.market_index_id::text) as index_name,
            c.close,
            p.prev_close,
            case when p.prev_close is null or p.prev_close = 0 then null else c.close / p.prev_close - 1 end as pct_change,
            c.volume,
            c.turnover
        from curr c
        left join prev p on p.market_index_id = c.market_index_id
        order by c.market_index_id
        limit :limit
        """
        try:
            return self._rows(sql_with_dim, {"report_date": report_date, "limit": limit})
        except Exception:
            self._rollback_session_safely()
            try:
                return self._rows(fallback_sql, {"report_date": report_date, "limit": limit})
            except Exception:
                self._rollback_session_safely()
                return []

    def _market_stock_extremes(self, *, report_date: date, order: str, limit: int) -> list[dict[str, Any]]:
        direction = "desc" if order == "strong" else "asc"
        sql = f"""
        select
            b.instrument_id,
            mi.instrument_code,
            mi.symbol,
            mi.display_name,
            b.close,
            b.pre_close,
            case
                    when b.pct_change is null then
                        case when b.pre_close is null or b.pre_close = 0 then null else b.close / b.pre_close - 1 end
                    when abs(b.pct_change) > 1 then b.pct_change / 100.0
                    else b.pct_change
                end as pct_change,
            b.amount,
            b.volume,
            b.turnover_rate,
            l.up_limit,
            l.down_limit,
            case when l.up_limit is not null and b.close >= l.up_limit then true else false end as is_limit_up,
            case when l.down_limit is not null and b.close <= l.down_limit then true else false end as is_limit_down
        from public.core_daily_bar b
        left join public.meta_instrument mi on mi.id = b.instrument_id
        left join public.core_price_limit_daily l
          on l.instrument_id = b.instrument_id
         and l.trade_date = b.trade_date
        where b.trade_date = :report_date
          and coalesce(b.is_suspended, false) = false
          and b.pre_close is not null
          and b.pre_close <> 0
        order by pct_change {direction} nulls last, b.amount desc nulls last
        limit :limit
        """
        return self._rows(sql, {"report_date": report_date, "limit": limit})

    def _tag_strength_summary(self, *, report_date: date, tag_type_pattern: str, limit: int) -> dict[str, Any]:
        sql = """
        with stock_ret as (
            select
                b.instrument_id,
                b.close,
                case
                    when b.pct_change is null then
                        case when b.pre_close is null or b.pre_close = 0 then null else b.close / b.pre_close - 1 end
                    when abs(b.pct_change) > 1 then b.pct_change / 100.0
                    else b.pct_change
                end as pct_change,
                b.amount,
                l.up_limit,
                l.down_limit
            from public.core_daily_bar b
            left join public.core_price_limit_daily l
              on l.instrument_id = b.instrument_id
             and l.trade_date = b.trade_date
            where b.trade_date = :report_date
              and coalesce(b.is_suspended, false) = false
        ), tag_rows as (
            select
                t.tag_type,
                t.tag_code,
                t.tag_name,
                sr.instrument_id,
                sr.close,
                sr.pct_change,
                sr.amount,
                sr.up_limit,
                sr.down_limit
            from stock_ret sr
            join public.instrument_tag it
              on it.instrument_id = sr.instrument_id
             and it.effective_from <= :report_date
             and (it.effective_to is null or it.effective_to >= :report_date)
            join public.tag t on t.id = it.tag_id
            where t.is_active = true
              and t.tag_type like :tag_type_pattern
        ), agg as (
            select
                tag_type,
                tag_code,
                tag_name,
                count(*) as instrument_count,
                count(*) filter (where pct_change > 0) as up_rows,
                count(*) filter (where pct_change < 0) as down_rows,
                avg(pct_change) as avg_pct_change,
                percentile_cont(0.5) within group (order by pct_change) as median_pct_change,
                sum(amount) as total_amount,
                count(*) filter (where up_limit is not null and close >= up_limit) as limit_up_rows,
                count(*) filter (where down_limit is not null and close <= down_limit) as limit_down_rows
            from tag_rows
            group by tag_type, tag_code, tag_name
            having count(*) >= 5
        )
        select *
        from agg
        order by avg_pct_change desc nulls last, total_amount desc nulls last
        limit :limit
        """
        try:
            rows = self._rows(sql, {"report_date": report_date, "tag_type_pattern": tag_type_pattern, "limit": limit})
        except Exception as exc:
            self._rollback_session_safely()
            return {"status": "WARN", "reason": f"query_failed:{type(exc).__name__}:{exc}", "rows": []}
        if not rows:
            return {"status": "WARN", "reason": "no_matching_tag_data", "rows": []}
        return {"status": "PASS", "reason": f"rows={len(rows)}", "rows": rows}

    def _strategy_market_alignment(self, *, report_date: date, campaign_reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for campaign in campaign_reports:
            selected_ids = [item.get("instrument_id") for item in campaign.get("selected_instruments") or [] if item.get("instrument_id") is not None]
            holding_ids = [item.get("instrument_id") for item in campaign.get("positions_preview") or [] if item.get("instrument_id") is not None]
            rows.append({
                "campaign_code": campaign.get("campaign_code"),
                "portfolio_id": campaign.get("portfolio_id"),
                "selected_market_stats": self._instrument_market_stats(report_date=report_date, instrument_ids=selected_ids),
                "holding_market_stats": self._instrument_market_stats(report_date=report_date, instrument_ids=holding_ids),
            })
        return rows

    def _instrument_market_stats(self, *, report_date: date, instrument_ids: list[Any]) -> dict[str, Any]:
        cleaned_ids = [int(x) for x in instrument_ids if x is not None]
        if not cleaned_ids:
            return {"instrument_count": 0, "status": "WARN", "reason": "no_instruments"}
        sql = """
        select
            count(*) as instrument_count,
            count(*) filter (where pct_change > 0) as up_rows,
            count(*) filter (where pct_change < 0) as down_rows,
            avg(pct_change) as avg_pct_change,
            count(*) filter (where up_limit is not null and close >= up_limit) as limit_up_rows,
            count(*) filter (where down_limit is not null and close <= down_limit) as limit_down_rows,
            sum(amount) as total_amount
        from (
            select
                b.instrument_id,
                b.close,
                b.amount,
                case
                    when b.pct_change is null then
                        case when b.pre_close is null or b.pre_close = 0 then null else b.close / b.pre_close - 1 end
                    when abs(b.pct_change) > 1 then b.pct_change / 100.0
                    else b.pct_change
                end as pct_change,
                l.up_limit,
                l.down_limit
            from public.core_daily_bar b
            left join public.core_price_limit_daily l
              on l.instrument_id = b.instrument_id
             and l.trade_date = b.trade_date
            where b.trade_date = :report_date
              and b.instrument_id = any(:instrument_ids)
        ) x
        """
        row = self._one_or_none(sql, {"report_date": report_date, "instrument_ids": cleaned_ids}) or {}
        row["status"] = "PASS" if row.get("instrument_count") else "WARN"
        row["reason"] = "market_stats_ready" if row.get("instrument_count") else "no_market_rows"
        return row

    @classmethod
    def _derive_market_context_status(
        cls,
        *,
        breadth: dict[str, Any],
        index_overview: list[dict[str, Any]],
        strong_stocks: list[dict[str, Any]],
    ) -> str:
        if not breadth or not breadth.get("total_rows"):
            return "FAIL"
        if not index_overview or not strong_stocks:
            return "WARN"
        return "PASS"

    @classmethod
    def _market_context_summary(
        cls,
        *,
        breadth: dict[str, Any],
        index_overview: list[dict[str, Any]],
        industry_strength: dict[str, Any],
        strategy_alignment: list[dict[str, Any]],
    ) -> list[str]:
        notes: list[str] = []
        if breadth:
            notes.append(
                "market_breadth="
                f"{breadth.get('market_breadth_state')} "
                f"up_ratio={cls._fmt_percent(breadth.get('up_ratio'), 2)} "
                f"limit_up={breadth.get('limit_up_rows')} limit_down={breadth.get('limit_down_rows')}"
            )
        if index_overview:
            lead = index_overview[0]
            notes.append(
                f"index_sample={lead.get('index_name') or lead.get('index_code')} pct_change={cls._fmt_percent(lead.get('pct_change'), 2)}"
            )
        if industry_strength.get("status") == "PASS" and industry_strength.get("rows"):
            lead = industry_strength["rows"][0]
            notes.append(
                f"strong_industry={lead.get('tag_name')} avg_pct_change={cls._fmt_percent(lead.get('avg_pct_change'), 2)}"
            )
        for item in strategy_alignment:
            selected = item.get("selected_market_stats") or {}
            holding = item.get("holding_market_stats") or {}
            notes.append(
                f"campaign={item.get('campaign_code')} selected_avg_return={cls._fmt_percent(selected.get('avg_pct_change'), 2)} "
                f"holding_avg_return={cls._fmt_percent(holding.get('avg_pct_change'), 2)}"
            )
        return notes

    @staticmethod
    def _classify_breadth(breadth: dict[str, Any]) -> str:
        up_ratio = ProductionDailyObservationReportBuilder._to_decimal_value(breadth.get("up_ratio"))
        limit_up = ProductionDailyObservationReportBuilder._optional_int(breadth.get("limit_up_rows")) or 0
        limit_down = ProductionDailyObservationReportBuilder._optional_int(breadth.get("limit_down_rows")) or 0
        if up_ratio is None:
            return "UNKNOWN"
        if up_ratio >= Decimal("0.60") and limit_up >= limit_down:
            return "BREADTH_STRONG"
        if up_ratio <= Decimal("0.40") or limit_down > limit_up * 2:
            return "BREADTH_WEAK"
        return "BREADTH_NEUTRAL"

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

    @classmethod
    def _build_observation_notes(
        cls,
        *,
        overall_status: str,
        waterline: list[dict[str, Any]],
        market_context: dict[str, Any],
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
        market_status = (market_context or {}).get("status")
        notes.append(f"market_context_status={market_status}。")
        for note in (market_context or {}).get("summary") or []:
            notes.append(str(note))
        for campaign in campaign_reports:
            notes.append(
                f"campaign={campaign.get('campaign_code')} portfolio_id={campaign.get('portfolio_id')} status={campaign.get('status')} reason={campaign.get('reason')}"
            )
            runtime = campaign.get("runtime_observation") or {}
            if runtime:
                notes.append(
                    f"campaign={campaign.get('campaign_code')} runtime_action={runtime.get('runtime_action')} campaign_data_status={runtime.get('campaign_data_status')} latest_campaign_date={runtime.get('latest_campaign_date')}"
                )
            risk = campaign.get("risk_metrics") or {}
            if risk:
                notes.append(
                    f"campaign={campaign.get('campaign_code')} max_position_weight={cls._fmt_percent(risk.get('max_position_weight'), 2)} stock_exposure={cls._fmt_percent(risk.get('stock_exposure'), 2)} total_position_pnl={cls._fmt_money(risk.get('total_position_pnl'))}"
                )
            losers = campaign.get("top_losers") or []
            if losers:
                worst = losers[0]
                code = worst.get("instrument_code") or worst.get("symbol") or worst.get("instrument_id")
                notes.append(
                    f"campaign={campaign.get('campaign_code')} worst_holding={code} total_pnl={cls._fmt_money(worst.get('total_pnl'))}"
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
            f"- signal_as_of_date: `{self._json_default(payload.get('signal_as_of_date'))}`",
            f"- overall_status: `{payload.get('overall_status')}`",
            "",
            "> 这是一份生产端 daily run 观察报告，不是研究报告，不是 M8 full ops 报告，也不是正式实盘交易报告。",
            "",
            "## 1. 数据水位",
            "",
            "| table | basis | expected_date | max_date | rows | max_run_id | status | reason |",
            "|---|---|---:|---:|---:|---:|---|---|",
        ])
        for row in payload.get("waterline") or []:
            lines.append(
                f"| {row.get('table_name')} | {row.get('freshness_basis')} | {self._json_default(row.get('expected_date'))} | {self._json_default(row.get('max_date'))} | {row.get('rows')} | {row.get('max_run_id')} | {row.get('status')} | {row.get('reason')} |"
            )
        market_context = payload.get("market_context") or {}
        breadth = market_context.get("breadth") or {}
        lines.extend([
            "",
            "## 2. 市场环境观察",
            "",
            f"- market_context_status: `{market_context.get('status')}`",
            f"- market_breadth_state: `{breadth.get('market_breadth_state')}`",
            f"- total_rows: `{breadth.get('total_rows')}` / up: `{breadth.get('up_rows')}` / down: `{breadth.get('down_rows')}` / flat: `{breadth.get('flat_rows')}`",
            f"- up_ratio: `{self._fmt_percent(breadth.get('up_ratio'), 2)}` / down_ratio: `{self._fmt_percent(breadth.get('down_ratio'), 2)}`",
            f"- limit_up: `{breadth.get('limit_up_rows')}` / limit_down: `{breadth.get('limit_down_rows')}` / near_limit_up: `{breadth.get('near_limit_up_rows')}` / near_limit_down: `{breadth.get('near_limit_down_rows')}`",
            f"- avg_pct_change: `{self._fmt_percent(breadth.get('avg_pct_change'), 2)}` / median_pct_change: `{self._fmt_percent(breadth.get('median_pct_change'), 2)}` / total_amount: `{self._fmt_money(breadth.get('total_amount'))}`",
            "",
            "### 2.1 指数概况",
            "",
            "| index | close | pct_change | turnover |",
            "|---|---:|---:|---:|",
        ])
        for item in (market_context.get("index_overview") or [])[:12]:
            index_name = item.get("index_name") or item.get("index_code") or item.get("market_index_id")
            lines.append(f"| {index_name} | {self._fmt_money(item.get('close'))} | {self._fmt_percent(item.get('pct_change'), 2)} | {self._fmt_money(item.get('turnover'))} |")
        lines.extend([
            "",
            "### 2.2 强势股 Top",
            "",
            "| code | name | pct_change | close | amount | limit_up |",
            "|---|---|---:|---:|---:|---|",
        ])
        for item in (market_context.get("strong_stocks") or [])[:20]:
            code = item.get("instrument_code") or item.get("symbol") or item.get("instrument_id")
            lines.append(f"| {code} | {item.get('display_name')} | {self._fmt_percent(item.get('pct_change'), 2)} | {self._fmt_money(item.get('close'))} | {self._fmt_money(item.get('amount'))} | {item.get('is_limit_up')} |")
        lines.extend([
            "",
            "### 2.3 弱势股 Top",
            "",
            "| code | name | pct_change | close | amount | limit_down |",
            "|---|---|---:|---:|---:|---|",
        ])
        for item in (market_context.get("weak_stocks") or [])[:20]:
            code = item.get("instrument_code") or item.get("symbol") or item.get("instrument_id")
            lines.append(f"| {code} | {item.get('display_name')} | {self._fmt_percent(item.get('pct_change'), 2)} | {self._fmt_money(item.get('close'))} | {self._fmt_money(item.get('amount'))} | {item.get('is_limit_down')} |")
        lines.extend([
            "",
            "### 2.4 行业强弱",
            "",
            f"- status: `{(market_context.get('industry_strength') or {}).get('status')}` / reason: `{(market_context.get('industry_strength') or {}).get('reason')}`",
            "",
            "| industry | count | up | down | avg_pct_change | median_pct_change | limit_up | amount |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for item in ((market_context.get("industry_strength") or {}).get("rows") or [])[:15]:
            lines.append(f"| {item.get('tag_name')} | {item.get('instrument_count')} | {item.get('up_rows')} | {item.get('down_rows')} | {self._fmt_percent(item.get('avg_pct_change'), 2)} | {self._fmt_percent(item.get('median_pct_change'), 2)} | {item.get('limit_up_rows')} | {self._fmt_money(item.get('total_amount'))} |")
        lines.extend([
            "",
            "### 2.5 概念 / 题材数据状态",
            "",
            f"- status: `{(market_context.get('concept_strength') or {}).get('status')}` / reason: `{(market_context.get('concept_strength') or {}).get('reason')}`",
            "",
            "| concept | count | up | down | avg_pct_change | limit_up | amount |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ])
        for item in ((market_context.get("concept_strength") or {}).get("rows") or [])[:15]:
            lines.append(f"| {item.get('tag_name')} | {item.get('instrument_count')} | {item.get('up_rows')} | {item.get('down_rows')} | {self._fmt_percent(item.get('avg_pct_change'), 2)} | {item.get('limit_up_rows')} | {self._fmt_money(item.get('total_amount'))} |")
        lines.extend([
            "",
            "### 2.6 策略与市场匹配度",
            "",
            "| campaign | selected_count | selected_avg_return | selected_up | selected_down | selected_limit_up | holding_count | holding_avg_return | holding_up | holding_down |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for item in market_context.get("strategy_alignment") or []:
            selected = item.get("selected_market_stats") or {}
            holding = item.get("holding_market_stats") or {}
            lines.append(
                f"| {item.get('campaign_code')} | {selected.get('instrument_count')} | {self._fmt_percent(selected.get('avg_pct_change'), 2)} | {selected.get('up_rows')} | {selected.get('down_rows')} | {selected.get('limit_up_rows')} | {holding.get('instrument_count')} | {self._fmt_percent(holding.get('avg_pct_change'), 2)} | {holding.get('up_rows')} | {holding.get('down_rows')} |"
            )
        lines.extend(["", "## 3. Production Paper Campaigns", ""])
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
                f"- snapshot_run_id: `{snapshot.get('snapshot_run_id')}` / position_run_id: `{snapshot.get('position_run_id') or snapshot.get('snapshot_run_id')}` / snapshot_date: `{snapshot.get('snapshot_date')}`",
                f"- holding_count: `{snapshot.get('holding_count')}`",
                f"- cash_balance: `{self._fmt_money(snapshot.get('cash_balance'))}`",
                f"- market_value: `{self._fmt_money(snapshot.get('market_value'))}`",
                f"- total_equity: `{self._fmt_money(snapshot.get('total_equity'))}`",
                f"- daily_return: `{self._fmt_percent(snapshot.get('daily_return'), 4)}`",
                f"- turnover_rate: `{self._fmt_percent(snapshot.get('turnover_rate'), 2)}`",
                "",
                "#### Daily runtime action",
                "",
            ])
            runtime = campaign.get("runtime_observation") or {}
            lines.extend([
                f"- runtime_action: `{runtime.get('runtime_action')}` / campaign_data_status: `{runtime.get('campaign_data_status')}`",
                f"- latest_campaign_date: `{self._json_default(runtime.get('latest_campaign_date'))}` / daily_artifact_exists: `{runtime.get('daily_artifact_exists')}`",
                f"- target_run_id: `{runtime.get('target_run_id')}` / order_run_id: `{runtime.get('order_run_id')}` / fill_run_id: `{runtime.get('fill_run_id')}` / snapshot_run_id: `{runtime.get('snapshot_run_id')}` / position_run_id: `{runtime.get('position_run_id')}`",
                f"- note: {runtime.get('note')}",
                "",
                "#### 交易增强摘要",
                "",
                f"- order_total_quantity: `{self._fmt_quantity((orders or {}).get('total_order_quantity'))}` / estimated_gross_amount: `{self._fmt_money((orders or {}).get('total_estimated_gross_amount'))}` / estimated_fee: `{self._fmt_money((orders or {}).get('total_estimated_fee'))}`",
                f"- fill_total_quantity: `{self._fmt_quantity((fills or {}).get('total_fill_quantity'))}` / gross_amount: `{self._fmt_money((fills or {}).get('gross_amount'))}` / total_fee: `{self._fmt_money((fills or {}).get('total_fee_amount'))}` / cash_delta: `{self._fmt_money((fills or {}).get('cash_delta'))}`",
                "",
                "#### 仓位风险摘要",
                "",
            ])
            risk = campaign.get("risk_metrics") or {}
            lines.extend([
                f"- position_rows: `{risk.get('position_rows')}` / open_position_rows: `{risk.get('open_position_rows')}`",
                f"- stock_exposure: `{self._fmt_percent(risk.get('stock_exposure'), 2)}` / max_position_weight: `{self._fmt_percent(risk.get('max_position_weight'), 2)}`",
                f"- total_position_pnl: `{self._fmt_money(risk.get('total_position_pnl'))}` / max_position_pnl: `{self._fmt_money(risk.get('max_position_pnl'))}` / min_position_pnl: `{self._fmt_money(risk.get('min_position_pnl'))}`",
                f"- profitable_position_rows: `{risk.get('profitable_position_rows')}` / losing_position_rows: `{risk.get('losing_position_rows')}`",
                "",
                "#### Campaign 风险检查",
                "",
                "| check | status | reason |",
                "|---|---|---|",
            ])
            for check in campaign.get("campaign_risk_checks") or []:
                lines.append(f"| {check.get('check_name')} | {check.get('status')} | {check.get('reason')} |")
            lines.extend([
                "",
                "#### 入选股票预览",
                "",
                "| rank | code | name | weight | score | source_rank | reason |",
                "|---:|---|---|---:|---:|---:|---|",
            ])
            for item in (campaign.get("selected_instruments") or [])[:30]:
                code = item.get("instrument_code") or item.get("symbol") or item.get("instrument_id")
                lines.append(
                    f"| {item.get('rank_no')} | {code} | {item.get('display_name')} | {self._fmt_percent(item.get('target_weight'), 2)} | {self._fmt_decimal(item.get('score'), 4)} | {item.get('source_rank')} | {item.get('target_reason_code') or item.get('signal_reason_code')} |"
                )
            lines.extend([
                "",
                "#### 交易明细预览",
                "",
                "| side | code | name | order_qty | fill_qty | fill_price | gross_amount | fee | order_status | fill_status | strategy_reason | sizing_reason | price_reason | fill_reason |",
                "|---|---|---|---:|---:|---:|---:|---:|---|---|---|---|---|---|",
            ])
            for item in (campaign.get("trade_details") or [])[:30]:
                code = item.get("instrument_code") or item.get("symbol") or item.get("instrument_id")
                lines.append(
                    f"| {item.get('order_side')} | {code} | {item.get('display_name')} | {self._fmt_quantity(item.get('order_quantity'))} | {self._fmt_quantity(item.get('fill_quantity'))} | {self._fmt_money(item.get('fill_price'))} | {self._fmt_money(item.get('gross_amount'))} | {self._fmt_money(item.get('total_fee_amount'))} | {item.get('order_status')} | {item.get('fill_status')} | {(item.get('trade_reason_parts') or {}).get('strategy_reason')} | {(item.get('trade_reason_parts') or {}).get('sizing_reason')} | {(item.get('trade_reason_parts') or {}).get('price_reason')} | {(item.get('trade_reason_parts') or {}).get('fill_reason')} |"
                )
            lines.extend([
                "",
                "#### 交易流水摘要",
                "",
                "| event_type | reason_code | rows | quantity_delta | cash_delta | amount_delta |",
                "|---|---|---:|---:|---:|---:|",
            ])
            for item in campaign.get("ledger_summary") or []:
                lines.append(
                    f"| {item.get('event_type')} | {item.get('reason_code')} | {item.get('rows')} | {self._fmt_quantity(item.get('total_quantity_delta'))} | {self._fmt_money(item.get('total_cash_delta'))} | {self._fmt_money(item.get('total_amount_delta'))} |"
                )
            lines.extend(["", "#### 持仓预览", "", "| code | name | quantity | weight | avg_cost | market_price | market_value | total_pnl | status |", "|---|---|---:|---:|---:|---:|---:|---:|---|"])
            for item in (campaign.get("positions_preview") or [])[:30]:
                code = item.get("instrument_code") or item.get("symbol") or item.get("instrument_id")
                lines.append(
                    f"| {code} | {item.get('display_name')} | {self._fmt_quantity(item.get('quantity'))} | {self._fmt_percent(item.get('position_weight'), 2)} | {self._fmt_money(item.get('avg_cost'))} | {self._fmt_money(item.get('market_price'))} | {self._fmt_money(item.get('market_value'))} | {self._fmt_money(item.get('total_pnl'))} | {item.get('position_status')} |"
                )
            lines.extend(["", "#### 盈亏 Top 观察", "", "| type | code | name | market_value | total_pnl |", "|---|---|---|---:|---:|"])
            for label, rows in (("top_gain", campaign.get("top_gainers") or []), ("top_loss", campaign.get("top_losers") or [])):
                for item in rows[:5]:
                    code = item.get("instrument_code") or item.get("symbol") or item.get("instrument_id")
                    lines.append(f"| {label} | {code} | {item.get('display_name')} | {self._fmt_money(item.get('market_value'))} | {self._fmt_money(item.get('total_pnl'))} |")
            lines.append("")
        lines.extend(["## 4. 风险 / 异常检查", "", "| check | status | reason |", "|---|---|---|"])
        for check in payload.get("checks") or []:
            lines.append(f"| {check.get('check_name')} | {check.get('status')} | {check.get('reason')} |")
        lines.extend(["", "## 5. 产物索引", "", "| campaign | type | path | exists |", "|---|---|---|---|"])
        for row in payload.get("artifact_index") or []:
            lines.append(f"| {row.get('campaign_code')} | {row.get('artifact_type')} | `{row.get('path')}` | {row.get('exists')} |")
        lines.extend(["", "## 6. 观察提示", ""])
        for note in payload.get("observation_notes") or []:
            lines.append(f"- {note}")
        lines.append("")
        return "\n".join(lines)

    def _source_rows(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        rows.append({"section": "metadata", "source": "campaign_config", "value": payload.get("campaign_config_path")})
        for item in payload.get("waterline") or []:
            rows.append({"section": "waterline", "source": item.get("table_name"), "value": item.get("max_date"), "status": item.get("status")})
        market_context = payload.get("market_context") or {}
        rows.append({"section": "market_context", "source": "market_breadth", "value": (market_context.get("breadth") or {}).get("market_breadth_state"), "status": market_context.get("status")})
        rows.append({"section": "market_context", "source": "industry_strength", "value": (market_context.get("industry_strength") or {}).get("reason"), "status": (market_context.get("industry_strength") or {}).get("status")})
        rows.append({"section": "market_context", "source": "concept_strength", "value": (market_context.get("concept_strength") or {}).get("reason"), "status": (market_context.get("concept_strength") or {}).get("status")})
        for campaign in payload.get("campaigns") or []:
            rows.append({"section": "campaign", "source": campaign.get("campaign_code"), "value": campaign.get("portfolio_id"), "status": campaign.get("status")})
        return rows


    def _rollback_session_safely(self) -> None:
        """Rollback failed read transaction so later observation queries can continue."""
        try:
            self.session.rollback()
        except Exception:
            pass

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
            self._rollback_session_safely()
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
    def _fmt_decimal(cls, value: Any, places: int = 2) -> str:
        decimal_value = cls._to_decimal_value(value)
        if decimal_value is None:
            return ""
        quant = Decimal("1") if places <= 0 else Decimal("1").scaleb(-places)
        return f"{decimal_value.quantize(quant):,}"

    @classmethod
    def _fmt_money(cls, value: Any) -> str:
        return cls._fmt_decimal(value, 2)

    @classmethod
    def _fmt_quantity(cls, value: Any) -> str:
        return cls._fmt_decimal(value, 0)

    @classmethod
    def _fmt_percent(cls, value: Any, places: int = 2) -> str:
        decimal_value = cls._to_decimal_value(value)
        if decimal_value is None:
            return ""
        quant = Decimal("1").scaleb(-places)
        return f"{(decimal_value * Decimal('100')).quantize(quant)}%"

    @classmethod
    def _csv_cell(cls, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, default=cls._json_default)
        return str(cls._json_default(value))

    @staticmethod
    def _to_decimal_value(value: Any) -> Decimal | None:
        if value is None or value == "":
            return None
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except Exception:
            return None

    @classmethod
    def _safe_ratio(cls, numerator: Any, denominator: Any) -> Decimal | None:
        num = cls._to_decimal_value(numerator)
        den = cls._to_decimal_value(denominator)
        if num is None or den is None or den == 0:
            return None
        return num / den

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
