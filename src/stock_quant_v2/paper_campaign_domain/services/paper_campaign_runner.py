from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.paper_campaign_domain.dto.paper_campaign_models import (
    CampaignDailyResult,
    CampaignExecutionPlan,
    CampaignModuleExecution,
    PaperCampaignConfig,
)
from stock_quant_v2.paper_campaign_domain.services.paper_campaign_calendar_service import (
    PaperCampaignCalendarService,
)
from stock_quant_v2.paper_campaign_domain.services.paper_campaign_config_loader import (
    PaperCampaignConfigLoader,
)
from stock_quant_v2.paper_campaign_domain.services.paper_campaign_report_builder import (
    PaperCampaignReportBuilder,
)


class PaperCampaignRunner:
    """P1 orchestrator for forward paper campaigns.

    The runner deliberately does not implement trading mechanics.  It calls the
    already accepted M6/M7 entrypoints and writes campaign-level artifacts around
    those executions.
    """

    def __init__(self, *, project_root: Path, python_executable: str = sys.executable) -> None:
        self.project_root = project_root
        self.python_executable = python_executable
        self.report_builder = PaperCampaignReportBuilder(project_root=project_root)

    def run_daily(
        self,
        *,
        config_path: Path,
        trade_date: date | None = None,
        campaign_code: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        loader = PaperCampaignConfigLoader(config_path)
        if not loader.exists():
            return {
                "module": "M6.5",
                "query": "run_paper_campaign_daily",
                "overall_status": "SKIPPED",
                "reason": f"config file not found: {config_path}",
                "config_path": str(config_path),
                "results": [],
            }

        campaigns = loader.load()
        if campaign_code:
            campaigns = [c for c in campaigns if c.campaign_code == campaign_code]

        results: list[dict[str, Any]] = []
        for campaign in campaigns:
            result = self._run_one_campaign_daily(campaign=campaign, trade_date=trade_date, dry_run=dry_run)
            results.append(_jsonable(result))

        failed = [r for r in results if r.get("status") == "FAILED"]
        return {
            "module": "M6.5",
            "query": "run_paper_campaign_daily",
            "overall_status": "FAIL" if failed else "PASS",
            "config_path": str(config_path),
            "campaign_count": len(campaigns),
            "failed_count": len(failed),
            "results": results,
        }

    def build_summary(
        self,
        *,
        config_path: Path,
        campaign_code: str,
    ) -> dict[str, Any]:
        campaigns = PaperCampaignConfigLoader(config_path).load()
        matches = [c for c in campaigns if c.campaign_code == campaign_code]
        if not matches:
            raise RuntimeError(f"campaign not found in config: {campaign_code}")
        campaign = matches[0]
        daily_payloads = self.report_builder.list_daily_payloads(campaign.campaign_code)

        portfolio_id = None
        for payload in reversed(daily_payloads):
            if payload.get("portfolio_id") is not None:
                portfolio_id = int(payload["portfolio_id"])
                break

        snapshot_rows: list[dict[str, Any]] = []
        if portfolio_id is not None:
            dates = [date.fromisoformat(str(p["trade_date"])[:10]) for p in daily_payloads if p.get("trade_date")]
            start = min(dates) if dates else None
            end = max(dates) if dates else None
            with SessionLocal() as session:
                calendar = PaperCampaignCalendarService(session)
                snapshot_rows = calendar.read_snapshots(portfolio_id=portfolio_id, start_date=start, end_date=end)

        summary = self.report_builder.write_summary(
            campaign=campaign,
            daily_payloads=daily_payloads,
            snapshot_rows=snapshot_rows,
        )
        return {
            "module": "M6.5",
            "query": "build_paper_campaign_summary",
            "overall_status": "PASS",
            "summary": _jsonable(summary),
        }

    def _run_one_campaign_daily(
        self,
        *,
        campaign: PaperCampaignConfig,
        trade_date: date | None,
        dry_run: bool,
    ) -> CampaignDailyResult:
        generated_at = datetime.now(timezone.utc)
        module_executions: list[CampaignModuleExecution] = []
        extracted_run_ids: dict[str, int] = {}

        try:
            with SessionLocal() as session:
                calendar = PaperCampaignCalendarService(session)
                resolved_trade_date = trade_date or calendar.latest_completed_trade_date()
                plan = self._build_plan(calendar=calendar, campaign=campaign, trade_date=resolved_trade_date)

            if plan.action == "SKIP" or dry_run:
                artifact_paths: dict[str, str] = {}
                should_write_skip_artifact = True
                if plan.action == "SKIP" and self.report_builder.daily_artifact_exists(campaign.campaign_code, plan.trade_date):
                    stem = f"{campaign.campaign_code}_{plan.trade_date.isoformat()}"
                    artifact_paths = {
                        "json": f"artifacts/m6_5/paper_campaign_daily/{stem}.json",
                        "markdown": f"artifacts/m6_5/paper_campaign_daily/{stem}.md",
                        "sources_csv": f"artifacts/m6_5/paper_campaign_daily/{stem}_sources.csv",
                    }
                    should_write_skip_artifact = False

                result = CampaignDailyResult(
                    campaign_code=campaign.campaign_code,
                    campaign_name=campaign.campaign_name,
                    trade_date=plan.trade_date,
                    day_no=plan.day_no,
                    action="DRY_RUN" if dry_run and plan.action != "SKIP" else plan.action,
                    status="SUCCESS" if dry_run else "SKIPPED",
                    reason=plan.reason if not dry_run else f"dry run: planned action would be {plan.action}",
                    generated_at=generated_at,
                    portfolio_id=plan.portfolio_id,
                    portfolio_code=campaign.resolved_portfolio_code,
                    strategy_code=campaign.strategy_code,
                    strategy_version_code=campaign.strategy_version_code,
                    signal_source=plan.signal_source,
                    module_executions=[],
                    artifact_paths=artifact_paths,
                    extracted_run_ids={},
                )
                if should_write_skip_artifact:
                    return self.report_builder.write_daily_result(result)
                return result

            if plan.action == "M6_FIRST_CHAIN":
                execution = self._run_m6_first_chain(campaign=campaign, plan=plan)
                module_executions.append(execution)
                extracted_run_ids.update(_extract_run_ids(execution.parsed_payloads))
            elif plan.action == "M7_DAILY_REFRESH":
                execution = self._run_m7_daily_refresh(campaign=campaign, plan=plan)
                module_executions.append(execution)
                extracted_run_ids.update(_extract_run_ids(execution.parsed_payloads))
            else:
                raise RuntimeError(f"unsupported campaign action: {plan.action}")

            # M6 creates a portfolio by code. Resolve it again after execution.
            with SessionLocal() as session:
                calendar = PaperCampaignCalendarService(session)
                portfolio_id = calendar.resolve_portfolio_id(
                    portfolio_id=campaign.portfolio_id,
                    portfolio_code=campaign.resolved_portfolio_code,
                )

            result = CampaignDailyResult(
                campaign_code=campaign.campaign_code,
                campaign_name=campaign.campaign_name,
                trade_date=plan.trade_date,
                day_no=plan.day_no,
                action=plan.action,
                status="SUCCESS",
                reason=plan.reason,
                generated_at=generated_at,
                portfolio_id=portfolio_id,
                portfolio_code=campaign.resolved_portfolio_code,
                strategy_code=campaign.strategy_code,
                strategy_version_code=campaign.strategy_version_code,
                signal_source=plan.signal_source,
                module_executions=module_executions,
                artifact_paths={},
                extracted_run_ids=extracted_run_ids,
            )
            return self.report_builder.write_daily_result(result)

        except Exception as exc:
            result = CampaignDailyResult(
                campaign_code=campaign.campaign_code,
                campaign_name=campaign.campaign_name,
                trade_date=trade_date or date.today(),
                day_no=0,
                action="ERROR",
                status="FAILED",
                reason=str(exc),
                generated_at=generated_at,
                portfolio_id=campaign.portfolio_id,
                portfolio_code=campaign.resolved_portfolio_code,
                strategy_code=campaign.strategy_code,
                strategy_version_code=campaign.strategy_version_code,
                signal_source=None,
                module_executions=module_executions,
                artifact_paths={},
                extracted_run_ids=extracted_run_ids,
            )
            return self.report_builder.write_daily_result(result)

    def _build_plan(
        self,
        *,
        calendar: PaperCampaignCalendarService,
        campaign: PaperCampaignConfig,
        trade_date: date,
    ) -> CampaignExecutionPlan:
        if campaign.status != "ACTIVE":
            return CampaignExecutionPlan(campaign, trade_date, 0, "SKIP", f"campaign status is {campaign.status}")

        if campaign.run_mode == "skip":
            return CampaignExecutionPlan(campaign, trade_date, 0, "SKIP", "campaign run_mode=skip")

        if campaign.start_trade_date and trade_date < campaign.start_trade_date:
            return CampaignExecutionPlan(
                campaign,
                trade_date,
                0,
                "SKIP",
                f"trade_date is before campaign start_trade_date={campaign.start_trade_date}",
            )

        if not calendar.is_open_trade_date(trade_date):
            return CampaignExecutionPlan(campaign, trade_date, 0, "SKIP", "not an open trading day")

        if not calendar.has_daily_bar(trade_date):
            return CampaignExecutionPlan(campaign, trade_date, 0, "SKIP", "core_daily_bar has no data for trade_date")

        if self.report_builder.daily_artifact_exists(campaign.campaign_code, trade_date) and not campaign.replace_existing:
            completed = self.report_builder.successful_trade_dates(campaign.campaign_code)
            day_no = completed.index(trade_date) + 1 if trade_date in completed else len(completed)
            return CampaignExecutionPlan(campaign, trade_date, day_no, "SKIP", "daily artifact already exists")

        completed_dates = [d for d in self.report_builder.successful_trade_dates(campaign.campaign_code) if d < trade_date]
        day_no = len(completed_dates) + 1
        if day_no > campaign.planned_trading_days:
            return CampaignExecutionPlan(
                campaign,
                trade_date,
                day_no,
                "SKIP",
                f"campaign already reached planned_trading_days={campaign.planned_trading_days}",
            )

        strategy_version_id = calendar.resolve_strategy_version_id(
            campaign.strategy_code,
            campaign.strategy_version_code,
        )
        signal_source = calendar.resolve_signal_source(strategy_version_id=strategy_version_id, trade_date=trade_date)
        portfolio_id = calendar.resolve_portfolio_id(
            portfolio_id=campaign.portfolio_id,
            portfolio_code=campaign.resolved_portfolio_code,
        )

        has_previous_snapshot = False
        if portfolio_id is not None:
            has_previous_snapshot = calendar.has_previous_snapshot(portfolio_id=portfolio_id, trade_date=trade_date)

        if campaign.run_mode == "m6":
            action = "M6_FIRST_CHAIN"
        elif campaign.run_mode == "m7":
            action = "M7_DAILY_REFRESH"
        else:
            action = "M7_DAILY_REFRESH" if day_no > 1 and portfolio_id is not None and has_previous_snapshot else "M6_FIRST_CHAIN"

        if action == "M7_DAILY_REFRESH" and portfolio_id is None:
            raise RuntimeError(
                f"campaign {campaign.campaign_code} cannot run M7 because portfolio does not exist yet; use M6 first"
            )

        return CampaignExecutionPlan(
            campaign=campaign,
            trade_date=trade_date,
            day_no=day_no,
            action=action,
            reason="first campaign trading day" if action == "M6_FIRST_CHAIN" else "campaign continuation trading day",
            portfolio_id=portfolio_id,
            signal_source=signal_source,
        )

    def _run_m6_first_chain(self, *, campaign: PaperCampaignConfig, plan: CampaignExecutionPlan) -> CampaignModuleExecution:
        if plan.signal_source is None:
            raise RuntimeError("M6 campaign execution requires resolved signal source")
        env = {
            "M6_PAPER_ACCOUNT_CODE": campaign.resolved_account_code,
            "M6_PAPER_PORTFOLIO_CODE": campaign.resolved_portfolio_code,
            "M6_STRATEGY_VERSION_ID": str(plan.signal_source.strategy_version_id),
            "M6_EXECUTION_ASSUMPTION_PROFILE_ID": str(campaign.extra.get("execution_assumption_profile_id", 1)),
            "M6_SOURCE_SIGNAL_RUN_ID": str(plan.signal_source.signal_run_id),
            "M6_SOURCE_SCREEN_REQUEST_ID": str(plan.signal_source.screen_request_id or ""),
            "M6_AS_OF_DATE": plan.signal_source.as_of_date.isoformat(),
            "M6_EFFECTIVE_DATE": plan.trade_date.isoformat(),
            "M6_START_DATE": plan.trade_date.isoformat(),
            "M6_TARGET_DATE": plan.trade_date.isoformat(),
            "M6_TRADE_DATE": plan.trade_date.isoformat(),
            "M6_TARGET_COUNT": str(campaign.target_count),
            "M6_INITIAL_CASH": str(campaign.initial_cash),
        }
        return self._run_module(
            step_name="m6_first_chain",
            module_name="stock_quant_v2.scripts.bootstrap_m6_paper_trading_first_chain",
            extra_args=[],
            extra_env=env,
        )

    def _run_m7_daily_refresh(self, *, campaign: PaperCampaignConfig, plan: CampaignExecutionPlan) -> CampaignModuleExecution:
        if plan.signal_source is None:
            raise RuntimeError("M7 campaign execution requires resolved signal source")
        if plan.portfolio_id is None:
            raise RuntimeError("M7 campaign execution requires portfolio_id")

        args = [
            "--portfolio-id",
            str(plan.portfolio_id),
            "--effective-date",
            plan.trade_date.isoformat(),
            "--source-signal-run-id",
            str(plan.signal_source.signal_run_id),
        ]
        if plan.signal_source.screen_request_id is not None:
            args.extend(["--source-screen-request-id", str(plan.signal_source.screen_request_id)])
        if campaign.replace_existing:
            args.append("--replace-existing")

        env = {
            "M7_PORTFOLIO_CODE": campaign.resolved_portfolio_code,
            "M7_TARGET_COUNT": str(campaign.target_count),
        }
        return self._run_module(
            step_name="m7_daily_refresh",
            module_name="stock_quant_v2.scripts.bootstrap_m7_daily_refresh_chain",
            extra_args=args,
            extra_env=env,
        )

    def _run_module(
        self,
        *,
        step_name: str,
        module_name: str,
        extra_args: Sequence[str],
        extra_env: dict[str, str],
    ) -> CampaignModuleExecution:
        env = os.environ.copy()
        env.update(extra_env)
        env.setdefault("PYTHONUNBUFFERED", "1")
        src_dir = self.project_root / "src"
        old_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{src_dir}{os.pathsep}{old_pythonpath}" if old_pythonpath else str(src_dir)

        command = [self.python_executable, "-u", "-m", module_name, *extra_args]
        started_at = datetime.now(timezone.utc)
        completed = subprocess.run(
            command,
            cwd=self.project_root,
            env=env,
            capture_output=True,
            text=True,
        )
        finished_at = datetime.now(timezone.utc)
        stdout = (completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")
        payloads = _parse_payloads(stdout)
        if completed.returncode != 0:
            raise RuntimeError(
                f"campaign module failed: step={step_name}, module={module_name}, "
                f"exit_code={completed.returncode}\n{_tail(stdout)}"
            )
        return CampaignModuleExecution(
            step_name=step_name,
            module_name=module_name,
            command=command,
            exit_code=int(completed.returncode),
            started_at=started_at,
            finished_at=finished_at,
            stdout_tail=_tail(stdout),
            parsed_payloads=payloads,
        )


def _tail(text: str, *, max_chars: int = 8000) -> str:
    text = text or ""
    return text[-max_chars:]


def _parse_payloads(text: str) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for block in _balanced_blocks(text):
        obj = None
        try:
            obj = json.loads(block)
        except Exception:
            try:
                obj = ast.literal_eval(block)
            except Exception:
                obj = None
        if isinstance(obj, dict):
            payloads.append(obj)
    return payloads


def _balanced_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    depth = 0
    start: int | None = None
    in_string: str | None = None
    escape = False

    for i, ch in enumerate(text or ""):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == in_string:
                in_string = None
            continue

        if ch in {'"', "'"}:
            in_string = ch
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    blocks.append(text[start : i + 1])
                    start = None
    return blocks


def _extract_run_ids(payloads: list[dict[str, Any]]) -> dict[str, int]:
    keys = {
        "target_run_id",
        "order_run_id",
        "fill_run_id",
        "position_run_id",
        "snapshot_run_id",
        "position_snapshot_run_id",
        "ledger_run_id",
        "run_id",
        "source_signal_run_id",
        "source_screen_request_id",
    }
    result: dict[str, int] = {}
    for payload in payloads:
        _collect_run_ids(payload, result, keys)
    return result


def _collect_run_ids(value: Any, result: dict[str, int], keys: set[str], prefix: str = "") -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            key = str(k)
            out_key = f"{prefix}.{key}" if prefix else key
            if key in keys and v is not None:
                try:
                    result[out_key] = int(v)
                except Exception:
                    pass
            if isinstance(v, (dict, list)):
                _collect_run_ids(v, result, keys, out_key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            if isinstance(item, (dict, list)):
                _collect_run_ids(item, result, keys, f"{prefix}[{index}]")


def _jsonable(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value) if not isinstance(value, (str, int, float, bool, type(None))) else value
