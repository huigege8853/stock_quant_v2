from __future__ import annotations

import csv
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from stock_quant_v2.ops_domain.services.m8_query_service import M8QueryService


class M8ReportExportService:
    def __init__(self, session: Session):
        self.session = session
        self.query_service = M8QueryService(session)

    def export_paper_chain_report(
        self,
        *,
        output_dir: Path,
        portfolio_id: int,
        target_run_id: int,
        order_run_id: int,
        fill_run_id: int,
        position_run_id: int,
        snapshot_run_id: int,
        detail_limit: int = 5000,
    ) -> dict[str, Any]:
        output_dir.mkdir(parents=True, exist_ok=True)

        payload = self.query_service.query_paper_chain(
            portfolio_id=portfolio_id,
            target_run_id=target_run_id,
            order_run_id=order_run_id,
            fill_run_id=fill_run_id,
            position_run_id=position_run_id,
            snapshot_run_id=snapshot_run_id,
        )

        target_rows = self._rows(
            """
            select
                id,
                run_id,
                portfolio_id,
                as_of_date,
                effective_date,
                instrument_id,
                target_side,
                target_weight,
                target_amount,
                target_quantity,
                rank_no,
                score,
                reason_code,
                target_source,
                construction_mode,
                status,
                status_reason
            from trading_paper_target_position
            where portfolio_id = cast(:portfolio_id as bigint)
              and run_id = cast(:run_id as bigint)
            order by effective_date, rank_no, instrument_id
            limit cast(:limit as bigint)
            """,
            {
                "portfolio_id": portfolio_id,
                "run_id": target_run_id,
                "limit": detail_limit,
            },
        )

        order_rows = self._rows(
            """
            select
                id,
                run_id,
                portfolio_id,
                target_position_id,
                instrument_id,
                order_date,
                effective_date,
                order_side,
                order_type,
                price_fill_rule,
                target_quantity,
                order_quantity,
                estimated_price,
                estimated_gross_amount,
                estimated_fee,
                estimated_net_amount,
                status,
                reject_reason
            from trading_paper_order
            where portfolio_id = cast(:portfolio_id as bigint)
              and run_id = cast(:run_id as bigint)
            order by effective_date, instrument_id, id
            limit cast(:limit as bigint)
            """,
            {
                "portfolio_id": portfolio_id,
                "run_id": order_run_id,
                "limit": detail_limit,
            },
        )

        fill_rows = self._rows(
            """
            select
                id,
                run_id,
                portfolio_id,
                order_id,
                instrument_id,
                fill_date,
                fill_price,
                fill_quantity,
                gross_amount,
                commission_amount,
                stamp_duty_amount,
                transfer_fee_amount,
                slippage_amount,
                total_fee_amount,
                net_amount,
                cash_delta,
                price_source,
                fill_rule,
                fill_status
            from trading_paper_fill
            where portfolio_id = cast(:portfolio_id as bigint)
              and run_id = cast(:run_id as bigint)
            order by fill_date, instrument_id, id
            limit cast(:limit as bigint)
            """,
            {
                "portfolio_id": portfolio_id,
                "run_id": fill_run_id,
                "limit": detail_limit,
            },
        )

        position_rows = self._rows(
            """
            select
                id,
                run_id,
                portfolio_id,
                instrument_id,
                position_date,
                quantity,
                available_quantity,
                frozen_quantity,
                avg_cost,
                cost_amount,
                market_price,
                market_value,
                unrealized_pnl,
                realized_pnl,
                total_pnl,
                position_status
            from trading_paper_position
            where portfolio_id = cast(:portfolio_id as bigint)
              and run_id = cast(:run_id as bigint)
            order by position_date, instrument_id, id
            limit cast(:limit as bigint)
            """,
            {
                "portfolio_id": portfolio_id,
                "run_id": position_run_id,
                "limit": detail_limit,
            },
        )

        snapshot_rows = self._rows(
            """
            select
                id,
                run_id,
                portfolio_id,
                snapshot_date,
                cash_balance,
                market_value,
                total_equity,
                gross_exposure,
                net_exposure,
                holding_count,
                daily_pnl,
                cumulative_pnl,
                daily_return,
                cumulative_return,
                turnover_amount,
                turnover_rate
            from trading_paper_portfolio_snapshot
            where portfolio_id = cast(:portfolio_id as bigint)
              and run_id = cast(:run_id as bigint)
            order by snapshot_date, id
            limit cast(:limit as bigint)
            """,
            {
                "portfolio_id": portfolio_id,
                "run_id": snapshot_run_id,
                "limit": detail_limit,
            },
        )

        stem = (
            f"m8_paper_chain_p{portfolio_id}"
            f"_t{target_run_id}_o{order_run_id}_f{fill_run_id}"
            f"_p{position_run_id}_s{snapshot_run_id}"
        )

        json_path = output_dir / f"{stem}.json"
        md_path = output_dir / f"{stem}.md"
        target_csv_path = output_dir / f"{stem}_targets.csv"
        order_csv_path = output_dir / f"{stem}_orders.csv"
        fill_csv_path = output_dir / f"{stem}_fills.csv"
        position_csv_path = output_dir / f"{stem}_positions.csv"
        snapshot_csv_path = output_dir / f"{stem}_snapshots.csv"

        full_payload = {
            **payload,
            "exported_at": datetime.utcnow().isoformat(),
            "detail_counts": {
                "target_rows": len(target_rows),
                "order_rows": len(order_rows),
                "fill_rows": len(fill_rows),
                "position_rows": len(position_rows),
                "snapshot_rows": len(snapshot_rows),
            },
        }

        json_path.write_text(
            json.dumps(full_payload, ensure_ascii=False, indent=2, default=self._json_default),
            encoding="utf-8",
        )
        md_path.write_text(
            self._render_paper_chain_md(full_payload),
            encoding="utf-8",
        )

        self._write_csv(target_csv_path, target_rows)
        self._write_csv(order_csv_path, order_rows)
        self._write_csv(fill_csv_path, fill_rows)
        self._write_csv(position_csv_path, position_rows)
        self._write_csv(snapshot_csv_path, snapshot_rows)

        return {
            "module": "M8.2",
            "query": "export_paper_chain_report",
            "portfolio_id": portfolio_id,
            "runs": {
                "target_run_id": target_run_id,
                "order_run_id": order_run_id,
                "fill_run_id": fill_run_id,
                "position_run_id": position_run_id,
                "snapshot_run_id": snapshot_run_id,
            },
            "files": {
                "json": str(json_path),
                "markdown": str(md_path),
                "targets_csv": str(target_csv_path),
                "orders_csv": str(order_csv_path),
                "fills_csv": str(fill_csv_path),
                "positions_csv": str(position_csv_path),
                "snapshots_csv": str(snapshot_csv_path),
            },
            "detail_counts": full_payload["detail_counts"],
            "overall_status": payload.get("overall_status"),
        }

    def export_portfolio_snapshot_report(
        self,
        *,
        output_dir: Path,
        portfolio_id: int,
        snapshot_run_id: int | None = None,
        snapshot_date: date | None = None,
    ) -> dict[str, Any]:
        output_dir.mkdir(parents=True, exist_ok=True)

        payload = self.query_service.query_portfolio_snapshot(
            portfolio_id=portfolio_id,
            snapshot_run_id=snapshot_run_id,
            snapshot_date=snapshot_date,
        )

        snapshot = payload.get("snapshot") or {}
        resolved_run_id = snapshot.get("run_id") or snapshot_run_id or "latest"
        resolved_date = snapshot.get("snapshot_date") or snapshot_date or "latest"

        stem = f"m8_portfolio_snapshot_p{portfolio_id}_r{resolved_run_id}_{resolved_date}"

        json_path = output_dir / f"{stem}.json"
        md_path = output_dir / f"{stem}.md"
        csv_path = output_dir / f"{stem}.csv"

        full_payload = {
            **payload,
            "exported_at": datetime.utcnow().isoformat(),
        }

        json_path.write_text(
            json.dumps(full_payload, ensure_ascii=False, indent=2, default=self._json_default),
            encoding="utf-8",
        )
        md_path.write_text(
            self._render_snapshot_md(full_payload),
            encoding="utf-8",
        )
        self._write_csv(csv_path, [snapshot] if snapshot else [])

        return {
            "module": "M8.2",
            "query": "export_portfolio_snapshot_report",
            "portfolio_id": portfolio_id,
            "snapshot_run_id": snapshot_run_id,
            "snapshot_date": snapshot_date,
            "files": {
                "json": str(json_path),
                "markdown": str(md_path),
                "csv": str(csv_path),
            },
            "overall_status": payload.get("overall_status"),
        }

    def export_run_summary_report(
        self,
        *,
        output_dir: Path,
        run_id: int,
    ) -> dict[str, Any]:
        output_dir.mkdir(parents=True, exist_ok=True)

        payload = self.query_service.query_run(run_id=run_id)
        run = payload.get("run") or {}

        stem = f"m8_run_summary_r{run_id}"
        json_path = output_dir / f"{stem}.json"
        md_path = output_dir / f"{stem}.md"
        metrics_csv_path = output_dir / f"{stem}_metrics.csv"
        artifacts_csv_path = output_dir / f"{stem}_artifacts.csv"

        full_payload = {
            **payload,
            "exported_at": datetime.utcnow().isoformat(),
        }

        json_path.write_text(
            json.dumps(full_payload, ensure_ascii=False, indent=2, default=self._json_default),
            encoding="utf-8",
        )
        md_path.write_text(
            self._render_run_summary_md(full_payload),
            encoding="utf-8",
        )
        self._write_csv(metrics_csv_path, payload.get("metrics") or [])
        self._write_csv(artifacts_csv_path, payload.get("artifacts") or [])

        return {
            "module": "M8.2",
            "query": "export_run_summary_report",
            "run_id": run_id,
            "run_type": run.get("run_type"),
            "run_status": run.get("status"),
            "files": {
                "json": str(json_path),
                "markdown": str(md_path),
                "metrics_csv": str(metrics_csv_path),
                "artifacts_csv": str(artifacts_csv_path),
            },
            "overall_status": payload.get("overall_status"),
        }

    def export_daily_ops_report(
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

        trading_chain = latest.get("trading_chain") or {}
        risk_chain = latest.get("risk_chain") or {}

        paper_chain = None
        if all(
            trading_chain.get(k) is not None
            for k in [
                "target_run_id",
                "order_run_id",
                "fill_run_id",
                "position_run_id",
                "snapshot_run_id",
            ]
        ):
            paper_chain = self.query_service.query_paper_chain(
                portfolio_id=portfolio_id,
                target_run_id=int(trading_chain["target_run_id"]),
                order_run_id=int(trading_chain["order_run_id"]),
                fill_run_id=int(trading_chain["fill_run_id"]),
                position_run_id=int(trading_chain["position_run_id"]),
                snapshot_run_id=int(trading_chain["snapshot_run_id"]),
            )

        risk_decision = None
        target_diff = None
        if all(
            risk_chain.get(k) is not None
            for k in [
                "risk_run_id",
                "source_target_run_id",
                "adjusted_target_run_id",
            ]
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

        snapshot_date = (
            ((latest.get("details") or {}).get("latest_snapshot") or {}).get("snapshot_date")
            or "latest"
        )
        stem = f"m8_daily_ops_p{portfolio_id}_{snapshot_date}"

        json_path = output_dir / f"{stem}.json"
        md_path = output_dir / f"{stem}.md"

        full_payload = {
            "module": "M8.2",
            "query": "export_daily_ops_report",
            "portfolio_id": portfolio_id,
            "profile_code": profile_code,
            "latest_runs": latest,
            "paper_chain": paper_chain,
            "risk_decision": risk_decision,
            "target_diff": target_diff,
            "exported_at": datetime.utcnow().isoformat(),
        }

        json_path.write_text(
            json.dumps(full_payload, ensure_ascii=False, indent=2, default=self._json_default),
            encoding="utf-8",
        )
        md_path.write_text(
            self._render_daily_ops_md(full_payload),
            encoding="utf-8",
        )

        checks = {
            "latest_runs_pass": latest.get("overall_status") == "PASS",
            "paper_chain_pass": paper_chain is not None and paper_chain.get("overall_status") == "PASS",
            "risk_decision_pass": risk_decision is not None and risk_decision.get("overall_status") == "PASS",
            "target_diff_pass": target_diff is not None and target_diff.get("overall_status") == "PASS",
        }

        return {
            "module": "M8.2",
            "query": "export_daily_ops_report",
            "portfolio_id": portfolio_id,
            "profile_code": profile_code,
            "files": {
                "json": str(json_path),
                "markdown": str(md_path),
            },
            "checks": checks,
            "overall_status": "PASS" if all(checks.values()) else "WARN",
        }

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
                writer.writerow(
                    {
                        key: self._csv_cell(row.get(key))
                        for key in fields
                    }
                )

    def _render_paper_chain_md(self, payload: dict[str, Any]) -> str:
        runs = payload.get("runs") or {}
        target = payload.get("target") or {}
        order = payload.get("order") or {}
        fill = payload.get("fill") or {}
        position = payload.get("position") or {}
        snapshot = payload.get("snapshot") or {}
        checks = payload.get("checks") or {}

        return "\n".join(
            [
                "# M8.2 Paper Chain Report",
                "",
                f"- portfolio_id: `{payload.get('portfolio_id')}`",
                f"- target_run_id: `{runs.get('target_run_id')}`",
                f"- order_run_id: `{runs.get('order_run_id')}`",
                f"- fill_run_id: `{runs.get('fill_run_id')}`",
                f"- position_run_id: `{runs.get('position_run_id')}`",
                f"- snapshot_run_id: `{runs.get('snapshot_run_id')}`",
                f"- overall_status: `{payload.get('overall_status')}`",
                "",
                "## Summary",
                "",
                f"- target_count: `{target.get('target_count')}`",
                f"- order_count: `{order.get('order_count')}`",
                f"- fill_count: `{fill.get('fill_count')}`",
                f"- position_count: `{position.get('position_count')}`",
                f"- snapshot_count: `{snapshot.get('snapshot_count')}`",
                "",
                "## Portfolio",
                "",
                f"- cash_balance: `{snapshot.get('cash_balance_total')}`",
                f"- market_value: `{snapshot.get('market_value_total')}`",
                f"- total_equity: `{snapshot.get('total_equity_total')}`",
                f"- holding_count: `{snapshot.get('holding_count')}`",
                "",
                "## Checks",
                "",
                *[f"- {k}: `{v}`" for k, v in checks.items()],
                "",
            ]
        )

    def _render_snapshot_md(self, payload: dict[str, Any]) -> str:
        snapshot = payload.get("snapshot") or {}
        return "\n".join(
            [
                "# M8.2 Portfolio Snapshot Report",
                "",
                f"- portfolio_id: `{payload.get('portfolio_id')}`",
                f"- snapshot_run_id: `{payload.get('snapshot_run_id')}`",
                f"- snapshot_date: `{snapshot.get('snapshot_date')}`",
                f"- overall_status: `{payload.get('overall_status')}`",
                "",
                "## Snapshot",
                "",
                f"- cash_balance: `{snapshot.get('cash_balance')}`",
                f"- market_value: `{snapshot.get('market_value')}`",
                f"- total_equity: `{snapshot.get('total_equity')}`",
                f"- gross_exposure: `{snapshot.get('gross_exposure')}`",
                f"- net_exposure: `{snapshot.get('net_exposure')}`",
                f"- holding_count: `{snapshot.get('holding_count')}`",
                f"- daily_pnl: `{snapshot.get('daily_pnl')}`",
                f"- cumulative_pnl: `{snapshot.get('cumulative_pnl')}`",
                f"- daily_return: `{snapshot.get('daily_return')}`",
                f"- cumulative_return: `{snapshot.get('cumulative_return')}`",
                f"- turnover_amount: `{snapshot.get('turnover_amount')}`",
                f"- turnover_rate: `{snapshot.get('turnover_rate')}`",
                "",
            ]
        )

    def _render_run_summary_md(self, payload: dict[str, Any]) -> str:
        run = payload.get("run") or {}
        return "\n".join(
            [
                "# M8.2 Run Summary Report",
                "",
                f"- run_id: `{payload.get('run_id')}`",
                f"- run_type: `{run.get('run_type')}`",
                f"- run_name: `{run.get('run_name')}`",
                f"- status: `{run.get('status')}`",
                f"- trigger_type: `{run.get('trigger_type')}`",
                f"- requested_at: `{run.get('requested_at')}`",
                f"- started_at: `{run.get('started_at')}`",
                f"- ended_at: `{run.get('ended_at')}`",
                f"- overall_status: `{payload.get('overall_status')}`",
                "",
                "## Counts",
                "",
                f"- steps: `{len(payload.get('steps') or [])}`",
                f"- metrics: `{len(payload.get('metrics') or [])}`",
                f"- series_preview: `{len(payload.get('series_preview') or [])}`",
                f"- artifacts: `{len(payload.get('artifacts') or [])}`",
                "",
                "## Error",
                "",
                f"- error_message: `{run.get('error_message')}`",
                "",
            ]
        )

    def _render_daily_ops_md(self, payload: dict[str, Any]) -> str:
        latest = payload.get("latest_runs") or {}
        details = latest.get("details") or {}
        snapshot = details.get("latest_snapshot") or {}
        trading_chain = latest.get("trading_chain") or {}
        risk_chain = latest.get("risk_chain") or {}
        paper_chain = payload.get("paper_chain") or {}
        risk_decision = payload.get("risk_decision") or {}
        target_diff = payload.get("target_diff") or {}

        risk_summary = risk_decision.get("summary") or {}
        diff_summary = target_diff.get("diff_summary") or {}

        return "\n".join(
            [
                "# M8.2 Daily Ops Report",
                "",
                f"- portfolio_id: `{payload.get('portfolio_id')}`",
                f"- profile_code: `{payload.get('profile_code')}`",
                f"- snapshot_date: `{snapshot.get('snapshot_date')}`",
                f"- latest_runs_status: `{latest.get('overall_status')}`",
                f"- paper_chain_status: `{paper_chain.get('overall_status')}`",
                f"- risk_decision_status: `{risk_decision.get('overall_status')}`",
                f"- target_diff_status: `{target_diff.get('overall_status')}`",
                "",
                "## Trading Chain",
                "",
                f"- target_run_id: `{trading_chain.get('target_run_id')}`",
                f"- order_run_id: `{trading_chain.get('order_run_id')}`",
                f"- fill_run_id: `{trading_chain.get('fill_run_id')}`",
                f"- position_run_id: `{trading_chain.get('position_run_id')}`",
                f"- snapshot_run_id: `{trading_chain.get('snapshot_run_id')}`",
                "",
                "## Risk Chain",
                "",
                f"- risk_run_id: `{risk_chain.get('risk_run_id')}`",
                f"- source_target_run_id: `{risk_chain.get('source_target_run_id')}`",
                f"- adjusted_target_run_id: `{risk_chain.get('adjusted_target_run_id')}`",
                "",
                "## Snapshot",
                "",
                f"- holding_count: `{snapshot.get('holding_count')}`",
                f"- total_equity: `{snapshot.get('total_equity')}`",
                "",
                "## Risk Summary",
                "",
                f"- decision_count: `{risk_summary.get('decision_count')}`",
                f"- pass_count: `{risk_summary.get('pass_count')}`",
                f"- warn_count: `{risk_summary.get('warn_count')}`",
                f"- reject_count: `{risk_summary.get('reject_count')}`",
                f"- adjust_count: `{risk_summary.get('adjust_count')}`",
                "",
                "## Target Diff",
                "",
                f"- target_weight_delta: `{diff_summary.get('target_weight_delta')}`",
                f"- target_quantity_delta: `{diff_summary.get('target_quantity_delta')}`",
                f"- target_amount_delta: `{diff_summary.get('target_amount_delta')}`",
                "",
            ]
        )

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