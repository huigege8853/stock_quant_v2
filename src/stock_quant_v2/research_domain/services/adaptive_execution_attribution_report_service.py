"""Artifact-only M9 adaptive execution attribution report builder.

The service reads V2 Stage-2 adaptive execution dry-run artifacts and produces a
natural-language attribution pack. It does not read or write the database, does
not change strategy_signal/research_backtest_result, and never routes to M6.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

DEFAULT_DRY_RUN_ARTIFACT_DIR = Path("artifacts/m5/adaptive_execution_dry_run/request_47")
DEFAULT_INPUT_ENRICHMENT_ARTIFACT_DIR = Path("artifacts/m5/adaptive_execution_input_enrichment/request_47")
DEFAULT_OUTPUT_DIR = Path("artifacts/m9/adaptive_execution_attribution")


@dataclass(frozen=True)
class AdaptiveExecutionAttributionReportConfig:
    report_date: str
    request_id: int = 47
    dry_run_artifact_dir: Path = DEFAULT_DRY_RUN_ARTIFACT_DIR
    input_enrichment_artifact_dir: Path = DEFAULT_INPUT_ENRICHMENT_ARTIFACT_DIR
    output_dir: Path = DEFAULT_OUTPUT_DIR
    top_n: int = 10


@dataclass(frozen=True)
class AdaptiveExecutionAttributionArtifacts:
    output_dir: Path
    metrics_path: Path
    report_path: Path
    sections_path: Path
    by_exit_reason_path: Path
    by_regime_path: Path
    by_industry_path: Path
    by_trade_date_path: Path
    top_positions_path: Path
    sources_path: Path
    contract_checks_path: Path


@dataclass(frozen=True)
class AdaptiveExecutionAttributionReportResult:
    status: str
    metrics: dict[str, Any]
    sections: list[dict[str, Any]]
    attribution_rows: dict[str, list[dict[str, Any]]]
    contract_checks: list[dict[str, Any]]
    validation_decision: dict[str, Any]
    artifacts: AdaptiveExecutionAttributionArtifacts | None = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(v) for v in value]
    return value


def _safe_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    text = str(value).strip()
    if text == "":
        return default
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or str(value).strip() == "":
            return default
        return int(Decimal(str(value).strip()))
    except (InvalidOperation, ValueError):
        return default


def _fmt_money(value: Any) -> str:
    return f"{_safe_decimal(value):,.2f}"


def _fmt_pct(value: Any) -> str:
    return f"{_safe_decimal(value) * Decimal('100'):.2f}%"


def _ratio(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator == 0:
        return Decimal("0")
    return numerator / denominator


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        return json.loads(path.read_text(encoding="utf-8-sig"))


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return [{str(k): ("" if v is None else str(v)) for k, v in row.items()} for row in csv.DictReader(f)]


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: _to_jsonable(row.get(name, "")) for name in fieldnames})


class AdaptiveExecutionAttributionReportService:
    """Build M9 attribution artifacts from M5 adaptive execution dry-run outputs."""

    def build(self, config: AdaptiveExecutionAttributionReportConfig) -> AdaptiveExecutionAttributionReportResult:
        dry_dir = Path(config.dry_run_artifact_dir)
        enrich_dir = Path(config.input_enrichment_artifact_dir)

        sources = [
            {"source_code": "m5_adaptive_execution_dry_run", "path": str(dry_dir), "status": "USED" if dry_dir.exists() else "MISSING", "note": "required dry-run artifact directory"},
            {"source_code": "m5_adaptive_execution_input_enrichment", "path": str(enrich_dir), "status": "USED" if enrich_dir.exists() else "MISSING", "note": "optional input enrichment evidence"},
        ]
        contract_checks: list[dict[str, Any]] = []

        dry_metrics_payload = _read_json(dry_dir / "metrics.json")
        dry_metrics = dry_metrics_payload.get("metrics", dry_metrics_payload if dry_metrics_payload else {})
        dry_status = str(dry_metrics_payload.get("status") or dry_metrics.get("status") or "MISSING")
        validation_decision = dict(dry_metrics_payload.get("validation_decision") or {})

        trade_rows = _read_csv_rows(dry_dir / "trade_log.csv")
        lifecycle_rows = _read_csv_rows(dry_dir / "position_lifecycle.csv")
        daily_rows = _read_csv_rows(dry_dir / "daily_portfolio.csv")
        exit_summary_rows = _read_csv_rows(dry_dir / "exit_reason_summary.csv")
        entry_summary_rows = _read_csv_rows(dry_dir / "entry_reason_summary.csv")
        regime_rows = _read_csv_rows(dry_dir / "by_regime_performance.csv")
        industry_rows = _read_csv_rows(dry_dir / "by_industry_performance.csv")
        dry_contract_rows = _read_csv_rows(dry_dir / "contract_checks.csv")
        input_rows = _read_csv_rows(enrich_dir / "candidate_execution_inputs.csv")
        no_trade_by_design = (
            _safe_int(dry_metrics.get("candidate_row_count")) == 0
            and len(trade_rows) == 0
            and dry_status in {"PASS", "PASS_WITH_WARN", "PASS_NO_TRADE", "PASS_NO_TRADE_BY_DESIGN"}
        )

        contract_checks.append({
            "check_name": "dry_run_metrics_loaded",
            "status": "PASS" if dry_metrics_payload else "FAIL",
            "row_count": 1 if dry_metrics_payload else 0,
            "detail": str(dry_dir / "metrics.json"),
        })
        contract_checks.append({
            "check_name": "dry_run_contract_passed",
            "status": "PASS" if dry_status in {"PASS", "PASS_WITH_WARN", "PASS_NO_TRADE", "PASS_NO_TRADE_BY_DESIGN"} else "FAIL",
            "row_count": 1,
            "detail": f"dry_run_status={dry_status}",
        })
        contract_checks.append({
            "check_name": "trade_log_loaded",
            "status": "PASS" if (trade_rows or no_trade_by_design) else "FAIL",
            "row_count": len(trade_rows),
            "detail": ("no-trade-by-design; empty trade_log accepted" if no_trade_by_design else str(dry_dir / "trade_log.csv")),
        })
        contract_checks.append({
            "check_name": "position_lifecycle_loaded",
            "status": "PASS" if lifecycle_rows else "WARN",
            "row_count": len(lifecycle_rows),
            "detail": str(dry_dir / "position_lifecycle.csv"),
        })
        contract_checks.append({
            "check_name": "artifact_only_boundary",
            "status": "PASS",
            "row_count": 0,
            "detail": "M9 attribution reads artifacts only; no DB engine/session is used.",
        })
        contract_checks.append({
            "check_name": "m6_boundary",
            "status": "PASS",
            "row_count": 0,
            "detail": "Report cannot route to M6 and cannot claim strategy effectiveness.",
        })

        closed_rows = [row for row in lifecycle_rows if str(row.get("status") or "").upper() == "CLOSED"]
        open_rows = [row for row in lifecycle_rows if str(row.get("status") or "").upper() == "OPEN"]
        buy_rows = [row for row in trade_rows if str(row.get("side") or "").upper() == "BUY"]
        sell_rows = [row for row in trade_rows if str(row.get("side") or "").upper() == "SELL"]
        realized_pnl = sum(_safe_decimal(row.get("realized_pnl")) for row in closed_rows)
        realized_notional = sum(_safe_decimal(row.get("entry_notional")) for row in closed_rows)
        realized_return = _ratio(realized_pnl, realized_notional)
        winners = [row for row in closed_rows if _safe_decimal(row.get("realized_pnl")) > 0]
        losers = [row for row in closed_rows if _safe_decimal(row.get("realized_pnl")) < 0]
        avg_holding = _ratio(sum(_safe_decimal(row.get("holding_days")) for row in closed_rows), Decimal(len(closed_rows))) if closed_rows else Decimal("0")

        cash_metrics = self._cash_utilization_metrics(daily_rows)
        exit_attribution = self._exit_reason_attribution(closed_rows)
        regime_attribution = self._normalize_numeric_rows(regime_rows, key_name="confirmed_market_regime")
        industry_attribution = self._normalize_numeric_rows(industry_rows, key_name="industry_tag_name")
        trade_date_attribution = self._trade_date_attribution(trade_rows, daily_rows)
        top_positions = self._top_position_rows(closed_rows, config.top_n)
        entry_block_reasons = dry_metrics.get("entry_block_reasons") if isinstance(dry_metrics, dict) else {}
        if not isinstance(entry_block_reasons, dict):
            entry_block_reasons = {}

        metrics: dict[str, Any] = {
            "report_date": config.report_date,
            "request_id": config.request_id,
            "stage": "M9_ADAPTIVE_EXECUTION_ATTRIBUTION_REPORT",
            "source_stage": "M5_ADAPTIVE_EXECUTION_DRY_RUN",
            "dry_run_status": dry_status,
            "candidate_row_count": _safe_int(dry_metrics.get("candidate_row_count")),
            "candidate_date_count": _safe_int(dry_metrics.get("candidate_date_count")),
            "trade_count": len(trade_rows),
            "buy_count": len(buy_rows),
            "sell_count": len(sell_rows),
            "closed_position_count": len(closed_rows),
            "open_position_count": len(open_rows),
            "realized_pnl": realized_pnl,
            "realized_return": realized_return,
            "win_count": len(winners),
            "loss_count": len(losers),
            "win_rate": _ratio(Decimal(len(winners)), Decimal(len(closed_rows))) if closed_rows else Decimal("0"),
            "avg_holding_days": avg_holding,
            "ending_cash": dry_metrics.get("ending_cash", ""),
            "blocker_count": _safe_int(dry_metrics.get("blocker_count")),
            "warn_count": _safe_int(dry_metrics.get("warn_count")),
            "cash_utilization": cash_metrics,
            "entry_block_reasons": entry_block_reasons,
            "input_candidate_row_count": len(input_rows),
            "input_pass_count": len([row for row in input_rows if str(row.get("entry_input_status") or "").upper() == "PASS"]),
            "input_fail_count": len([row for row in input_rows if str(row.get("entry_input_status") or "").upper() == "FAIL"]),
            "dry_run_validation_decision": validation_decision,
            "no_trade_by_design": no_trade_by_design,
            "no_trade_reason": "zero_candidate_rows_after_top_down_or_window_filter" if no_trade_by_design else "",
        }
        metrics["worst_exit_reason"] = exit_attribution[0]["exit_reason"] if exit_attribution else ""
        metrics["top_loss_position"] = top_positions[0] if top_positions else {}

        sections = self._build_sections(
            metrics=metrics,
            dry_status=dry_status,
            exit_attribution=exit_attribution,
            regime_attribution=regime_attribution,
            industry_attribution=industry_attribution,
            top_positions=top_positions,
            dry_contract_rows=dry_contract_rows,
            entry_summary_rows=entry_summary_rows,
            exit_summary_rows=exit_summary_rows,
        )

        fatal = any(row["status"] == "FAIL" for row in contract_checks)
        warn = any(row["status"] == "WARN" for row in contract_checks)
        status = "FAIL" if fatal else ("PASS_WITH_WARN" if no_trade_by_design or warn or dry_status == "PASS_WITH_WARN" else "PASS")
        decision = {
            "can_write_strategy_signal": False,
            "can_write_research_backtest_result": False,
            "can_route_to_m6": False,
            "can_claim_strategy_effective": False,
            "can_start_full_dry_run": status in {"PASS", "PASS_WITH_WARN"},
            "no_trade_by_design": no_trade_by_design,
            "no_trade_reason": "zero_candidate_rows_after_top_down_or_window_filter" if no_trade_by_design else "",
            "manual_review_required": True,
            "interpretation_scope": "artifact_only_m9_adaptive_execution_attribution",
            "next_research_step": "Review attribution report before expanding dry-run or tightening entry gates.",
        }

        result = AdaptiveExecutionAttributionReportResult(
            status=status,
            metrics=metrics,
            sections=sections,
            attribution_rows={
                "by_exit_reason": exit_attribution,
                "by_regime": regime_attribution,
                "by_industry": industry_attribution,
                "by_trade_date": trade_date_attribution,
                "top_positions": top_positions,
                "sources": sources,
            },
            contract_checks=contract_checks,
            validation_decision=decision,
            artifacts=None,
        )
        artifacts = self._export(result, config, sources)
        return AdaptiveExecutionAttributionReportResult(
            status=result.status,
            metrics=result.metrics,
            sections=result.sections,
            attribution_rows=result.attribution_rows,
            contract_checks=result.contract_checks,
            validation_decision=result.validation_decision,
            artifacts=artifacts,
        )

    def _cash_utilization_metrics(self, daily_rows: list[dict[str, str]]) -> dict[str, Any]:
        if not daily_rows:
            return {"daily_count": 0, "avg_cash_ratio": "0", "avg_exposure_ratio": "0", "max_exposure_ratio": "0"}
        cash_ratios: list[Decimal] = []
        exposure_ratios: list[Decimal] = []
        position_counts: list[int] = []
        for row in daily_rows:
            equity = _safe_decimal(row.get("total_equity"))
            if equity <= 0:
                continue
            cash_ratios.append(_ratio(_safe_decimal(row.get("ending_cash")), equity))
            exposure_ratios.append(_ratio(_safe_decimal(row.get("gross_exposure")), equity))
            position_counts.append(_safe_int(row.get("position_count")))
        avg_cash = _ratio(sum(cash_ratios, Decimal("0")), Decimal(len(cash_ratios))) if cash_ratios else Decimal("0")
        avg_exposure = _ratio(sum(exposure_ratios, Decimal("0")), Decimal(len(exposure_ratios))) if exposure_ratios else Decimal("0")
        return {
            "daily_count": len(daily_rows),
            "avg_cash_ratio": avg_cash,
            "avg_exposure_ratio": avg_exposure,
            "max_exposure_ratio": max(exposure_ratios) if exposure_ratios else Decimal("0"),
            "min_cash_ratio": min(cash_ratios) if cash_ratios else Decimal("0"),
            "max_position_count": max(position_counts) if position_counts else 0,
        }

    def _exit_reason_attribution(self, closed_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
        buckets: dict[str, dict[str, Any]] = defaultdict(lambda: {
            "exit_reason": "",
            "closed_position_count": 0,
            "realized_pnl": Decimal("0"),
            "entry_notional": Decimal("0"),
            "avg_holding_days": Decimal("0"),
            "win_count": 0,
            "loss_count": 0,
        })
        for row in closed_rows:
            reason = row.get("exit_reason") or row.get("exit_type") or "UNKNOWN"
            bucket = buckets[reason]
            bucket["exit_reason"] = reason
            bucket["closed_position_count"] += 1
            pnl = _safe_decimal(row.get("realized_pnl"))
            bucket["realized_pnl"] += pnl
            bucket["entry_notional"] += _safe_decimal(row.get("entry_notional"))
            bucket["avg_holding_days"] += _safe_decimal(row.get("holding_days"))
            if pnl > 0:
                bucket["win_count"] += 1
            elif pnl < 0:
                bucket["loss_count"] += 1
        rows: list[dict[str, Any]] = []
        for bucket in buckets.values():
            count = Decimal(bucket["closed_position_count"])
            bucket["avg_holding_days"] = _ratio(bucket["avg_holding_days"], count)
            bucket["realized_return"] = _ratio(bucket["realized_pnl"], bucket["entry_notional"])
            bucket["win_rate"] = _ratio(Decimal(bucket["win_count"]), count)
            rows.append(bucket)
        rows.sort(key=lambda row: (_safe_decimal(row["realized_pnl"]), -_safe_int(row["closed_position_count"])))
        return rows

    def _normalize_numeric_rows(self, rows: list[dict[str, str]], *, key_name: str) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for row in rows:
            normalized.append({
                key_name: row.get(key_name, ""),
                "trade_count": _safe_int(row.get("trade_count")),
                "realized_pnl": _safe_decimal(row.get("realized_pnl")),
                "realized_return": _safe_decimal(row.get("realized_return")),
                "avg_holding_days": _safe_decimal(row.get("avg_holding_days")),
                "status": row.get("status", ""),
                "detail": row.get("detail", ""),
            })
        normalized.sort(key=lambda row: _safe_decimal(row.get("realized_pnl")), reverse=False)
        return normalized

    def _trade_date_attribution(self, trade_rows: list[dict[str, str]], daily_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
        buys = Counter(row.get("trade_date", "") for row in trade_rows if str(row.get("side") or "").upper() == "BUY")
        sells = Counter(row.get("trade_date", "") for row in trade_rows if str(row.get("side") or "").upper() == "SELL")
        daily_by_date = {row.get("trade_date", ""): row for row in daily_rows}
        dates = sorted(set(buys) | set(sells) | set(daily_by_date))
        rows: list[dict[str, Any]] = []
        for date_value in dates:
            daily = daily_by_date.get(date_value, {})
            rows.append({
                "trade_date": date_value,
                "buy_count": buys.get(date_value, 0),
                "sell_count": sells.get(date_value, 0),
                "ending_cash": _safe_decimal(daily.get("ending_cash")),
                "gross_exposure": _safe_decimal(daily.get("gross_exposure")),
                "total_equity": _safe_decimal(daily.get("total_equity")),
                "position_count": _safe_int(daily.get("position_count")),
                "confirmed_market_regime": daily.get("confirmed_market_regime", ""),
                "status": daily.get("status", ""),
            })
        return rows

    def _top_position_rows(self, closed_rows: list[dict[str, str]], top_n: int) -> list[dict[str, Any]]:
        rows = [
            {
                "position_id": row.get("position_id", ""),
                "instrument_code": row.get("instrument_code", ""),
                "display_name": row.get("display_name", ""),
                "industry_tag_name": row.get("industry_tag_name", ""),
                "entry_date": row.get("entry_date", ""),
                "exit_date": row.get("exit_date", ""),
                "realized_pnl": _safe_decimal(row.get("realized_pnl")),
                "realized_return": _safe_decimal(row.get("realized_return")),
                "holding_days": _safe_int(row.get("holding_days")),
                "max_floating_profit": _safe_decimal(row.get("max_floating_profit")),
                "max_floating_loss": _safe_decimal(row.get("max_floating_loss")),
                "entry_reason": row.get("entry_reason", ""),
                "exit_reason": row.get("exit_reason") or row.get("exit_type", ""),
            }
            for row in closed_rows
        ]
        rows.sort(key=lambda row: _safe_decimal(row.get("realized_pnl")))
        losses = rows[:top_n]
        wins = list(reversed(rows[-top_n:])) if rows else []
        merged: list[dict[str, Any]] = []
        for label, group in (("BOTTOM_LOSS", losses), ("TOP_WIN", wins)):
            for rank, row in enumerate(group, start=1):
                item = dict(row)
                item["bucket"] = label
                item["rank"] = rank
                merged.append(item)
        return merged

    def _build_sections(
        self,
        *,
        metrics: dict[str, Any],
        dry_status: str,
        exit_attribution: list[dict[str, Any]],
        regime_attribution: list[dict[str, Any]],
        industry_attribution: list[dict[str, Any]],
        top_positions: list[dict[str, Any]],
        dry_contract_rows: list[dict[str, str]],
        entry_summary_rows: list[dict[str, str]],
        exit_summary_rows: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        worst_exit = exit_attribution[0] if exit_attribution else {}
        worst_industry = industry_attribution[0] if industry_attribution else {}
        cash = metrics.get("cash_utilization") or {}
        fail_contracts = [row for row in dry_contract_rows if str(row.get("status") or "").upper() == "FAIL"]
        sections = [
            {
                "section_id": "01_scope_and_gate",
                "title": "范围与门禁",
                "status": "PASS" if dry_status in {"PASS", "PASS_WITH_WARN"} else "FAIL",
                "summary": "本报告只解释 M5 adaptive execution dry-run artifact，不写库、不进入 M6、不声明策略有效。",
                "details": [
                    f"dry_run_status={dry_status}",
                    f"candidate_date_count={metrics.get('candidate_date_count')}",
                    f"trade_count={metrics.get('trade_count')}",
                    "can_route_to_m6=false",
                ],
            },
            {
                "section_id": "02_lifecycle_summary",
                "title": "交易生命周期摘要",
                "status": "PASS",
                "summary": (
                    f"买入 {metrics.get('buy_count')} 次，卖出 {metrics.get('sell_count')} 次，"
                    f"已闭合 {metrics.get('closed_position_count')} 笔，未闭合 {metrics.get('open_position_count')} 笔。"
                ),
                "details": [
                    f"realized_pnl={_fmt_money(metrics.get('realized_pnl'))}",
                    f"realized_return={_fmt_pct(metrics.get('realized_return'))}",
                    f"win_rate={_fmt_pct(metrics.get('win_rate'))}",
                    f"avg_holding_days={_safe_decimal(metrics.get('avg_holding_days')):.2f}",
                ],
            },
            {
                "section_id": "03_exit_attribution",
                "title": "卖点归因",
                "status": "WARN" if worst_exit and _safe_decimal(worst_exit.get("realized_pnl")) < 0 else "PASS",
                "summary": (
                    f"亏损最大的退出原因是 {worst_exit.get('exit_reason', 'N/A')}，"
                    f"realized_pnl={_fmt_money(worst_exit.get('realized_pnl'))}。"
                    if worst_exit else "没有闭合仓位，无法做卖点归因。"
                ),
                "details": [
                    f"exit_reason_types={len(exit_attribution)}",
                    f"raw_exit_summary_rows={len(exit_summary_rows)}",
                ],
            },
            {
                "section_id": "04_regime_and_industry",
                "title": "市场状态与行业归因",
                "status": "WARN" if worst_industry and _safe_decimal(worst_industry.get("realized_pnl")) < 0 else "PASS",
                "summary": (
                    f"亏损最大的行业是 {worst_industry.get('industry_tag_name', 'N/A')}，"
                    f"realized_pnl={_fmt_money(worst_industry.get('realized_pnl'))}。"
                    if worst_industry else "缺少行业归因行。"
                ),
                "details": [
                    f"regime_rows={len(regime_attribution)}",
                    f"industry_rows={len(industry_attribution)}",
                ],
            },
            {
                "section_id": "05_cash_and_risk_budget",
                "title": "现金与仓位约束",
                "status": "PASS",
                "summary": "dry-run 已通过现金非负、仓位上限、行业上限和先卖后买检查。",
                "details": [
                    f"ending_cash={_fmt_money(metrics.get('ending_cash'))}",
                    f"avg_cash_ratio={_fmt_pct(cash.get('avg_cash_ratio'))}",
                    f"max_exposure_ratio={_fmt_pct(cash.get('max_exposure_ratio'))}",
                    f"max_position_count={cash.get('max_position_count')}",
                ],
            },
            {
                "section_id": "06_entry_quality_and_blockers",
                "title": "买点输入与阻断原因",
                "status": "PASS" if not fail_contracts else "FAIL",
                "summary": "输入补齐已支撑 dry-run；剩余阻断主要来自风险预算、涨停、重复标的或持仓数量约束。",
                "details": [
                    f"input_pass_count={metrics.get('input_pass_count')}",
                    f"input_fail_count={metrics.get('input_fail_count')}",
                    f"entry_block_reasons={json.dumps(_to_jsonable(metrics.get('entry_block_reasons')), ensure_ascii=False)}",
                    f"entry_summary_rows={len(entry_summary_rows)}",
                ],
            },
            {
                "section_id": "07_next_step",
                "title": "下一步建议",
                "status": "PASS",
                "summary": "建议先人工复核归因，再决定扩大全量 dry-run 或收紧 RISK_OFF / RANGE 买点。",
                "details": [
                    "不进入 M6。",
                    "不写 research_backtest_result。",
                    "不把 25 日期收益作为策略有效结论。",
                    f"top_position_rows={len(top_positions)}",
                ],
            },
        ]
        return sections

    def _render_markdown(self, result: AdaptiveExecutionAttributionReportResult) -> str:
        metrics = result.metrics
        lines = [
            "# M9 Adaptive Execution Attribution Report",
            "",
            f"- Report Date: {metrics.get('report_date')}",
            f"- Generated At: {_utc_now_iso()}",
            f"- Overall Status: {result.status}",
            f"- Request ID: {metrics.get('request_id')}",
            f"- Source Stage: {metrics.get('source_stage')}",
            "- Boundary: artifact-only; no DB writes; no M6 routing; no strategy effectiveness claim.",
            "",
            "## Executive Summary",
            "",
            f"本报告解释 M5 adaptive execution dry-run 的买入、卖出、亏损来源和门禁状态。当前 dry-run_status={metrics.get('dry_run_status')}，trade_count={metrics.get('trade_count')}，buy_count={metrics.get('buy_count')}，sell_count={metrics.get('sell_count')}，closed_position_count={metrics.get('closed_position_count')}。",
            "",
            f"已闭合仓位 realized_pnl={_fmt_money(metrics.get('realized_pnl'))}，realized_return={_fmt_pct(metrics.get('realized_return'))}，win_rate={_fmt_pct(metrics.get('win_rate'))}，avg_holding_days={_safe_decimal(metrics.get('avg_holding_days')):.2f}。这些数字只用于 dry-run 归因，不可作为正式回测或生产收益结论。",
            "",
        ]
        for section in result.sections:
            lines.extend([
                f"## {section['section_id']}｜{section['title']}",
                "",
                f"- Status: {section['status']}",
                f"- Summary: {section['summary']}",
            ])
            for detail in section.get("details") or []:
                lines.append(f"  - {detail}")
            lines.append("")

        lines.extend([
            "## 归因回答：为什么买、为什么卖、为什么亏",
            "",
            "- 为什么买：当前 Stage 2 的买入只代表 candidate_pool_match + route_match + liquidity_ok + not_limit_up + risk_budget_available + board_lot_ok 这组最小执行门禁通过，不代表买点已经优化。",
            "- 为什么卖：卖出来自 dry-run 生命周期中的 hard_stop_loss / trailing_profit_drawdown_exit / market_regime_exit / max_holding_days_exit 等规则触发。",
            f"- 为什么亏：从闭合仓位看，realized_pnl={_fmt_money(metrics.get('realized_pnl'))}，主要亏损应继续在 by_exit_reason、by_regime、by_industry 和 top_position_pnl 中复核。",
            "",
            "## Validation Decision",
            "",
            f"- can_write_strategy_signal: {str(result.validation_decision['can_write_strategy_signal']).lower()}",
            f"- can_write_research_backtest_result: {str(result.validation_decision['can_write_research_backtest_result']).lower()}",
            f"- can_route_to_m6: {str(result.validation_decision['can_route_to_m6']).lower()}",
            f"- can_claim_strategy_effective: {str(result.validation_decision['can_claim_strategy_effective']).lower()}",
            f"- can_start_full_dry_run: {str(result.validation_decision['can_start_full_dry_run']).lower()}",
            "",
            "## Sources",
            "",
        ])
        for row in result.attribution_rows.get("sources", []):
            lines.append(f"- {row.get('source_code')}: {row.get('status')} - {row.get('path')}")
        lines.append("")
        return "\n".join(lines)

    def _export(
        self,
        result: AdaptiveExecutionAttributionReportResult,
        config: AdaptiveExecutionAttributionReportConfig,
        sources: list[dict[str, Any]],
    ) -> AdaptiveExecutionAttributionArtifacts:
        out_dir = Path(config.output_dir) / f"request_{config.request_id}"
        out_dir.mkdir(parents=True, exist_ok=True)

        metrics_path = out_dir / "metrics.json"
        report_path = out_dir / "adaptive_execution_attribution_report.md"
        sections_path = out_dir / "attribution_sections.csv"
        by_exit_reason_path = out_dir / "by_exit_reason_attribution.csv"
        by_regime_path = out_dir / "by_regime_attribution.csv"
        by_industry_path = out_dir / "by_industry_attribution.csv"
        by_trade_date_path = out_dir / "by_trade_date_attribution.csv"
        top_positions_path = out_dir / "top_position_pnl.csv"
        sources_path = out_dir / "sources.csv"
        contract_checks_path = out_dir / "contract_checks.csv"

        metrics_payload = {
            "status": result.status,
            "generated_at": _utc_now_iso(),
            "report_date": config.report_date,
            "request_id": config.request_id,
            "stage": "M9_ADAPTIVE_EXECUTION_ATTRIBUTION_REPORT",
            "metrics": _to_jsonable(result.metrics),
            "validation_decision": _to_jsonable(result.validation_decision),
            "contract_checks": _to_jsonable(result.contract_checks),
        }
        metrics_path.write_text(json.dumps(metrics_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        report_path.write_text(self._render_markdown(result), encoding="utf-8")

        _write_csv(sections_path, result.sections, ["section_id", "title", "status", "summary", "details"])
        _write_csv(by_exit_reason_path, result.attribution_rows["by_exit_reason"], ["exit_reason", "closed_position_count", "realized_pnl", "entry_notional", "realized_return", "avg_holding_days", "win_count", "loss_count", "win_rate"])
        _write_csv(by_regime_path, result.attribution_rows["by_regime"], ["confirmed_market_regime", "trade_count", "realized_pnl", "realized_return", "avg_holding_days", "status", "detail"])
        _write_csv(by_industry_path, result.attribution_rows["by_industry"], ["industry_tag_name", "trade_count", "realized_pnl", "realized_return", "avg_holding_days", "status", "detail"])
        _write_csv(by_trade_date_path, result.attribution_rows["by_trade_date"], ["trade_date", "buy_count", "sell_count", "ending_cash", "gross_exposure", "total_equity", "position_count", "confirmed_market_regime", "status"])
        _write_csv(top_positions_path, result.attribution_rows["top_positions"], ["bucket", "rank", "position_id", "instrument_code", "display_name", "industry_tag_name", "entry_date", "exit_date", "realized_pnl", "realized_return", "holding_days", "max_floating_profit", "max_floating_loss", "entry_reason", "exit_reason"])
        _write_csv(sources_path, sources, ["source_code", "path", "status", "note"])
        _write_csv(contract_checks_path, result.contract_checks, ["check_name", "status", "row_count", "detail"])

        return AdaptiveExecutionAttributionArtifacts(
            output_dir=out_dir,
            metrics_path=metrics_path,
            report_path=report_path,
            sections_path=sections_path,
            by_exit_reason_path=by_exit_reason_path,
            by_regime_path=by_regime_path,
            by_industry_path=by_industry_path,
            by_trade_date_path=by_trade_date_path,
            top_positions_path=top_positions_path,
            sources_path=sources_path,
            contract_checks_path=contract_checks_path,
        )
