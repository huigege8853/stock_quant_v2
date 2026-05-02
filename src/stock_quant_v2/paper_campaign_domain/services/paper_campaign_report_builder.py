from __future__ import annotations

import csv
import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from stock_quant_v2.paper_campaign_domain.dto.paper_campaign_models import (
    CampaignDailyResult,
    CampaignSummaryResult,
    PaperCampaignConfig,
)


class PaperCampaignReportBuilder:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.daily_dir = project_root / "artifacts" / "m6_5" / "paper_campaign_daily"
        self.summary_dir = project_root / "artifacts" / "m6_5" / "paper_campaign_summary"

    def write_daily_result(self, result: CampaignDailyResult) -> CampaignDailyResult:
        self.daily_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{result.campaign_code}_{result.trade_date.isoformat()}"
        json_path = self.daily_dir / f"{stem}.json"
        md_path = self.daily_dir / f"{stem}.md"
        sources_path = self.daily_dir / f"{stem}_sources.csv"

        payload = _to_jsonable(result)
        payload["artifact_paths"] = {
            "json": _rel(self.project_root, json_path),
            "markdown": _rel(self.project_root, md_path),
            "sources_csv": _rel(self.project_root, sources_path),
        }

        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(self._build_daily_markdown(payload), encoding="utf-8")
        self._write_sources_csv(payload, sources_path)

        return CampaignDailyResult(
            **{
                **asdict(result),
                "artifact_paths": payload["artifact_paths"],
            }
        )

    def list_daily_payloads(self, campaign_code: str) -> list[dict[str, Any]]:
        if not self.daily_dir.exists():
            return []
        payloads: list[dict[str, Any]] = []
        for path in sorted(self.daily_dir.glob(f"{campaign_code}_*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if payload.get("campaign_code") == campaign_code:
                payloads.append(payload)
        return payloads

    def successful_trade_dates(self, campaign_code: str) -> list[date]:
        dates: list[date] = []
        for payload in self.list_daily_payloads(campaign_code):
            if payload.get("status") != "SUCCESS":
                continue
            raw = payload.get("trade_date")
            if raw:
                dates.append(date.fromisoformat(str(raw)[:10]))
        return sorted(set(dates))

    def daily_artifact_exists(self, campaign_code: str, trade_date: date) -> bool:
        return (self.daily_dir / f"{campaign_code}_{trade_date.isoformat()}.json").exists()

    def write_summary(
        self,
        *,
        campaign: PaperCampaignConfig,
        daily_payloads: list[dict[str, Any]],
        snapshot_rows: list[dict[str, Any]],
    ) -> CampaignSummaryResult:
        self.summary_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{campaign.campaign_code}_summary"
        json_path = self.summary_dir / f"{stem}.json"
        md_path = self.summary_dir / f"{stem}.md"
        daily_csv = self.summary_dir / f"{campaign.campaign_code}_daily_snapshots.csv"
        trades_csv = self.summary_dir / f"{campaign.campaign_code}_trades.csv"
        action_csv = self.summary_dir / f"{campaign.campaign_code}_action_items.csv"

        completed = [p for p in daily_payloads if p.get("status") == "SUCCESS"]
        trade_dates = [date.fromisoformat(str(p["trade_date"])[:10]) for p in completed if p.get("trade_date")]
        first_trade_date = min(trade_dates) if trade_dates else None
        last_trade_date = max(trade_dates) if trade_dates else None

        first_equity = _decimal(snapshot_rows[0].get("total_equity")) if snapshot_rows else None
        final_equity = _decimal(snapshot_rows[-1].get("total_equity")) if snapshot_rows else None
        total_return = None
        if first_equity is not None and final_equity is not None and first_equity != 0:
            total_return = (final_equity - first_equity) / first_equity

        portfolio_id = None
        for p in reversed(daily_payloads):
            if p.get("portfolio_id") is not None:
                portfolio_id = int(p["portfolio_id"])
                break

        status = "COMPLETED" if len(completed) >= campaign.planned_trading_days else "ACTIVE"
        result = CampaignSummaryResult(
            campaign_code=campaign.campaign_code,
            campaign_name=campaign.campaign_name,
            status=status,
            generated_at=datetime.now(timezone.utc),
            planned_trading_days=campaign.planned_trading_days,
            completed_day_count=len(completed),
            first_trade_date=first_trade_date,
            last_trade_date=last_trade_date,
            portfolio_id=portfolio_id,
            initial_equity=first_equity,
            final_equity=final_equity,
            total_return=total_return,
            artifact_paths={
                "json": _rel(self.project_root, json_path),
                "markdown": _rel(self.project_root, md_path),
                "daily_snapshots_csv": _rel(self.project_root, daily_csv),
                "trades_csv": _rel(self.project_root, trades_csv),
                "action_items_csv": _rel(self.project_root, action_csv),
            },
        )

        payload = _to_jsonable(result)
        payload["daily_artifact_count"] = len(daily_payloads)
        payload["snapshot_row_count"] = len(snapshot_rows)
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(self._build_summary_markdown(payload), encoding="utf-8")
        self._write_snapshot_csv(snapshot_rows, daily_csv)
        self._write_placeholder_csv(trades_csv, ["note"], [["P1 summary keeps trade extraction for a later enhancement; use M7/M8 trade artifacts for details."]])
        self._write_action_items_csv(payload, action_csv)
        return result

    @staticmethod
    def _build_daily_markdown(payload: dict[str, Any]) -> str:
        signal = payload.get("signal_source") or {}
        run_ids = payload.get("extracted_run_ids") or {}
        lines = [
            f"# M6.5 Forward Paper Campaign Daily - {payload.get('campaign_code')}",
            "",
            f"- campaign_name: {payload.get('campaign_name')}",
            f"- trade_date: {payload.get('trade_date')}",
            f"- day_no: {payload.get('day_no')}",
            f"- action: {payload.get('action')}",
            f"- status: {payload.get('status')}",
            f"- reason: {payload.get('reason')}",
            f"- portfolio_id: {payload.get('portfolio_id')}",
            f"- portfolio_code: {payload.get('portfolio_code')}",
            "",
            "## Signal Source",
            "",
            f"- strategy: {payload.get('strategy_code')}:{payload.get('strategy_version_code')}",
            f"- strategy_version_id: {signal.get('strategy_version_id')}",
            f"- signal_run_id: {signal.get('signal_run_id')}",
            f"- screen_request_id: {signal.get('screen_request_id')}",
            f"- signal_as_of_date: {signal.get('as_of_date')}",
            f"- signal_effective_date: {signal.get('effective_date')}",
            "",
            "## Run Lineage",
            "",
        ]
        if run_ids:
            for key, value in sorted(run_ids.items()):
                lines.append(f"- {key}: {value}")
        else:
            lines.append("- no run ids extracted")

        lines.extend(["", "## Module Executions", ""])
        for item in payload.get("module_executions") or []:
            lines.append(f"- {item.get('step_name')}: exit_code={item.get('exit_code')}; module={item.get('module_name')}")
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _build_summary_markdown(payload: dict[str, Any]) -> str:
        tr = payload.get("total_return")
        lines = [
            f"# M6.5 Forward Paper Campaign Summary - {payload.get('campaign_code')}",
            "",
            f"- campaign_name: {payload.get('campaign_name')}",
            f"- status: {payload.get('status')}",
            f"- planned_trading_days: {payload.get('planned_trading_days')}",
            f"- completed_day_count: {payload.get('completed_day_count')}",
            f"- first_trade_date: {payload.get('first_trade_date')}",
            f"- last_trade_date: {payload.get('last_trade_date')}",
            f"- portfolio_id: {payload.get('portfolio_id')}",
            f"- initial_equity: {payload.get('initial_equity')}",
            f"- final_equity: {payload.get('final_equity')}",
            f"- total_return: {tr}",
            "",
            "## Notes",
            "",
            "- P1 summary is based on campaign daily artifacts and portfolio snapshots.",
            "- No real orders are sent. This remains paper trading only.",
        ]
        return "\n".join(lines) + "\n"

    @staticmethod
    def _write_sources_csv(payload: dict[str, Any], path: Path) -> None:
        rows = []
        for item in payload.get("module_executions") or []:
            rows.append(
                {
                    "source_type": "module_execution",
                    "source_name": item.get("step_name"),
                    "module_name": item.get("module_name"),
                    "exit_code": item.get("exit_code"),
                }
            )
        if not rows:
            rows.append({"source_type": "none", "source_name": "no_module_execution", "module_name": "", "exit_code": ""})
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["source_type", "source_name", "module_name", "exit_code"])
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _write_snapshot_csv(rows: list[dict[str, Any]], path: Path) -> None:
        fieldnames = [
            "run_id",
            "snapshot_date",
            "cash_balance",
            "market_value",
            "total_equity",
            "total_cost",
            "unrealized_pnl",
            "realized_pnl",
            "open_position_count",
            "closed_position_count",
        ]
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: _to_jsonable(row.get(k)) for k in fieldnames})

    @staticmethod
    def _write_placeholder_csv(path: Path, fieldnames: list[str], rows: list[list[str]]) -> None:
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(fieldnames)
            writer.writerows(rows)

    @staticmethod
    def _write_action_items_csv(payload: dict[str, Any], path: Path) -> None:
        rows = []
        if payload.get("status") != "COMPLETED":
            rows.append([
                "INFO",
                "campaign_not_completed",
                "Campaign has not reached planned_trading_days yet.",
                "Continue daily execution until the planned trading-day count is reached.",
            ])
        if not rows:
            rows.append(["INFO", "no_action", "No immediate action item generated by P1 summary.", "Review detailed M7/M8 artifacts."])
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["priority", "category", "item", "suggested_action"])
            writer.writerows(rows)


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {k: _to_jsonable(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    return value
