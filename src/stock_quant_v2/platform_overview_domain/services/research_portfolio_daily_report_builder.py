from __future__ import annotations

import csv
import json
import math
import re
import shutil
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_jsonable(value):
    """Convert Python/runtime objects into JSON-safe values."""
    from dataclasses import asdict, is_dataclass
    from datetime import date, datetime
    from decimal import Decimal
    from pathlib import Path

    if value is None:
        return None

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, Path):
        return str(value)

    if is_dataclass(value):
        return _to_jsonable(asdict(value))

    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(v) for v in value]

    return value


def _safe_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        text = str(value).strip()
        if text == "":
            return None
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _fmt_money(value: Any) -> str:
    number = _safe_decimal(value)
    if number is None:
        return "N/A"
    return f"{number:,.2f}"


def _fmt_pct(value: Any, signed: bool = False) -> str:
    number = _safe_decimal(value)
    if number is None:
        return "N/A"
    # Most project metrics are stored as decimal ratio, e.g. 0.13 = 13%.
    pct = number * Decimal("100")
    sign = "+" if signed and pct > 0 else ""
    return f"{sign}{pct:.2f}%"


def _fmt_int(value: Any) -> str:
    number = _safe_decimal(value)
    if number is None:
        return "N/A"
    return f"{int(number):,}"




_EXCHANGE_CODE_NORMALIZE_MAP = {
    "1": "SSE",
    "2": "SZSE",
    "SSE": "SSE",
    "SZSE": "SZSE",
    "BSE": "BSE",
    "SH": "SSE",
    "SZ": "SZSE",
    "BJ": "BSE",
    "XSHG": "SSE",
    "XSHE": "SZSE",
    "XBSE": "BSE",
}


def _normalize_exchange_code_value(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    return _EXCHANGE_CODE_NORMALIZE_MAP.get(text.upper(), text.upper())


def _fmt_signed_money(value: Any) -> str:
    number = _safe_decimal(value)
    if number is None:
        return "N/A"
    sign = "+" if number > 0 else ""
    return f"{sign}{number:,.2f}"


def _fmt_qty(value: Any) -> str:
    number = _safe_decimal(value)
    if number is None:
        return "N/A"
    return f"{int(number):,}"


def _fmt_metric(value: Any, digits: int = 4) -> str:
    number = _safe_decimal(value)
    if number is None:
        return "N/A"
    return f"{number:.{digits}f}"


def _decimal_gt(value: Any, threshold: str) -> bool:
    number = _safe_decimal(value)
    if number is None:
        return False
    return number > Decimal(threshold)


def _decimal_lt(value: Any, threshold: str) -> bool:
    number = _safe_decimal(value)
    if number is None:
        return False
    return number < Decimal(threshold)


def _ratio(numerator: Any, denominator: Any) -> Decimal | None:
    n = _safe_decimal(numerator)
    d = _safe_decimal(denominator)
    if n is None or d in (None, Decimal("0")):
        return None
    return n / d


def _is_warnish_status(status: Any) -> bool:
    if status is None:
        return False
    return str(status).upper() not in {"OK", "PASS", "SUCCESS"}


def _is_st_or_special_treatment(row: dict[str, Any]) -> bool:
    name = str(row.get("stock_name") or row.get("display_name") or row.get("display_label") or "")
    code = str(row.get("stock_code") or row.get("display_code") or "")
    text = f"{code} {name}".upper()
    return "*ST" in text or " ST" in text or text.startswith("ST") or "退" in text or "退市" in text


def _pick(mapping: dict[str, Any] | None, names: Iterable[str], default: Any = None) -> Any:
    if not mapping:
        return default
    lower = {str(k).lower(): v for k, v in mapping.items()}
    for name in names:
        if name in mapping:
            return mapping[name]
        key = name.lower()
        if key in lower:
            return lower[key]
    return default


def _read_json(path: Path | None) -> dict[str, Any]:
    if not path or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def _read_csv_rows(path: Path | None, limit: int | None = None) -> list[dict[str, str]]:
    if not path or not path.exists():
        return []
    try:
        fh = path.open("r", encoding="utf-8-sig", newline="")
    except Exception:
        return []
    rows: list[dict[str, str]] = []
    with fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append({str(k): ("" if v is None else str(v)) for k, v in row.items()})
            if limit is not None and len(rows) >= limit:
                break
    return rows


@dataclass
class ReportSource:
    source_code: str
    path: str
    status: str = "USED"
    note: str = ""


@dataclass
class ReportSection:
    section_id: str
    title: str
    status: str
    summary: str
    details: list[str] = field(default_factory=list)


@dataclass
class ResearchPortfolioDailyReport:
    report_date: str
    generated_at: str
    scope: str
    overall_status: str
    sections: list[ReportSection]
    selected_stocks: list[dict[str, Any]]
    position_summary_rows: list[dict[str, Any]]
    action_items: list[dict[str, Any]]
    sources: list[ReportSource]
    facts: dict[str, Any]


class ResearchPortfolioDailyReportBuilder:
    """Build a research / portfolio natural-language daily report from artifacts.

    This report is intentionally read-only. It does not change DB state and does
    not generate trading signals. It complements the existing M9.1.1 platform
    overview report with an investor-facing view: market context, strategy,
    selected stocks, backtest, paper portfolio, cash/exposure and risk.
    """

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)
        self.sources: list[ReportSource] = []

    def build_report(self, report_date: str) -> ResearchPortfolioDailyReport:
        self.sources = []

        m3_path = self._latest_artifact([
            f"artifacts/m3/m9_bridge/*_{report_date}.json",
            "artifacts/m3/m9_bridge/*.json",
        ], "m3_bridge")
        m4_path = self._latest_artifact([
            f"artifacts/m4/m9_bridge/*_{report_date}.json",
            "artifacts/m4/m9_bridge/*.json",
        ], "m4_bridge")
        m5_path = self._latest_artifact([
            f"artifacts/m5/m9_bridge/*_{report_date}.json",
            "artifacts/m5/m9_bridge/*.json",
        ], "m5_bridge")
        daily_ops_path = self._latest_artifact([
            f"artifacts/m8/daily_ops/*_{report_date}.json",
            "artifacts/m8/daily_ops/*.json",
        ], "m8_daily_ops")
        paper_chain_path = self._latest_artifact([
            "artifacts/m8/paper_chain/*.json",
        ], "m8_paper_chain")
        paper_targets_path = self._latest_artifact([
            "artifacts/m8/paper_chain/*_targets.csv",
        ], "m8_paper_targets")
        paper_positions_path = self._latest_artifact([
            "artifacts/m8/paper_chain/*_positions.csv",
        ], "m8_paper_positions")
        portfolio_snapshot_path = self._latest_artifact([
            "artifacts/m8/portfolio_snapshot/*.json",
        ], "m8_portfolio_snapshot")
        portfolio_snapshot_csv_path = self._latest_artifact([
            "artifacts/m8/portfolio_snapshot/*.csv",
        ], "m8_portfolio_snapshot_csv")
        risk_path = self._latest_artifact([
            "artifacts/m8/risk/*.json",
        ], "m8_risk")
        alert_path = self._latest_artifact([
            f"artifacts/m8/alert/*_{report_date}.json",
            "artifacts/m8/alert/*.json",
        ], "m8_alert")
        m6_5_daily_paths = self._matching_artifacts([
            f"artifacts/m6_5/paper_campaign_daily/*_{report_date}.json",
            "artifacts/m6_5/paper_campaign_daily/*.json",
        ], "m6_5_paper_campaign_daily")
        m6_5_summary_paths = self._matching_artifacts([
            "artifacts/m6_5/paper_campaign_summary/*.json",
        ], "m6_5_paper_campaign_summary")

        m3 = _read_json(m3_path)
        m4 = _read_json(m4_path)
        m5 = _read_json(m5_path)
        daily_ops = _read_json(daily_ops_path)
        paper_chain = _read_json(paper_chain_path)
        portfolio_snapshot = _read_json(portfolio_snapshot_path)
        risk = _read_json(risk_path)
        alert = _read_json(alert_path)
        m6_5_daily_payloads = [_read_json(path) for path in m6_5_daily_paths]
        m6_5_summary_payloads = [_read_json(path) for path in m6_5_summary_paths]

        selected_rows = _read_csv_rows(paper_targets_path)
        if not selected_rows:
            selected_rows = self._load_selected_stock_rows_from_db(daily_ops, paper_chain, report_date)
        position_rows = _read_csv_rows(paper_positions_path)
        snapshot_csv_rows = _read_csv_rows(portfolio_snapshot_csv_path)

        backtest_fact = self._extract_backtest(m5, daily_ops)
        strategy_fact = self._extract_strategy(m4, backtest_fact)
        portfolio_fact = self._extract_portfolio(daily_ops, paper_chain, portfolio_snapshot, snapshot_csv_rows)
        risk_fact = self._extract_risk(risk, daily_ops, alert)
        market_fact = self._extract_market(m3)
        db_market_fact = self._try_extract_market_from_db()
        selected_stock_rows = self._normalize_selected_stock_rows(selected_rows)
        selected_fact = self._extract_selected_stocks(selected_stock_rows, paper_chain)
        position_fact = self._extract_positions(position_rows, portfolio_fact)
        campaign_fact = self._extract_paper_campaigns(m6_5_daily_payloads, m6_5_summary_payloads)

        facts = {
            "report_date": report_date,
            "generated_at": _utc_now_iso(),
            "market": market_fact,
            "db_market": db_market_fact,
            "strategy": strategy_fact,
            "backtest": backtest_fact,
            "selected": selected_fact,
            "portfolio": portfolio_fact,
            "positions": position_fact,
            "risk": risk_fact,
            "paper_campaigns": campaign_fact,
        }
        facts["review_flags"] = self._derive_review_flags(facts)
        facts["status_layers"] = self._derive_status_layers(facts)

        sections = [
            self._section_cover_and_watermark(facts),
            self._section_exec_summary(facts),
            self._section_market(facts),
            self._section_strategy(facts),
            self._section_selected(facts),
            self._section_portfolio(facts),
            self._section_pnl_turnover(facts),
            self._section_backtest(facts),
            self._section_risk(facts),
            self._section_paper_campaigns(facts),
            self._section_anomalies_and_actions(facts),
            self._section_conclusion(facts),
            self._section_sources(),
            self._section_appendix(facts),
        ]
        action_items = self._build_action_items(facts, sections)
        overall_status = self._overall_status(sections)

        return ResearchPortfolioDailyReport(
            report_date=report_date,
            generated_at=_utc_now_iso(),
            scope="M9.1.1-B Professional Research & Portfolio Daily Report P1",
            overall_status=overall_status,
            sections=sections,
            selected_stocks=selected_stock_rows,
            position_summary_rows=self._build_position_summary_rows(position_rows, portfolio_fact),
            action_items=action_items,
            sources=self.sources,
            facts=facts,
        )

    def _latest_artifact(self, patterns: list[str], source_code: str) -> Path | None:
        """Return the latest file for the first pattern that has matches.

        Patterns are ordered by preference. This matters because report-date
        exact matches should beat older fallback files even if a fallback file
        has a newer filesystem mtime after unzip/copy.
        """
        matches = self._matching_artifacts(patterns, source_code, allow_many=False)
        return matches[0] if matches else None

    def _artifact_sort_key(self, path: Path) -> tuple[Any, ...]:
        """Return a stable recency key for artifact selection.

        Do not rely on lexicographic filename order for run-based artifacts:
        r698 sorts after r1504 as text, which can make M9 reports read stale
        M5 bridge files. Prefer explicit JSON run ids / generated_at, then
        filename run ids, then filesystem mtime as a final fallback.
        """
        payload: dict[str, Any] = {}
        if path.suffix.lower() == ".json":
            payload = _read_json(path)

        run_candidates = [
            payload.get("latest_run_id"),
            payload.get("run_id"),
            payload.get("source_signal_run_id"),
        ]
        latest_result = payload.get("latest_result")
        if isinstance(latest_result, dict):
            run_candidates.append(latest_result.get("run_id"))

        filename_match = re.search(r"_r(\d+)(?:_|\.)", path.name)
        if filename_match:
            run_candidates.append(filename_match.group(1))

        run_id = 0
        for value in run_candidates:
            try:
                if value is not None and str(value).strip() != "":
                    run_id = max(run_id, int(str(value).strip()))
            except ValueError:
                continue

        generated_at = str(payload.get("generated_at") or "")
        report_date = str(payload.get("report_date") or "")
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        return (report_date, run_id, generated_at, mtime, path.name)

    def _matching_artifacts(self, patterns: list[str], source_code: str, allow_many: bool = True) -> list[Path]:
        selected_pattern = ""
        candidates: list[Path] = []
        for pattern in patterns:
            pattern_candidates = [candidate for candidate in self.repo_root.glob(pattern) if candidate.is_file()]
            if pattern_candidates:
                selected_pattern = pattern
                candidates = pattern_candidates
                break
        if not candidates:
            self.sources.append(ReportSource(source_code, "", "MISSING", "no matching artifact"))
            return []
        candidates.sort(key=self._artifact_sort_key, reverse=True)
        selected = candidates if allow_many else candidates[:1]
        for path in selected:
            self.sources.append(
                ReportSource(
                    source_code,
                    str(path.relative_to(self.repo_root)),
                    "USED",
                    f"matching artifact from pattern: {selected_pattern}",
                )
            )
        return selected

    def _extract_paper_campaigns(
        self,
        daily_payloads: list[dict[str, Any]],
        summary_payloads: list[dict[str, Any]],
    ) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        for payload in daily_payloads:
            if not payload:
                continue
            if isinstance(payload.get("results"), list):
                for item in payload.get("results") or []:
                    if isinstance(item, dict):
                        rows.append(dict(item))
            elif payload.get("campaign_code"):
                rows.append(dict(payload))

        normalized: list[dict[str, Any]] = []
        for row in rows:
            normalized.append({
                "campaign_code": row.get("campaign_code"),
                "campaign_name": row.get("campaign_name"),
                "trade_date": row.get("trade_date"),
                "day_no": row.get("day_no"),
                "action": row.get("action"),
                "status": row.get("status"),
                "reason": row.get("reason"),
                "portfolio_id": row.get("portfolio_id"),
                "portfolio_code": row.get("portfolio_code"),
                "strategy_code": row.get("strategy_code"),
                "strategy_version_code": row.get("strategy_version_code"),
                "signal_source": row.get("signal_source"),
                "module_execution_count": len(row.get("module_executions") or []),
                "extracted_run_ids": row.get("extracted_run_ids") or {},
                "artifact_paths": row.get("artifact_paths") or {},
            })

        failed = [row for row in normalized if str(row.get("status") or "").upper() in {"FAIL", "FAILED", "ERROR"}]
        executed = [row for row in normalized if str(row.get("action") or "").upper() in {"M6_FIRST_CHAIN", "M7_DAILY_REFRESH"}]
        skipped = [row for row in normalized if str(row.get("action") or "").upper() == "SKIP"]
        latest = normalized[0] if normalized else {}
        return {
            "status": "WARN" if failed else ("OK" if normalized else "MISSING"),
            "campaign_count": len(normalized),
            "executed_count": len(executed),
            "skipped_count": len(skipped),
            "failed_count": len(failed),
            "latest": latest,
            "rows": normalized,
            "summary_count": len([p for p in summary_payloads if p]),
        }

    def _extract_strategy(self, m4: dict[str, Any], backtest: dict[str, Any] | None = None) -> dict[str, Any]:
        strategies = m4.get("strategies") or []
        versions = m4.get("versions") or []
        schemas = m4.get("schemas") or []
        backtest = backtest or {}
        backtest_strategy_code = backtest.get("strategy_code")
        backtest_version_code = backtest.get("strategy_version_code")

        strategy = next(
            (item for item in strategies if item.get("strategy_code") == backtest_strategy_code),
            strategies[0] if strategies else {},
        )
        version = next(
            (v for v in versions if v.get("version_code") == backtest_version_code),
            next((v for v in versions if v.get("is_current") is True), versions[0] if versions else {}),
        )
        schema = next(
            (
                item
                for item in schemas
                if item.get("strategy_version_id") == backtest.get("strategy_version_id")
                or item.get("version_code") == backtest_version_code
            ),
            schemas[0] if schemas else {},
        )
        example = schema.get("example_payload_json") or {}
        return {
            "status": m4.get("status") or ("OK" if strategies else "MISSING"),
            "strategy_code": backtest_strategy_code or strategy.get("strategy_code"),
            "strategy_name": backtest.get("strategy_name") or strategy.get("strategy_name"),
            "strategy_type": backtest.get("strategy_type") or strategy.get("strategy_type"),
            "engine_type": backtest.get("engine_type") or strategy.get("engine_type"),
            "version_code": backtest_version_code or version.get("version_code"),
            "strategy_version_id": backtest.get("strategy_version_id") or version.get("id"),
            "source_signal_run_id": backtest.get("source_signal_run_id"),
            "implementation_ref": version.get("implementation_ref"),
            "output_contract_version": version.get("output_contract_version"),
            "params": example,
            "top_n": example.get("top_n"),
            "min_score": example.get("min_score"),
            "weights": example.get("weights"),
            "signal_total_rows": m4.get("signal_total_rows"),
            "signal_latest_as_of_date": m4.get("signal_latest_as_of_date"),
            "signal_latest_effective_date": m4.get("signal_latest_effective_date"),
            "current_true_rows": m4.get("current_true_rows") or [],
            "human_summary": m4.get("human_summary"),
            "strategy_source": "m5_latest_backtest" if backtest_strategy_code or backtest_version_code else "m4_bridge",
        }

    def _extract_backtest(self, m5: dict[str, Any], daily_ops: dict[str, Any]) -> dict[str, Any]:
        latest = m5.get("latest_result") or (daily_ops.get("m5_backtest") or {})
        result_summary = latest.get("result_summary") or {}
        quality_warning_codes = m5.get("quality_warning_codes") or result_summary.get("quality_warning_codes") or []
        if not isinstance(quality_warning_codes, list):
            quality_warning_codes = [str(quality_warning_codes)]
        warnings = m5.get("warnings") or []
        preview_warning_stats = m5.get("preview_warning_stats") or {}
        execution_mode = m5.get("execution_mode") or daily_ops.get("m5_backtest", {}).get("execution_mode") or result_summary.get("execution_mode")
        stage = m5.get("execution_stage") or result_summary.get("stage")
        return {
            "status": m5.get("status") or daily_ops.get("m5_backtest", {}).get("overall_status"),
            "run_id": m5.get("latest_run_id") or latest.get("run_id"),
            "backtest_request_id": m5.get("backtest_request_id") or latest.get("backtest_request_id"),
            "strategy_code": m5.get("strategy_code"),
            "strategy_name": m5.get("strategy_name"),
            "strategy_type": m5.get("strategy_type"),
            "engine_type": m5.get("engine_type"),
            "strategy_version_id": m5.get("strategy_version_id"),
            "strategy_version_code": m5.get("strategy_version_code"),
            "source_signal_run_id": m5.get("source_signal_run_id") or result_summary.get("source_signal_run_id"),
            "execution_mode": execution_mode,
            "start_date": latest.get("start_date"),
            "end_date": latest.get("end_date"),
            "trading_days": latest.get("trading_days"),
            "initial_cash": latest.get("initial_cash"),
            "final_equity": latest.get("final_equity"),
            "total_return": latest.get("total_return"),
            "annual_return": latest.get("annual_return"),
            "max_drawdown": latest.get("max_drawdown"),
            "sharpe_ratio": latest.get("sharpe_ratio"),
            "volatility": latest.get("volatility"),
            "order_count": latest.get("order_count"),
            "trade_count": latest.get("trade_count"),
            "real_execution": daily_ops.get("m5_backtest", {}).get("real_execution"),
            "controlled_research_execution": m5.get("checks", {}).get("controlled_research_execution"),
            "internal_one_day_hold_preview": m5.get("checks", {}).get("internal_one_day_hold_preview")
                or execution_mode == "INTERNAL_ONE_DAY_HOLD_PREVIEW"
                or "INTERNAL_ONE_DAY_HOLD_PREVIEW" in quality_warning_codes,
            "quality_warning_codes": quality_warning_codes,
            "warnings": warnings,
            "preview_warning_stats": preview_warning_stats,
            "performance_claim_allowed": m5.get("performance_claim_allowed"),
            "message": daily_ops.get("m5_backtest", {}).get("message") or m5.get("human_summary"),
            "stage": stage,
            "source_signal_run_id": result_summary.get("source_signal_run_id"),
        }

    def _extract_portfolio(
        self,
        daily_ops: dict[str, Any],
        paper_chain: dict[str, Any],
        portfolio_snapshot: dict[str, Any],
        snapshot_csv_rows: list[dict[str, str]],
    ) -> dict[str, Any]:
        paper = daily_ops.get("paper_chain") or {}
        snapshot_from_daily = (paper.get("snapshot") or {}) if isinstance(paper, dict) else {}
        snapshot_from_json = portfolio_snapshot.get("snapshot") or portfolio_snapshot
        snapshot_from_csv = snapshot_csv_rows[0] if snapshot_csv_rows else {}
        snapshot = snapshot_from_json or snapshot_from_daily or snapshot_from_csv
        order = paper.get("order") or paper_chain.get("order") or {}
        fill = paper.get("fill") or paper_chain.get("fill") or {}
        position = paper.get("position") or paper_chain.get("position") or {}
        target = paper.get("target") or paper_chain.get("target") or {}
        runs = paper.get("runs") or paper_chain.get("runs") or {}
        total_equity = _pick(snapshot, ["total_equity", "total_equity_total"])
        cash = _pick(snapshot, ["cash_balance", "cash_balance_total"])
        market_value = _pick(snapshot, ["market_value", "market_value_total"])
        gross_exposure = _pick(snapshot, ["gross_exposure", "gross_exposure_total"])
        exposure_ratio = None
        total_equity_d = _safe_decimal(total_equity)
        gross_d = _safe_decimal(gross_exposure or market_value)
        if total_equity_d and total_equity_d != 0 and gross_d is not None:
            exposure_ratio = gross_d / total_equity_d
        return {
            "status": paper.get("overall_status") or portfolio_snapshot.get("overall_status"),
            "runs": runs,
            "snapshot_date": _pick(snapshot, ["snapshot_date", "max_snapshot_date", "min_snapshot_date"]),
            "cash_balance": cash,
            "market_value": market_value,
            "total_equity": total_equity,
            "gross_exposure": gross_exposure,
            "net_exposure": _pick(snapshot, ["net_exposure", "net_exposure_total"]),
            "holding_count": _pick(snapshot, ["holding_count"]),
            "daily_pnl": _pick(snapshot, ["daily_pnl", "daily_pnl_total"]),
            "cumulative_pnl": _pick(snapshot, ["cumulative_pnl", "cumulative_pnl_total"]),
            "daily_return": _pick(snapshot, ["daily_return"]),
            "cumulative_return": _pick(snapshot, ["cumulative_return"]),
            "turnover_amount": _pick(snapshot, ["turnover_amount"]),
            "turnover_rate": _pick(snapshot, ["turnover_rate"]),
            "target_count": _pick(target, ["target_count", "linked_target_count"]),
            "order_count": _pick(order, ["order_count"]),
            "fill_count": _pick(fill, ["fill_count"]),
            "position_count": _pick(position, ["position_count"]),
            "open_position_count": _pick(position, ["open_position_count"]),
            "closed_position_count": _pick(position, ["closed_position_count"]),
            "exposure_ratio": str(exposure_ratio) if exposure_ratio is not None else None,
        }

    def _extract_risk(self, risk: dict[str, Any], daily_ops: dict[str, Any], alert: dict[str, Any]) -> dict[str, Any]:
        risk_daily = daily_ops.get("risk_decision") or {}
        summary = risk.get("summary") or risk_daily.get("summary") or risk_daily
        return {
            "status": risk.get("overall_status") or risk_daily.get("overall_status"),
            "decision_count": summary.get("decision_count"),
            "pass_count": summary.get("pass_count"),
            "warn_count": summary.get("warn_count"),
            "reject_count": summary.get("reject_count"),
            "adjust_count": summary.get("adjust_count"),
            "min_decision_date": summary.get("min_decision_date"),
            "max_decision_date": summary.get("max_decision_date"),
            "reason_summary": risk.get("reason_summary") or risk_daily.get("reason_summary") or [],
            "alert_status": alert.get("overall_status") or alert.get("alert_status"),
            "highest_alert_level": alert.get("highest_level"),
            "alert_counts": alert.get("alert_counts") or {},
            "alerts": alert.get("alerts") or [],
        }

    def _extract_market(self, m3: dict[str, Any]) -> dict[str, Any]:
        snapshot_counts = m3.get("snapshot_counts") or {}
        readiness = m3.get("readiness_metrics") or {}
        return {
            "status": m3.get("status"),
            "latest_run_id": m3.get("latest_run_id"),
            "latest_run_name": (m3.get("latest_success_run") or {}).get("run_name"),
            "daily_bar_rows": snapshot_counts.get("daily_bar_rows"),
            "adjust_factor_rows": snapshot_counts.get("adjust_factor_rows"),
            "indicator_rows": snapshot_counts.get("indicator_rows"),
            "feature_rows": snapshot_counts.get("feature_rows"),
            "label_rows": snapshot_counts.get("label_rows"),
            "total_bar_rows": readiness.get("total_bar_rows"),
            "missing_forward_factor_rows": readiness.get("missing_forward_factor_rows"),
            "adj_close_ready": readiness.get("adj_close_ready"),
            "ret_20d_ready": readiness.get("ret_20d_ready"),
            "human_summary": m3.get("human_summary"),
        }

    def _try_extract_market_from_db(self) -> dict[str, Any]:
        """Best-effort market context from DB, with no hard dependency.

        The project has evolved table names across M2/M3. This method tries a
        small set of known stable candidates and returns WARN when unavailable.
        """
        try:
            from sqlalchemy import text  # type: ignore
        except Exception as exc:
            return {"status": "SKIPPED", "message": f"sqlalchemy unavailable: {exc}"}

        session_factory = None
        for module_name in (
            "stock_quant_v2.db.session",
            "stock_quant_v2.database.session",
        ):
            try:
                module = __import__(module_name, fromlist=["SessionLocal"])
                session_factory = getattr(module, "SessionLocal")
                break
            except Exception:
                continue
        if session_factory is None:
            return {"status": "SKIPPED", "message": "SessionLocal not found"}

        session = None
        try:
            session = session_factory()
            table_names = self._discover_table_names(session, text)
            breadth = self._read_latest_row(session, text, table_names, [
                "core_market_breadth", "market_breadth", "market_breadth_snapshot"
            ])
            index_bar = self._read_latest_row(session, text, table_names, [
                "core_market_index_bar", "market_index_bar"
            ])
            daily_bar_summary = self._read_daily_bar_summary(session, text, table_names)
            return {
                "status": "OK" if (breadth or index_bar or daily_bar_summary) else "WARN",
                "breadth": breadth,
                "index_bar": index_bar,
                "daily_bar_summary": daily_bar_summary,
            }
        except Exception as exc:
            return {"status": "WARN", "message": f"DB market snapshot unavailable: {type(exc).__name__}: {exc}"}
        finally:
            if session is not None:
                try:
                    session.close()
                except Exception:
                    pass

    def _discover_table_names(self, session: Any, text: Any) -> set[str]:
        names: set[str] = set()
        try:
            rows = session.execute(text(
                "select table_name from information_schema.tables "
                "where table_schema not in ('pg_catalog', 'information_schema')"
            )).fetchall()
            names.update(str(row[0]) for row in rows)
        except Exception:
            pass
        # Keep known candidates even when information_schema is unavailable.
        names.update({
            "core_market_breadth", "market_breadth", "market_breadth_snapshot",
            "core_market_index_bar", "market_index_bar",
            "core_daily_bar", "daily_bar",
        })
        return names

    def _read_latest_row(self, session: Any, text: Any, table_names: set[str], candidates: list[str]) -> dict[str, Any]:
        for table in candidates:
            if table not in table_names:
                continue
            try:
                rows = session.execute(text(f"select * from {table} order by trade_date desc limit 1")).mappings().all()
                if rows:
                    return {str(k): _to_jsonable(v) for k, v in dict(rows[0]).items()}
            except Exception:
                continue
        return {}

    def _read_daily_bar_summary(self, session: Any, text: Any, table_names: set[str]) -> dict[str, Any]:
        table = next((t for t in ["core_daily_bar", "daily_bar"] if t in table_names), None)
        if not table:
            return {}
        try:
            latest_row = session.execute(text(f"select max(trade_date) as trade_date from {table}")).mappings().first()
            latest_date = latest_row["trade_date"] if latest_row else None
            if latest_date is None:
                return {}
            count_row = session.execute(
                text(f"select count(*) as cnt from {table} where trade_date = :trade_date"),
                {"trade_date": latest_date},
            ).mappings().first()
            sample_rows = session.execute(
                text(f"select * from {table} where trade_date = :trade_date limit 6000"),
                {"trade_date": latest_date},
            ).mappings().all()
            returns = self._compute_close_returns([dict(r) for r in sample_rows])
            summary = {
                "latest_trade_date": str(latest_date),
                "instrument_count": int(count_row["cnt"]) if count_row else None,
            }
            summary.update(returns)
            return summary
        except Exception:
            return {}

    def _compute_close_returns(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        if not rows:
            return {}
        close_keys = ["close", "close_price", "close_px"]
        prev_keys = ["prev_close", "pre_close", "previous_close", "preclose", "last_close"]
        returns: list[float] = []
        for row in rows:
            close = _safe_decimal(_pick(row, close_keys))
            prev = _safe_decimal(_pick(row, prev_keys))
            if close is None or prev is None or prev == 0:
                continue
            try:
                returns.append(float((close / prev) - Decimal("1")))
            except Exception:
                continue
        if not returns:
            return {}
        up = sum(1 for x in returns if x > 0)
        down = sum(1 for x in returns if x < 0)
        flat = len(returns) - up - down
        avg = sum(returns) / len(returns)
        returns_sorted = sorted(returns)
        mid = len(returns_sorted) // 2
        median = returns_sorted[mid] if len(returns_sorted) % 2 else (returns_sorted[mid - 1] + returns_sorted[mid]) / 2
        return {
            "return_sample_count": len(returns),
            "up_count": up,
            "down_count": down,
            "flat_count": flat,
            "up_ratio": up / len(returns),
            "avg_return": avg,
            "median_return": median,
        }

    def _extract_selected_stocks(self, rows: list[dict[str, Any]], paper_chain: dict[str, Any]) -> dict[str, Any]:
        target_summary = paper_chain.get("target") or {}
        missing_identity_rows = [
            row for row in rows
            if row.get("identity_status") != "OK"
        ]
        source = rows[0].get("row_source") if rows else None
        return {
            "row_count": len(rows),
            "target_count": target_summary.get("target_count") or len(rows) or None,
            "source": source or ("artifact" if rows else "missing"),
            "top_rows": rows[:15],
            "all_rows": rows,
            "identity_status": "OK" if not missing_identity_rows else "WARN",
            "identity_missing_count": len(missing_identity_rows),
            "identity_missing_instrument_ids": [
                row.get("instrument_id") for row in missing_identity_rows[:50]
            ],
        }

    def _load_selected_stock_rows_from_db(
        self,
        daily_ops: dict[str, Any],
        paper_chain: dict[str, Any],
        report_date: str,
    ) -> list[dict[str, Any]]:
        """Best-effort selected-stock fallback from DB when M8 targets CSV is absent.

        DailyRun uses the lightweight M8 entrypoint, so detailed
        artifacts/m8/paper_chain/*_targets.csv may not exist. M9-B still needs
        the target stock list for the daily portfolio report, therefore this
        method performs a read-only lookup against trading_paper_target_position.
        It never writes to DB and it soft-fails to an empty list.
        """
        try:
            from sqlalchemy import text  # type: ignore
            from stock_quant_v2.db.session import SessionLocal  # type: ignore
        except Exception as exc:
            self.sources.append(ReportSource(
                "m9_selected_stocks_db_fallback",
                "",
                "MISSING",
                f"DB fallback unavailable: {type(exc).__name__}: {exc}",
            ))
            return []

        session = None
        try:
            session = SessionLocal()
            table_names = self._discover_table_names(session, text)
            table = self._first_existing_table(table_names, [
                "trading_paper_target_position",
                "paper_target_position",
                "paper_target_positions",
                "trading_target_position",
            ])
            if not table:
                self.sources.append(ReportSource(
                    "m9_selected_stocks_db_fallback",
                    "",
                    "MISSING",
                    "target position table not found",
                ))
                return []

            columns = self._read_table_columns(session, text, table)
            if not columns:
                self.sources.append(ReportSource(
                    "m9_selected_stocks_db_fallback",
                    table,
                    "MISSING",
                    "target position table columns unavailable",
                ))
                return []

            target_run_id = self._resolve_target_run_id(daily_ops, paper_chain)
            rows = self._query_target_rows(session, text, table, columns, target_run_id, report_date)
            if not rows:
                note = "no selected stock rows found"
                if target_run_id is not None:
                    note += f" for target_run_id={target_run_id}"
                self.sources.append(ReportSource(
                    "m9_selected_stocks_db_fallback",
                    table,
                    "MISSING",
                    note,
                ))
                return []

            normalized_rows = []
            for row in rows:
                item = {str(k): _to_jsonable(v) for k, v in dict(row).items()}
                item["_source"] = "db_fallback"
                if target_run_id is not None:
                    item.setdefault("target_run_id", str(target_run_id))
                normalized_rows.append(item)

            self.sources.append(ReportSource(
                "m9_selected_stocks_db_fallback",
                table,
                "USED",
                f"read {len(normalized_rows)} selected stock rows" + (f" for target_run_id={target_run_id}" if target_run_id is not None else ""),
            ))
            return normalized_rows
        except Exception as exc:
            self.sources.append(ReportSource(
                "m9_selected_stocks_db_fallback",
                "",
                "MISSING",
                f"DB fallback failed: {type(exc).__name__}: {exc}",
            ))
            return []
        finally:
            if session is not None:
                try:
                    session.close()
                except Exception:
                    pass

    def _first_existing_table(self, table_names: set[str], candidates: list[str]) -> str | None:
        for table in candidates:
            if table in table_names:
                return table
        return None

    def _read_table_columns(self, session: Any, text: Any, table: str) -> set[str]:
        try:
            rows = session.execute(
                text(
                    "select column_name from information_schema.columns "
                    "where table_schema not in ('pg_catalog', 'information_schema') "
                    "and table_name = :table_name"
                ),
                {"table_name": table},
            ).fetchall()
            return {str(row[0]) for row in rows}
        except Exception:
            return set()

    def _resolve_target_run_id(self, daily_ops: dict[str, Any], paper_chain: dict[str, Any]) -> int | None:
        value = self._find_first_deep(
            {"daily_ops": daily_ops, "paper_chain": paper_chain},
            [
                "target_run_id",
                "target_position_run_id",
                "source_target_run_id",
                "adjusted_target_run_id",
            ],
        )
        try:
            if value is None or str(value).strip() == "":
                return None
            return int(str(value).strip())
        except Exception:
            return None

    def _find_first_deep(self, value: Any, names: list[str]) -> Any:
        if isinstance(value, dict):
            lower = {str(k).lower(): v for k, v in value.items()}
            for name in names:
                if name in value:
                    return value[name]
                lowered = name.lower()
                if lowered in lower:
                    return lower[lowered]
            for child in value.values():
                found = self._find_first_deep(child, names)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = self._find_first_deep(child, names)
                if found is not None:
                    return found
        return None

    def _query_target_rows(
        self,
        session: Any,
        text: Any,
        table: str,
        columns: set[str],
        target_run_id: int | None,
        report_date: str,
    ) -> list[dict[str, Any]]:
        run_col = self._first_existing_column(columns, [
            "run_id",
            "target_run_id",
            "target_position_run_id",
            "paper_target_run_id",
        ])
        date_col = self._first_existing_column(columns, [
            "effective_date",
            "trade_date",
            "target_date",
            "as_of_date",
            "snapshot_date",
        ])
        order_clause = self._target_order_clause(columns)

        if target_run_id is not None and run_col:
            sql = f"select * from {table} where {run_col} = :target_run_id {order_clause}"
            rows = [dict(row) for row in session.execute(text(sql), {"target_run_id": target_run_id}).mappings().all()]
            if rows:
                return rows

        latest_run_id = self._find_latest_target_run_id(session, text, table, columns, run_col, date_col, report_date)
        if latest_run_id is not None and run_col:
            sql = f"select * from {table} where {run_col} = :target_run_id {order_clause}"
            return [dict(row) for row in session.execute(text(sql), {"target_run_id": latest_run_id}).mappings().all()]

        where = ""
        params: dict[str, Any] = {}
        if date_col:
            where = f"where {date_col} <= :report_date"
            params["report_date"] = report_date
        limit = " limit 500"
        sql = f"select * from {table} {where} {order_clause}{limit}"
        return [dict(row) for row in session.execute(text(sql), params).mappings().all()]

    def _find_latest_target_run_id(
        self,
        session: Any,
        text: Any,
        table: str,
        columns: set[str],
        run_col: str | None,
        date_col: str | None,
        report_date: str,
    ) -> int | None:
        if not run_col:
            return None
        try:
            if date_col:
                sql = (
                    f"select {run_col} as run_id, max({date_col}) as max_date "
                    f"from {table} where {date_col} <= :report_date "
                    f"group by {run_col} order by max_date desc, {run_col} desc limit 1"
                )
                row = session.execute(text(sql), {"report_date": report_date}).mappings().first()
            else:
                sql = f"select {run_col} as run_id from {table} group by {run_col} order by {run_col} desc limit 1"
                row = session.execute(text(sql)).mappings().first()
            if not row or row.get("run_id") is None:
                return None
            return int(row.get("run_id"))
        except Exception:
            return None

    def _first_existing_column(self, columns: set[str], candidates: list[str]) -> str | None:
        for column in candidates:
            if column in columns:
                return column
        return None

    def _target_order_clause(self, columns: set[str]) -> str:
        order_parts: list[str] = []
        for column in ["rank", "target_rank", "sort_order"]:
            if column in columns:
                order_parts.append(f"{column} asc")
                break
        for column in ["target_weight", "weight", "target_amount"]:
            if column in columns:
                order_parts.append(f"{column} desc")
                break
        for column in ["id", "instrument_id"]:
            if column in columns:
                order_parts.append(f"{column} asc")
        return " order by " + ", ".join(order_parts) if order_parts else ""

    def _load_instrument_identity_map(self, instrument_ids: Iterable[Any]) -> dict[str, dict[str, Any]]:
        """Best-effort lookup from meta_instrument by instrument_id.

        M8 paper_chain CSVs intentionally keep only instrument_id. The natural
        language report needs human-readable stock identity, so this method
        reads meta_instrument without modifying DB state. It is soft-fail by
        design: if DB or table lookup is unavailable, callers still display
        instrument_id instead of N/A.
        """
        ids: list[int] = []
        for raw in instrument_ids:
            try:
                if raw is not None and str(raw).strip() != "":
                    ids.append(int(str(raw).strip()))
            except Exception:
                continue
        ids = sorted(set(ids))
        if not ids:
            return {}

        try:
            from sqlalchemy import text  # type: ignore
            from stock_quant_v2.db.session import SessionLocal  # type: ignore
        except Exception:
            return {}

        session = None
        try:
            session = SessionLocal()
            sql = (
                "select * from meta_instrument "
                "where id in (" + ",".join(str(x) for x in ids) + ")"
            )
            rows = session.execute(text(sql)).mappings().all()
        except Exception:
            return {}
        finally:
            if session is not None:
                try:
                    session.close()
                except Exception:
                    pass

        identity_map: dict[str, dict[str, Any]] = {}
        for row_mapping in rows:
            row = {str(k): v for k, v in dict(row_mapping).items()}
            raw_id = _pick(row, ["id", "instrument_id"])
            if raw_id is None:
                continue
            instrument_id = str(raw_id).strip()
            if not instrument_id:
                continue

            stock_code = _pick(row, [
                "ticker", "instrument_code", "symbol", "stock_code",
                "security_code", "code", "vendor_symbol", "ts_code",
            ])
            exchange_code = _pick(row, [
                "exchange_code", "exchange", "market_code", "exchange_id",
            ])
            stock_name = _pick(row, [
                "instrument_name", "stock_name", "security_name", "name",
                "short_name", "display_name",
            ])

            stock_code_text = "" if stock_code is None else str(stock_code).strip()
            exchange_code_text = _normalize_exchange_code_value(exchange_code)
            stock_name_text = "" if stock_name is None else str(stock_name).strip()

            display_code = stock_code_text or f"instrument_id={instrument_id}"
            if stock_code_text and exchange_code_text and "." not in stock_code_text:
                display_code = f"{stock_code_text}.{exchange_code_text}"
            display_label = (display_code + (f" {stock_name_text}" if stock_name_text else "")).strip()

            identity_map[instrument_id] = {
                "instrument_id": instrument_id,
                "stock_code": stock_code_text,
                "exchange_code": exchange_code_text,
                "stock_name": stock_name_text,
                "display_code": display_code,
                "display_name": stock_name_text,
                "display_label": display_label,
                "identity_status": "OK" if stock_code_text or stock_name_text else "WARN",
            }
        return identity_map

    def _normalize_selected_stock_rows(self, rows: list[dict[str, str]]) -> list[dict[str, Any]]:
        identity_map = self._load_instrument_identity_map([
            _pick(row, ["instrument_id", "id"]) for row in rows
        ])
        normalized: list[dict[str, Any]] = []
        for idx, row in enumerate(rows, start=1):
            instrument_id = _pick(row, ["instrument_id"])
            instrument_id_text = "" if instrument_id is None else str(instrument_id).strip()
            identity = identity_map.get(instrument_id_text, {})

            stock_code = (
                _pick(row, ["ticker", "instrument_code", "symbol", "stock_code", "security_code", "code", "vendor_symbol"])
                or identity.get("stock_code")
            )
            exchange_code = _pick(row, ["exchange_code", "exchange", "market_code"]) or identity.get("exchange_code")
            stock_name = (
                _pick(row, ["instrument_name", "stock_name", "name", "display_name"])
                or identity.get("stock_name")
            )

            stock_code_text = "" if stock_code is None else str(stock_code).strip()
            exchange_code_text = _normalize_exchange_code_value(exchange_code)
            stock_name_text = "" if stock_name is None else str(stock_name).strip()

            display_code = identity.get("display_code") or stock_code_text
            if stock_code_text and exchange_code_text and "." not in stock_code_text:
                display_code = f"{stock_code_text}.{exchange_code_text}"
            if not display_code:
                display_code = f"instrument_id={instrument_id_text}" if instrument_id_text else "N/A"
            display_label = (display_code + (f" {stock_name_text}" if stock_name_text else "")).strip()
            identity_status = "OK" if stock_code_text or stock_name_text else "WARN"

            normalized.append({
                "rank": idx,
                "instrument_id": instrument_id_text,
                "stock_code": stock_code_text,
                "exchange_code": exchange_code_text,
                "stock_name": stock_name_text,
                "display_code": display_code,
                "display_name": stock_name_text,
                "display_label": display_label,
                "identity_status": identity_status,
                "row_source": _pick(row, ["_source"], "artifact"),
                "target_run_id": _pick(row, ["target_run_id", "target_position_run_id", "run_id"]),
                "target_weight": _pick(row, ["target_weight", "weight", "target_position_weight"]),
                "target_quantity": _pick(row, ["target_quantity", "quantity", "target_qty"]),
                "target_amount": _pick(row, ["target_amount", "amount", "target_market_value"]),
                "as_of_date": _pick(row, ["as_of_date"]),
                "effective_date": _pick(row, ["effective_date"]),
                "risk_status": _pick(row, ["risk_status", "decision_type"]),
                "source_columns": row,
            })
        return normalized

    def _extract_positions(self, rows: list[dict[str, str]], portfolio_fact: dict[str, Any]) -> dict[str, Any]:
        market_values: list[Decimal] = []
        for row in rows:
            value = _safe_decimal(_pick(row, ["market_value", "market_value_total", "position_market_value"]))
            if value is not None:
                market_values.append(value)
        top_mv = sorted(market_values, reverse=True)[:5]
        return {
            "row_count": len(rows),
            "open_position_count": portfolio_fact.get("open_position_count"),
            "top5_market_value_total": str(sum(top_mv, Decimal("0"))) if top_mv else None,
        }

    def _build_position_summary_rows(self, rows: list[dict[str, str]], portfolio_fact: dict[str, Any]) -> list[dict[str, Any]]:
        if rows:
            return [dict(row) for row in rows]
        return [{
            "snapshot_date": portfolio_fact.get("snapshot_date"),
            "holding_count": portfolio_fact.get("holding_count"),
            "cash_balance": portfolio_fact.get("cash_balance"),
            "market_value": portfolio_fact.get("market_value"),
            "total_equity": portfolio_fact.get("total_equity"),
            "gross_exposure": portfolio_fact.get("gross_exposure"),
            "net_exposure": portfolio_fact.get("net_exposure"),
            "daily_pnl": portfolio_fact.get("daily_pnl"),
            "cumulative_pnl": portfolio_fact.get("cumulative_pnl"),
        }]

    def _derive_status_layers(self, facts: dict[str, Any]) -> dict[str, str]:
        market = facts.get("market") or {}
        db_market = facts.get("db_market") or {}
        backtest = facts.get("backtest") or {}
        portfolio = facts.get("portfolio") or {}
        risk = facts.get("risk") or {}
        selected = facts.get("selected") or {}
        campaigns = facts.get("paper_campaigns") or {}

        data_status = "OK"
        if _is_warnish_status(market.get("status")) or _is_warnish_status(db_market.get("status")):
            data_status = "WARN"
        if selected.get("identity_missing_count"):
            data_status = "WARN"

        research_status = "OK" if not _is_warnish_status(backtest.get("status")) else "WARN"
        portfolio_status = "OK" if portfolio.get("total_equity") else "WARN"
        campaign_status = "OK" if campaigns.get("status") in {"OK", "MISSING"} else "WARN"
        risk_review_status = "OK"
        if not risk.get("status") and not risk.get("alert_status"):
            risk_review_status = "WARN"
        if _decimal_gt(risk.get("warn_count"), "0") or str(risk.get("highest_alert_level") or "").upper() == "CRITICAL":
            risk_review_status = "WARN"
        if _decimal_gt(risk.get("reject_count"), "0"):
            risk_review_status = "FAIL"

        final = "OK，可以作为 paper trading 复盘参考。"
        if "FAIL" in {data_status, research_status, portfolio_status, risk_review_status}:
            final = "FAIL，不建议参考为自动执行依据，需先处理阻断项。"
        elif "WARN" in {data_status, research_status, portfolio_status, campaign_status, risk_review_status}:
            final = "WARN，谨慎参考，需要人工复核后使用。"

        return {
            "DATA_STATUS": data_status,
            "RESEARCH_STATUS": research_status,
            "PORTFOLIO_STATUS": portfolio_status,
            "CAMPAIGN_STATUS": campaign_status,
            "RISK_REVIEW_STATUS": risk_review_status,
            "FINAL_REVIEW_CONCLUSION": final,
        }

    def _derive_review_flags(self, facts: dict[str, Any]) -> list[dict[str, Any]]:
        flags: list[dict[str, Any]] = []
        selected = facts.get("selected") or {}
        portfolio = facts.get("portfolio") or {}
        backtest = facts.get("backtest") or {}
        risk = facts.get("risk") or {}
        market = facts.get("market") or {}
        db_market = facts.get("db_market") or {}
        campaigns = facts.get("paper_campaigns") or {}

        def add(priority: str, category: str, item: str, reason: str, suggested_action: str, source: str) -> None:
            flags.append({
                "priority": priority,
                "category": category,
                "item": item,
                "reason": reason,
                "suggested_action": suggested_action,
                "source": source,
            })

        for row in campaigns.get("rows") or []:
            if str(row.get("status") or "").upper() in {"FAIL", "FAILED", "ERROR"}:
                add(
                    "P0", "M6.5未来模拟盘", row.get("campaign_code") or "N/A",
                    f"campaign daily status={row.get('status')}，action={row.get('action')}，reason={row.get('reason')}",
                    "复核该独立 campaign portfolio 的 M6/M7 run lineage 和当日输入数据。",
                    "m6_5_paper_campaign_daily",
                )

        st_rows = [row for row in (selected.get("all_rows") or selected.get("top_rows") or []) if _is_st_or_special_treatment(row)]
        for row in st_rows[:20]:
            add(
                "P0", "异常标的", row.get("display_label") or row.get("stock_code") or row.get("instrument_id") or "N/A",
                "目标仓位中识别到 ST / *ST / 退市风险字样。",
                "复核股票池是否允许 ST；如不允许，检查 M4 universe 与 M7 风控规则。",
                "selected_stocks",
            )

        cash_ratio = _ratio(portfolio.get("cash_balance"), portfolio.get("total_equity"))
        if cash_ratio is not None and cash_ratio < Decimal("0.05"):
            add(
                "P0", "资金缓冲", f"现金占比 {_fmt_pct(cash_ratio)}",
                "现金占比低于 5%，后续调仓或买入可能受现金约束。",
                "复核是否需要保留现金缓冲，或降低目标满仓程度。",
                "portfolio_snapshot",
            )

        exposure_ratio = _safe_decimal(portfolio.get("exposure_ratio"))
        if exposure_ratio is not None and exposure_ratio > Decimal("0.95"):
            add(
                "P1", "仓位水平", f"敞口比例 {_fmt_pct(exposure_ratio)}",
                "组合接近满仓，对市场波动和后续调仓更敏感。",
                "复核是否符合当前策略仓位目标和风险预算。",
                "portfolio_snapshot",
            )

        turnover_rate = _safe_decimal(portfolio.get("turnover_rate"))
        if turnover_rate is not None and turnover_rate > Decimal("0.80"):
            add(
                "P1", "换手", f"换手率 {_fmt_pct(turnover_rate)}",
                "本轮换手接近全仓级别，交易成本和滑点假设对结果影响较大。",
                "复核交易成本、滑点假设、换手约束是否合理。",
                "portfolio_snapshot",
            )

        if _decimal_gt(risk.get("warn_count"), "0"):
            add(
                "P1", "风控", f"WARN={risk.get('warn_count')}",
                "风控存在 WARN 项，不能仅因无 REJECT 就视为完全放行。",
                "复核 MISSING_STATUS / MISSING_PRICE_LIMIT 等基础数据风险。",
                "m8_risk",
            )

        if str(risk.get("highest_alert_level") or "").upper() == "CRITICAL":
            add(
                "P0", "告警", "最高告警 CRITICAL",
                f"告警状态={risk.get('alert_status') or 'N/A'}，告警统计={risk.get('alert_counts') or 'N/A'}。",
                "先定位 CRITICAL 告警来源，确认是否影响本报告结论可信度。",
                "m8_alert",
            )

        if backtest.get("internal_one_day_hold_preview"):
            add(
                "P0", "回测口径", "INTERNAL_ONE_DAY_HOLD_PREVIEW",
                "当前 M5 结果来自 close-to-next-close 一日持有 preview，属于研究回测证据，不是 M6 paper trading 晋级结论。",
                "在 M9.2 中解释收益、回撤、手数约束和窗口边界；禁止据此自动晋级 M6。",
                "m5_bridge",
            )

        preview_stats = backtest.get("preview_warning_stats") or {}
        if _decimal_gt(preview_stats.get("zero_lot_skipped"), "0"):
            add(
                "P1", "手数约束", f"zero_lot_skipped={preview_stats.get('zero_lot_skipped')}",
                "100 股手数约束导致部分目标无法成手成交，影响资金利用率和策略容量解释。",
                "复核 top_n、单票目标权重、初始资金和 board-lot 约束对结果的影响。",
                "m5_bridge",
            )

        if _decimal_gt(preview_stats.get("missing_exit_date_skipped"), "0"):
            add(
                "P1", "回测窗口", f"missing_exit_date_skipped={preview_stats.get('missing_exit_date_skipped')}",
                "部分 target date 缺少下一交易日 exit close，通常是窗口尾部边界问题。",
                "复核回测 end_date 是否需要向后一日扩展，或在报告中明确排除最后一日信号。",
                "m5_bridge",
            )

        if _decimal_gt(backtest.get("total_return"), "0") is False and backtest.get("total_return") is not None:
            add(
                "P1", "收益风险", f"total_return={backtest.get('total_return')}",
                "当前研究窗口累计收益为负，不能形成正向策略有效性结论。",
                "进入 M9.2 时优先解释市场环境、因子/行业贡献、交易成本敏感性和消融验证缺口。",
                "m5_bridge",
            )

        if _is_warnish_status(backtest.get("status")):
            add(
                "P1", "回测", f"回测状态 {backtest.get('status') or 'N/A'}",
                "当前回测结果可读，但尚不能直接视为生产级实盘执行结论。",
                "确认当前 execution_mode、warning codes 和是否需要 benchmark / 交易成本 / 消融实验补充。",
                "m5_bridge",
            )

        if not (db_market.get("daily_bar_summary") or {}).get("up_count"):
            add(
                "P2", "市场环境", "市场宽度缺失",
                "暂未识别完整涨跌家数、指数涨跌、成交额。",
                "后续接入市场宽度或指数快照，用于判断策略适配环境。",
                "m3/db_market",
            )

        return flags

    def _section_cover_and_watermark(self, facts: dict[str, Any]) -> ReportSection:
        strategy = facts["strategy"]
        selected = facts["selected"]
        portfolio = facts["portfolio"]
        backtest = facts["backtest"]
        risk = facts["risk"]
        campaigns = facts.get("paper_campaigns") or {}
        layers = facts.get("status_layers") or {}
        details = [
            f"报告生成日：{facts.get('report_date') or 'N/A'}。",
            f"组合快照日：{portfolio.get('snapshot_date') or 'N/A'}。",
            f"目标仓位日期：as_of_date={self._selected_date(selected, 'as_of_date')}，effective_date={self._selected_date(selected, 'effective_date')}。",
            f"最新信号水位：as_of_date={strategy.get('signal_latest_as_of_date') or 'N/A'}，effective_date={strategy.get('signal_latest_effective_date') or 'N/A'}。",
            f"回测区间：{backtest.get('start_date') or 'N/A'} 至 {backtest.get('end_date') or 'N/A'}，run_id={backtest.get('run_id') or 'N/A'}。",
            f"风控决策日期：{risk.get('min_decision_date') or 'N/A'} 至 {risk.get('max_decision_date') or 'N/A'}。",
            f"M6.5 campaign：count={campaigns.get('campaign_count') or 0}，executed={campaigns.get('executed_count') or 0}，skipped={campaigns.get('skipped_count') or 0}，failed={campaigns.get('failed_count') or 0}。",
            "状态分层："
            f"DATA={layers.get('DATA_STATUS') or 'N/A'}，"
            f"RESEARCH={layers.get('RESEARCH_STATUS') or 'N/A'}，"
            f"PORTFOLIO={layers.get('PORTFOLIO_STATUS') or 'N/A'}，"
            f"CAMPAIGN={layers.get('CAMPAIGN_STATUS') or 'N/A'}，"
            f"RISK_REVIEW={layers.get('RISK_REVIEW_STATUS') or 'N/A'}。",
        ]
        return ReportSection(
            "00",
            "报告封面与数据水位",
            "OK",
            "本节用于说明报告生成日、组合快照日、信号水位、目标仓位生效日和风控日期，避免混淆不同业务日期。",
            details,
        )

    def _selected_date(self, selected: dict[str, Any], key: str) -> str:
        for row in selected.get("top_rows") or []:
            value = row.get(key)
            if value:
                return str(value)
        return "N/A"

    def _section_exec_summary(self, facts: dict[str, Any]) -> ReportSection:
        strategy = facts["strategy"]
        selected = facts["selected"]
        backtest = facts["backtest"]
        portfolio = facts["portfolio"]
        risk = facts["risk"]
        campaigns = facts.get("paper_campaigns") or {}
        layers = facts.get("status_layers") or {}
        flags = facts.get("review_flags") or []
        cash_ratio = _ratio(portfolio.get("cash_balance"), portfolio.get("total_equity"))
        summary = layers.get("FINAL_REVIEW_CONCLUSION") or "WARN，谨慎参考，需要人工复核后使用。"
        details = [
            f"当前策略：{strategy.get('strategy_code') or 'N/A'} / {strategy.get('version_code') or 'N/A'}。",
            f"目标股票：{selected.get('row_count') or selected.get('target_count') or 'N/A'} 只；组合持仓：{portfolio.get('holding_count') or portfolio.get('open_position_count') or 'N/A'} 只。",
            f"组合敞口：{_fmt_pct(portfolio.get('exposure_ratio'))}；现金占比：{_fmt_pct(cash_ratio)}。",
            f"研究回测表现：累计收益 {_fmt_pct(backtest.get('total_return'))}，最大回撤 {_fmt_pct(backtest.get('max_drawdown'), signed=True)}，Sharpe {_fmt_metric(backtest.get('sharpe_ratio'))}。",
            f"风控状态：PASS={risk.get('pass_count') or 'N/A'}，WARN={risk.get('warn_count') or 'N/A'}，REJECT={risk.get('reject_count') or 'N/A'}；最高告警={risk.get('highest_alert_level') or 'N/A'}。",
        ]
        if flags:
            details.append("重点复核事项：")
            for idx, flag in enumerate(flags[:5], start=1):
                details.append(f"{idx}. [{flag.get('priority')}] {flag.get('category')}：{flag.get('item')}；建议：{flag.get('suggested_action')}")
        return ReportSection("01", "一页式执行摘要", "WARN" if flags else "OK", summary, details)

    def _section_market(self, facts: dict[str, Any]) -> ReportSection:
        market = facts["market"]
        db_market = facts["db_market"]
        db_daily = db_market.get("daily_bar_summary") or {}
        details = [
            f"M3 数据状态：{market.get('status') or 'N/A'}，latest_run_id={market.get('latest_run_id') or 'N/A'}，run_name={market.get('latest_run_name') or 'N/A'}。",
            f"日线行数：{_fmt_int(market.get('daily_bar_rows') or market.get('total_bar_rows'))}；指标行数：{_fmt_int(market.get('indicator_rows'))}；特征行数：{_fmt_int(market.get('feature_rows'))}；标签行数：{_fmt_int(market.get('label_rows'))}。",
        ]
        if db_daily:
            details.append(
                "DB 市场日线快照："
                f"交易日={db_daily.get('latest_trade_date') or 'N/A'}，"
                f"标的数={_fmt_int(db_daily.get('instrument_count'))}，"
                f"上涨={_fmt_int(db_daily.get('up_count'))}，下跌={_fmt_int(db_daily.get('down_count'))}，平盘={_fmt_int(db_daily.get('flat_count'))}，"
                f"上涨占比={_fmt_pct(db_daily.get('up_ratio'))}，平均涨跌幅={_fmt_pct(db_daily.get('avg_return'), signed=True)}。"
            )
        else:
            details.append("暂未从 DB/市场宽度 artifact 识别到完整涨跌家数、指数涨跌和成交额；本节目前主要解释数据水位。")
        summary = "市场环境用于判断策略适配背景；当前 P1 以数据水位和可选 DB 行情快照为主，市场宽度/指数涨跌后续继续补。"
        status = "OK" if db_daily else ("WARN" if market.get("daily_bar_rows") or market.get("total_bar_rows") else "MISSING")
        return ReportSection("02", "市场环境与交易背景", status, summary, details)

    def _section_strategy(self, facts: dict[str, Any]) -> ReportSection:
        s = facts["strategy"]
        weights = s.get("weights") or {}
        if isinstance(weights, dict):
            weight_text = "，".join(f"{k}={_fmt_pct(v)}" for k, v in weights.items())
        else:
            weight_text = str(weights or "N/A")
        details = [
            f"策略：{s.get('strategy_code') or 'N/A'}（{s.get('strategy_name') or 'N/A'}），类型={s.get('strategy_type') or 'N/A'}，引擎={s.get('engine_type') or 'N/A'}。",
            f"版本：{s.get('version_code') or 'N/A'}，strategy_version_id={s.get('strategy_version_id') or 'N/A'}，输出契约={s.get('output_contract_version') or 'N/A'}。",
            f"信号来源 run_id：{s.get('source_signal_run_id') or 'N/A'}；策略来源={s.get('strategy_source') or 'N/A'}。",
            f"参数：top_n={s.get('top_n') or 'N/A'}，min_score={s.get('min_score') or 'N/A'}，权重={weight_text}。",
            f"信号水位：signal_total_rows={_fmt_int(s.get('signal_total_rows'))}，latest_as_of_date={s.get('signal_latest_as_of_date') or 'N/A'}，latest_effective_date={s.get('signal_latest_effective_date') or 'N/A'}。",
        ]
        summary = "当前股票来自 M4 strategy_signal 契约；本报告只解释已生成信号，不生成新信号。"
        status = "OK" if s.get("strategy_code") and s.get("signal_latest_effective_date") else "WARN"
        return ReportSection("03", "策略与信号说明", status, summary, details)

    def _section_selected(self, facts: dict[str, Any]) -> ReportSection:
        selected = facts["selected"]
        rows = selected.get("top_rows") or []
        details = [
            f"本轮目标/选股行数：{selected.get('row_count') or selected.get('target_count') or 'N/A'}；完整清单见 selected_stocks.csv。",
            f"选股明细来源：{selected.get('source') or 'N/A'}。",
        ]
        if rows:
            for row in rows[:10]:
                details.append(
                    f"#{row.get('rank')} {row.get('display_label') or row.get('stock_code') or ('instrument_id=' + str(row.get('instrument_id')) if row.get('instrument_id') else 'N/A')}，"
                    f"目标权重={_fmt_pct(row.get('target_weight'))}，"
                    f"目标数量={_fmt_qty(row.get('target_quantity'))} 股，"
                    f"目标金额={_fmt_money(row.get('target_amount'))} 元。"
                )
            if (selected.get("row_count") or 0) > 10:
                details.append("正文仅展示前 10 只，完整 30 只见 selected_stocks.csv。")
        else:
            details.append("未找到 paper_chain targets CSV，且 DB 只读兜底未能取回目标仓位明细；需要检查 trading_paper_target_position 或生成 M8 paper_chain report。")
        summary = "本节回答买哪些、买多少、目标权重多少；后续 P1 将继续补因子得分、行业、市值和入选原因。"
        status = "OK" if rows else "MISSING"
        return ReportSection("04", "本轮选股与目标仓位", status, summary, details)

    def _section_portfolio(self, facts: dict[str, Any]) -> ReportSection:
        p = facts["portfolio"]
        cash_ratio = _ratio(p.get("cash_balance"), p.get("total_equity"))
        details = [
            f"组合日期：{p.get('snapshot_date') or 'N/A'}，持仓数={p.get('holding_count') or p.get('open_position_count') or 'N/A'}，开放持仓={p.get('open_position_count') or 'N/A'}。",
            f"目标数={p.get('target_count') or 'N/A'}，订单数={p.get('order_count') or 'N/A'}，成交数={p.get('fill_count') or 'N/A'}，持仓明细行={p.get('position_count') or 'N/A'}。",
            f"总权益={_fmt_money(p.get('total_equity'))} 元，现金={_fmt_money(p.get('cash_balance'))} 元，现金占比={_fmt_pct(cash_ratio)}。",
            f"持仓市值={_fmt_money(p.get('market_value'))} 元，总敞口={_fmt_money(p.get('gross_exposure'))} 元，敞口比例={_fmt_pct(p.get('exposure_ratio'))}。",
        ]
        summary = "本节判断组合是否接近满仓、现金缓冲是否充足，以及当前仓位是否符合策略和风险预算。"
        status = "OK" if p.get("total_equity") else "WARN"
        return ReportSection("05", "组合仓位与资金状态", status, summary, details)

    def _section_pnl_turnover(self, facts: dict[str, Any]) -> ReportSection:
        p = facts["portfolio"]
        details = [
            f"当日盈亏={_fmt_signed_money(p.get('daily_pnl'))} 元，累计盈亏={_fmt_signed_money(p.get('cumulative_pnl'))} 元。",
            f"当日收益={_fmt_pct(p.get('daily_return'), signed=True)}，累计收益={_fmt_pct(p.get('cumulative_return'), signed=True)}。",
            f"换手金额={_fmt_money(p.get('turnover_amount'))} 元，换手率={_fmt_pct(p.get('turnover_rate'))}。",
        ]
        turnover = _safe_decimal(p.get("turnover_rate"))
        if turnover is not None and turnover > Decimal("0.80"):
            details.append("解释：本轮换手率高于 80%，接近全仓级别换仓，需关注交易成本、滑点和换手约束。")
        summary = "本节回答今日赚没赚、累计表现如何、换手是否过高；收益归因将在后续 P1/P2 补充。"
        status = "OK" if p.get("daily_pnl") or p.get("turnover_rate") else "WARN"
        return ReportSection("06", "盈亏、收益与换手", status, summary, details)

    def _section_backtest(self, facts: dict[str, Any]) -> ReportSection:
        b = facts["backtest"]
        details = [
            f"回测 run_id={b.get('run_id') or 'N/A'}，request_id={b.get('backtest_request_id') or 'N/A'}，执行模式={b.get('execution_mode') or 'N/A'}。",
            f"区间：{b.get('start_date') or 'N/A'} 至 {b.get('end_date') or 'N/A'}，交易日={b.get('trading_days') or 'N/A'}。",
            f"初始资金={_fmt_money(b.get('initial_cash'))} 元，期末权益={_fmt_money(b.get('final_equity'))} 元，累计收益={_fmt_pct(b.get('total_return'))}，年化收益={_fmt_pct(b.get('annual_return'))}。",
            f"最大回撤={_fmt_pct(b.get('max_drawdown'), signed=True)}，Sharpe={_fmt_metric(b.get('sharpe_ratio'))}，波动率={_fmt_pct(b.get('volatility'))}，订单数={_fmt_int(b.get('order_count'))}，交易数={_fmt_int(b.get('trade_count'))}。",
        ]
        if b.get("internal_one_day_hold_preview"):
            details.append(
                "解释：当前回测模式为 INTERNAL_ONE_DAY_HOLD_PREVIEW，即 signal effective_date close 买入、下一交易日 close 卖出的一日持有研究预览。"
                "该结果只能作为 M9.2 研究解读输入，不能作为 M6 paper trading 晋级、自动调仓或真实交易依据。"
            )
        elif b.get("execution_mode"):
            details.append(
                f"解释：当前回测模式为 {b.get('execution_mode')}。本节用于研究参考，不能直接视为生产级实盘执行结论。"
            )
        elif b.get("message"):
            details.append(f"说明：{b.get('message')}")

        if b.get("message"):
            details.append(f"M5 bridge 解读：{b.get('message')}")

        warning_codes = b.get("quality_warning_codes") or []
        if warning_codes:
            details.append("质量告警代码：" + ", ".join(str(code) for code in warning_codes))

        preview_stats = b.get("preview_warning_stats") or {}
        if preview_stats:
            details.append(
                "一日持有 preview 约束："
                f"target_rows={preview_stats.get('target_rows') or 0}，"
                f"submitted_rows={preview_stats.get('submitted_rows') or 0}，"
                f"zero_lot_skipped={preview_stats.get('zero_lot_skipped') or 0}，"
                f"missing_exit_date_skipped={preview_stats.get('missing_exit_date_skipped') or 0}。"
            )

        if b.get("performance_claim_allowed") is False:
            details.append("边界：performance_claim_allowed=false，本报告只能解释研究证据，不能输出策略晋级或有效性定论。")

        summary = "回测用于提供研究证据；P1 先展示核心收益风险指标，后续必须补 benchmark、交易成本敏感性、消融实验和收益归因。"
        status = b.get("status") or "WARN"
        return ReportSection("07", "回测与研究证据", str(status), summary, details)

    def _section_risk(self, facts: dict[str, Any]) -> ReportSection:
        r = facts["risk"]
        details = [
            f"风控状态={r.get('status') or 'N/A'}，decision_count={r.get('decision_count') or 'N/A'}，PASS={r.get('pass_count') or 'N/A'}，WARN={r.get('warn_count') or 'N/A'}，REJECT={r.get('reject_count') or 'N/A'}，ADJUST={r.get('adjust_count') or 'N/A'}。",
            f"决策日期：{r.get('min_decision_date') or 'N/A'} 至 {r.get('max_decision_date') or 'N/A'}。",
            f"告警状态={r.get('alert_status') or 'N/A'}，最高告警={r.get('highest_alert_level') or 'N/A'}，告警统计={r.get('alert_counts') or 'N/A'}。",
        ]
        for item in (r.get("reason_summary") or [])[:8]:
            details.append(f"风控原因：{item}")
        critical_alerts = []
        for alert in r.get("alerts") or []:
            level = str(_pick(alert, ["level", "severity", "alert_level"]) or "").upper()
            if level == "CRITICAL":
                critical_alerts.append(alert)
        for alert in critical_alerts[:5]:
            details.append(f"CRITICAL 告警：{alert}")
        summary = "风控没有 REJECT 不代表没有风险；WARN 与 CRITICAL 告警必须进入人工复核。"
        status = "WARN" if _decimal_gt(r.get("warn_count"), "0") or str(r.get("highest_alert_level") or "").upper() == "CRITICAL" else (r.get("status") or "WARN")
        return ReportSection("08", "风控、约束与告警", str(status), summary, details)

    def _section_paper_campaigns(self, facts: dict[str, Any]) -> ReportSection:
        campaigns = facts.get("paper_campaigns") or {}
        rows = campaigns.get("rows") or []
        details = [
            f"campaign_count={campaigns.get('campaign_count') or 0}，executed={campaigns.get('executed_count') or 0}，skipped={campaigns.get('skipped_count') or 0}，failed={campaigns.get('failed_count') or 0}。",
            "M6.5 属于生产端 DailyRun 的未来模拟交易活动层；本报告只读解释，不生成信号、不下单、不调仓。",
        ]
        if rows:
            for row in rows[:10]:
                run_ids = row.get("extracted_run_ids") or {}
                details.append(
                    f"{row.get('campaign_code') or 'N/A'}：trade_date={row.get('trade_date') or 'N/A'}，"
                    f"day_no={row.get('day_no') if row.get('day_no') is not None else 'N/A'}，"
                    f"action={row.get('action') or 'N/A'}，status={row.get('status') or 'N/A'}，"
                    f"portfolio={row.get('portfolio_id') or row.get('portfolio_code') or 'N/A'}，"
                    f"strategy={row.get('strategy_code') or 'N/A'}:{row.get('strategy_version_code') or 'N/A'}，"
                    f"run_lineage={run_ids or 'N/A'}。"
                )
        else:
            details.append("未识别到 M6.5 campaign 日报；若生产端已启用，请检查 artifacts/m6_5/paper_campaign_daily。")
        summary = "本节展示未来真实交易日模拟盘活动的推进状态，回答 campaign 今天是否执行、执行到第几天、是否触发 M6/M7。"
        status = campaigns.get("status") or "MISSING"
        return ReportSection("09", "M6.5 Forward Paper Campaign", str(status), summary, details)

    def _section_anomalies_and_actions(self, facts: dict[str, Any]) -> ReportSection:
        flags = facts.get("review_flags") or []
        details: list[str] = []
        if flags:
            for idx, flag in enumerate(flags, start=1):
                details.append(
                    f"{idx}. [{flag.get('priority')}] {flag.get('category')} - {flag.get('item')}：{flag.get('reason')} 建议：{flag.get('suggested_action')}"
                )
        else:
            details.append("当前未识别到必须立即处理的组合级问题；建议人工抽查前十大目标仓位、风控 WARN 和资金状态。")
        return ReportSection(
            "10",
            "异常标的与人工复核清单",
            "WARN" if flags else "OK",
            "本节集中展示需要人工处理的标的、资金、风控、告警、回测和数据问题。",
            details,
        )

    def _section_conclusion(self, facts: dict[str, Any]) -> ReportSection:
        layers = facts.get("status_layers") or {}
        flags = facts.get("review_flags") or []
        conclusion = layers.get("FINAL_REVIEW_CONCLUSION") or "WARN，谨慎参考，需要人工复核后使用。"
        details = [
            f"最终人工结论：{conclusion}",
            "本报告可作为研究回测解读、人工检查和后续策略研究依据。",
            "本报告不应作为自动调仓、自动下单、M6 晋级或无人值守执行依据。",
        ]
        if flags:
            details.append("建议优先处理 P0/P1 复核项，再决定是否采信本轮组合结论。")
        status = "WARN" if flags else "OK"
        return ReportSection("11", "结论与人工动作建议", status, "本节给出最终可采信程度和人工动作边界。", details)

    def _section_sources(self) -> ReportSection:
        used = [s for s in self.sources if s.status == "USED"]
        missing = [s for s in self.sources if s.status != "USED"]
        details = [f"已使用来源 {len(used)} 个，缺失/不可用来源 {len(missing)} 个。"]
        for src in self.sources:
            details.append(f"{src.status}: {src.source_code} -> {src.path or src.note}")
        return ReportSection("12", "来源文件与 run_id 血缘", "OK" if used else "WARN", "报告只基于已落地 artifact 和可选 DB 快照生成，保留完整来源索引。", details)

    def _section_appendix(self, facts: dict[str, Any]) -> ReportSection:
        report_date = facts.get("report_date") or "YYYY-MM-DD"
        stem = f"m9_research_portfolio_daily_p1_{report_date}"
        details = [
            f"{stem}.md：专业版自然语言日报。",
            f"{stem}.json：结构化报告事实、章节和复核项。",
            f"{stem}_selected_stocks.csv：完整目标股清单。",
            f"{stem}_position_summary.csv：组合持仓 / 快照明细。",
            f"{stem}_action_items.csv：人工复核清单。",
            f"{stem}_sources.csv：来源 artifact 索引。",
            "后续 P1/P2 可新增 risk_review_items.csv、alert_items.csv、return_attribution.csv、factor_exposure.csv。",
        ]
        return ReportSection("13", "附录索引", "OK", "本节列出本次报告同步输出的结构化附件。", details)

    def _build_action_items(self, facts: dict[str, Any], sections: list[ReportSection]) -> list[dict[str, Any]]:
        action_items: list[dict[str, Any]] = []
        for flag in facts.get("review_flags") or []:
            action_items.append({
                "priority": flag.get("priority") or "P1",
                "category": flag.get("category") or "复核",
                "item": flag.get("item") or "N/A",
                "reason": flag.get("reason") or "N/A",
                "suggested_action": flag.get("suggested_action") or "N/A",
                "source": flag.get("source") or "N/A",
            })

        selected = facts.get("selected") or {}
        if selected.get("identity_missing_count"):
            action_items.append({
                "priority": "P1",
                "category": "标的身份",
                "item": "部分标的代码/名称未补全",
                "reason": (
                    f"missing_count={selected.get('identity_missing_count')}，"
                    f"sample_ids={selected.get('identity_missing_instrument_ids')}"
                ),
                "suggested_action": "检查 meta_instrument 标的主数据和 instrument_id 映射。",
                "source": "selected_stocks",
            })

        for section in sections:
            if section.status not in ("OK", "PASS", "SUCCESS"):
                action_items.append({
                    "priority": "P1" if section.status in ("WARN", "FAIL") else "P2",
                    "category": "章节状态",
                    "item": f"{section.section_id} {section.title}",
                    "reason": f"section_status={section.status}",
                    "suggested_action": section.summary,
                    "source": "markdown_section",
                })
        return action_items

    def _overall_status(self, sections: list[ReportSection]) -> str:
        statuses = {s.status for s in sections}
        if "FAIL" in statuses or "MISSING" in statuses:
            return "WARN"
        if any(s not in ("OK", "PASS", "SUCCESS") for s in statuses):
            return "WARN"
        return "OK"


class ResearchStrategySnapshotExporter:
    """Export a strategy-centric research snapshot from existing M9 facts/artifacts.

    This exporter deliberately lives in the existing research_portfolio_daily
    module so the M9 report flow can produce an investor/researcher-facing
    snapshot without adding a parallel task or new runtime chain file.
    """

    def __init__(self, repo_root: Path, output_dir: Path, overview_output_dir: Path | None = None):
        self.repo_root = Path(repo_root)
        self.output_dir = Path(output_dir)
        self.overview_output_dir = Path(overview_output_dir) if overview_output_dir is not None else None

    def export(self, report: ResearchPortfolioDailyReport) -> dict[str, Path]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        snapshot = self._build_snapshot(report)
        version_code = str(snapshot.get("strategy", {}).get("strategy_version_code") or "unknown_version")
        safe_version = re.sub(r"[^A-Za-z0-9_\-]+", "_", version_code).strip("_") or "unknown_version"
        stem = f"m9_research_strategy_snapshot_{safe_version}_{report.report_date}"

        paths = {
            "strategy_snapshot_markdown": self.output_dir / f"{stem}.md",
            "strategy_snapshot_json": self.output_dir / f"{stem}.json",
            "strategy_snapshot_parameters_csv": self.output_dir / f"{stem}_parameters.csv",
            "strategy_snapshot_next_experiments_csv": self.output_dir / f"{stem}_next_experiments.csv",
            "strategy_snapshot_sources_csv": self.output_dir / f"{stem}_sources.csv",
        }
        paths["strategy_snapshot_markdown"].write_text(self._to_markdown(snapshot), encoding="utf-8")
        paths["strategy_snapshot_json"].write_text(
            json.dumps(_to_jsonable(snapshot), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._write_rows(paths["strategy_snapshot_parameters_csv"], snapshot.get("parameter_rows") or [])
        self._write_rows(paths["strategy_snapshot_next_experiments_csv"], snapshot.get("next_experiments") or [])
        self._write_rows(paths["strategy_snapshot_sources_csv"], snapshot.get("sources") or [])

        if self.overview_output_dir is not None:
            paths.update(self._export_overview_mirror(paths, snapshot=snapshot, stem=stem))
        return paths

    def _export_overview_mirror(
        self,
        source_paths: dict[str, Path],
        *,
        snapshot: dict[str, Any],
        stem: str,
    ) -> dict[str, Path]:
        """Mirror the strategy snapshot to a top-level overview folder.

        The canonical M9 artifacts stay under artifacts/m9 for traceability.
        This mirror gives the user a single project-root folder to open first,
        without needing to navigate M4/M5/M9 directories.
        """
        assert self.overview_output_dir is not None
        overview_dir = self.overview_output_dir
        archive_dir = overview_dir / "archive"
        overview_dir.mkdir(parents=True, exist_ok=True)
        archive_dir.mkdir(parents=True, exist_ok=True)

        latest_map = {
            "overview_latest_strategy_report_md": (
                source_paths["strategy_snapshot_markdown"],
                overview_dir / "latest_strategy_report.md",
            ),
            "overview_latest_strategy_report_json": (
                source_paths["strategy_snapshot_json"],
                overview_dir / "latest_strategy_report.json",
            ),
            "overview_latest_strategy_parameters_csv": (
                source_paths["strategy_snapshot_parameters_csv"],
                overview_dir / "latest_strategy_parameters.csv",
            ),
            "overview_latest_next_experiments_csv": (
                source_paths["strategy_snapshot_next_experiments_csv"],
                overview_dir / "latest_next_experiments.csv",
            ),
            "overview_latest_sources_csv": (
                source_paths["strategy_snapshot_sources_csv"],
                overview_dir / "latest_sources.csv",
            ),
        }

        outputs: dict[str, Path] = {}
        for name, (src, dst) in latest_map.items():
            if src.exists():
                shutil.copyfile(src, dst)
                outputs[name] = dst

        archive_pairs = {
            "overview_archive_strategy_report_md": (
                source_paths["strategy_snapshot_markdown"],
                archive_dir / f"{stem}.md",
            ),
            "overview_archive_strategy_report_json": (
                source_paths["strategy_snapshot_json"],
                archive_dir / f"{stem}.json",
            ),
            "overview_archive_strategy_parameters_csv": (
                source_paths["strategy_snapshot_parameters_csv"],
                archive_dir / f"{stem}_parameters.csv",
            ),
            "overview_archive_next_experiments_csv": (
                source_paths["strategy_snapshot_next_experiments_csv"],
                archive_dir / f"{stem}_next_experiments.csv",
            ),
            "overview_archive_sources_csv": (
                source_paths["strategy_snapshot_sources_csv"],
                archive_dir / f"{stem}_sources.csv",
            ),
        }
        for name, (src, dst) in archive_pairs.items():
            if src.exists():
                shutil.copyfile(src, dst)
                outputs[name] = dst

        readme_path = overview_dir / "README.md"
        readme_path.write_text(self._overview_readme(snapshot), encoding="utf-8")
        outputs["overview_readme"] = readme_path
        return outputs

    def _overview_readme(self, snapshot: dict[str, Any]) -> str:
        strategy = snapshot.get("strategy") or {}
        backtest = snapshot.get("backtest") or {}
        market_regime = snapshot.get("market_regime") or {}
        gate = snapshot.get("gate_decision") or {}
        diagnostics = snapshot.get("diagnostics") or {}
        lines = [
            "# 项目总览入口",
            "",
            "这个目录是给人工查看的最外层总览入口。",
            "M4/M5/M9 下的原始 artifact 仍然保留，用于审计和追溯；日常先看这里。",
            "",
            "## 当前研究策略",
            "",
            f"- 策略：{strategy.get('strategy_code') or 'N/A'}",
            f"- 版本：{strategy.get('strategy_version_code') or 'N/A'}",
            f"- strategy_version_id：{strategy.get('strategy_version_id') or 'N/A'}",
            f"- source_signal_run_id：{strategy.get('source_signal_run_id') or 'N/A'}",
            "",
            "## 当前市场状态",
            "",
            f"- raw_market_regime：{market_regime.get('latest_raw_market_regime') or 'N/A'}",
            f"- confirmed_market_regime：{market_regime.get('latest_confirmed_market_regime') or 'N/A'}",
            f"- route_name：{market_regime.get('latest_route_name') or 'N/A'}",
            f"- regime_days_in_state：{market_regime.get('latest_regime_days_in_state') or 'N/A'}",
            "",
            "## 最新回测",
            "",
            f"- run_id：{backtest.get('run_id') or 'N/A'}",
            f"- backtest_request_id：{backtest.get('backtest_request_id') or 'N/A'}",
            f"- total_return：{_fmt_pct(backtest.get('total_return'), signed=True)}",
            f"- max_drawdown：{_fmt_pct(backtest.get('max_drawdown'), signed=True)}",
            f"- sharpe_ratio：{_fmt_metric(backtest.get('sharpe_ratio'))}",
            f"- quality_warning_codes：{', '.join(str(x) for x in diagnostics.get('quality_warning_codes') or []) or 'N/A'}",
            "",
            "## 先看这些文件",
            "",
            "1. [latest_strategy_report.md](latest_strategy_report.md) —— 当前策略、市场状态、行业、收益、风险、参数入口。",
            "2. [latest_strategy_parameters.csv](latest_strategy_parameters.csv) —— 当前可调整参数。",
            "3. [latest_next_experiments.csv](latest_next_experiments.csv) —— 下一步可选实验，不代表系统替你决策。",
            "4. [latest_sources.csv](latest_sources.csv) —— 所有来源 artifact。",
            "",
            "## 生产端门禁",
            "",
            f"- can_enter_m6：{gate.get('can_enter_m6')}",
            f"- can_publish_to_production：{gate.get('can_publish_to_production')}",
            f"- reason：{gate.get('reason') or 'N/A'}",
            "",
            "历史版本在 archive/ 目录。",
        ]
        return "\n".join(lines).rstrip() + "\n"

    def _build_snapshot(self, report: ResearchPortfolioDailyReport) -> dict[str, Any]:
        facts = report.facts or {}
        strategy = dict(facts.get("strategy") or {})
        backtest = dict(facts.get("backtest") or {})
        version_code = str(
            backtest.get("strategy_version_code")
            or strategy.get("version_code")
            or "v1_regime_state_machine"
        )

        source_signal_run_id = backtest.get("source_signal_run_id") or strategy.get("source_signal_run_id")
        m5_bridge_path = self._latest_m5_bridge(report.report_date, backtest.get("run_id"))
        m5_bridge = _read_json(m5_bridge_path)
        previous_m5_bridge_path = self._previous_m5_bridge(report.report_date, m5_bridge_path)
        previous_m5_bridge = _read_json(previous_m5_bridge_path)

        preview_dir = self.repo_root / "artifacts" / "m4" / f"historical_signal_generation_preview_{version_code}"
        controlled_dir = self.repo_root / "artifacts" / "m4" / f"historical_signal_controlled_db_write_{version_code}"
        request_dir = self.repo_root / "artifacts" / "m5" / f"historical_backtest_request_controlled_db_write_{version_code}"
        backtest_run_dir = self.repo_root / "artifacts" / "m5" / "backtest" / f"run_{backtest.get('run_id')}"

        batch_summary_path = preview_dir / f"m4_historical_signal_preview_batch_summary_{report.report_date}.csv"
        preview_rows_path = preview_dir / f"m4_historical_signal_preview_rows_{report.report_date}.csv"
        controlled_json_path = controlled_dir / f"m4_historical_signal_controlled_db_write_{report.report_date}.json"
        request_json_path = request_dir / f"m5_historical_backtest_request_controlled_db_write_{report.report_date}.json"
        metrics_path = backtest_run_dir / "backtest_metrics.json"
        equity_path = backtest_run_dir / "backtest_equity_curve.csv"
        rebalance_path = backtest_run_dir / "backtest_rebalance_log.csv"
        trade_log_path = backtest_run_dir / "backtest_trade_log.csv"

        batch_rows = _read_csv_rows(batch_summary_path)
        latest_signal_rows = self._latest_signal_rows(preview_rows_path, limit=20)
        parameter_rows = self._parameter_rows(latest_signal_rows)
        top_industries = self._top_industry_rows(latest_signal_rows)
        top_signals = self._top_signal_rows(latest_signal_rows[:10])
        regime_summary = self._regime_summary(batch_rows)
        previous_comparison = self._previous_comparison(backtest, previous_m5_bridge)
        diagnostics = self._diagnostics(backtest)

        sources = self._source_rows([
            ("m5_bridge_current", m5_bridge_path),
            ("m5_bridge_previous", previous_m5_bridge_path),
            ("m4_historical_preview_batch_summary", batch_summary_path),
            ("m4_historical_preview_rows", preview_rows_path),
            ("m4_controlled_signal_write", controlled_json_path),
            ("m5_request_controlled_write", request_json_path),
            ("m5_backtest_metrics", metrics_path),
            ("m5_backtest_equity_curve", equity_path),
            ("m5_backtest_rebalance_log", rebalance_path),
            ("m5_backtest_trade_log", trade_log_path),
            ("m9_research_portfolio_daily", self.repo_root / "artifacts" / "m9" / "research_portfolio_daily" / f"m9_research_portfolio_daily_p1_{report.report_date}.json"),
            ("m9_platform_overview", self.repo_root / "artifacts" / "m9" / "platform_overview" / f"m9_platform_overview_p1_{report.report_date}.json"),
        ])

        snapshot_strategy = {
            "strategy_code": backtest.get("strategy_code") or strategy.get("strategy_code"),
            "strategy_name": backtest.get("strategy_name") or strategy.get("strategy_name") or "市场状态驱动行业增强选股元策略",
            "strategy_version_code": version_code,
            "strategy_version_id": backtest.get("strategy_version_id") or strategy.get("strategy_version_id"),
            "source_signal_run_id": source_signal_run_id,
            "strategy_stage": "RESEARCH_ONLY",
            "production_allowed": False,
            "concept_strength_enabled": self._parameter_value(parameter_rows, "concept_strength_enabled") or False,
        }

        return {
            "report_date": report.report_date,
            "generated_at": _utc_now_iso(),
            "scope": "M9 Research Strategy Snapshot P1",
            "overall_status": "PASS_WITH_WARN",
            "strategy": snapshot_strategy,
            "market_regime": regime_summary,
            "industry_focus": top_industries,
            "top_signals": top_signals,
            "backtest": {
                **backtest,
                "human_summary": (m5_bridge.get("human_summary") or backtest.get("message")),
            },
            "previous_version_comparison": previous_comparison,
            "parameter_rows": parameter_rows,
            "diagnostics": diagnostics,
            "next_experiments": self._next_experiments(),
            "gate_decision": {
                "can_enter_m6": False,
                "can_publish_to_production": False,
                "can_claim_strategy_effective": False,
                "reason": "M5 controlled backtest is PASS_WITH_WARN, but return/sharpe/drawdown remain weak and performance_claim_allowed=false.",
            },
            "sources": sources,
        }

    def _latest_m5_bridge(self, report_date: str, run_id: Any) -> Path | None:
        bridge_dir = self.repo_root / "artifacts" / "m5" / "m9_bridge"
        if run_id:
            exact = bridge_dir / f"m5_m9_bridge_summary_p1_r{run_id}_{report_date}.json"
            if exact.exists():
                return exact
        candidates = [p for p in bridge_dir.glob(f"m5_m9_bridge_summary_p1_r*_{report_date}.json") if p.is_file()]
        return self._latest_run_file(candidates)

    def _previous_m5_bridge(self, report_date: str, current_path: Path | None) -> Path | None:
        bridge_dir = self.repo_root / "artifacts" / "m5" / "m9_bridge"
        candidates = [p for p in bridge_dir.glob(f"m5_m9_bridge_summary_p1_r*_{report_date}.json") if p.is_file()]
        if current_path:
            candidates = [p for p in candidates if p.resolve() != current_path.resolve()]
        return self._latest_run_file(candidates)

    def _latest_run_file(self, candidates: list[Path]) -> Path | None:
        def key(path: Path) -> tuple[int, float, str]:
            match = re.search(r"_r(\d+)_", path.name)
            run_id = int(match.group(1)) if match else 0
            try:
                mtime = path.stat().st_mtime
            except OSError:
                mtime = 0.0
            return (run_id, mtime, path.name)
        if not candidates:
            return None
        return sorted(candidates, key=key, reverse=True)[0]

    def _latest_signal_rows(self, csv_path: Path, limit: int = 20) -> list[dict[str, str]]:
        if not csv_path.exists():
            return []
        latest_as_of = ""
        latest_rows: list[dict[str, str]] = []
        try:
            with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    as_of = str(row.get("as_of_date") or "")
                    if as_of > latest_as_of:
                        latest_as_of = as_of
                        latest_rows = [row]
                    elif as_of == latest_as_of:
                        latest_rows.append(row)
        except Exception:
            return []
        latest_rows.sort(key=lambda row: int(str(row.get("rank_in_batch") or "999999")))
        return latest_rows[:limit]

    def _regime_summary(self, batch_rows: list[dict[str, str]]) -> dict[str, Any]:
        if not batch_rows:
            return {"status": "MISSING"}
        confirmed = [row.get("confirmed_market_regime") or row.get("market_regime") or "UNKNOWN" for row in batch_rows]
        raw = [row.get("raw_market_regime") or row.get("market_regime") or "UNKNOWN" for row in batch_rows]
        route = [row.get("route_name") or "UNKNOWN" for row in batch_rows]
        def transitions(values: list[str]) -> int:
            return sum(1 for prev, cur in zip(values, values[1:]) if prev != cur)
        segments: list[dict[str, Any]] = []
        start_index = 0
        for i in range(1, len(batch_rows) + 1):
            if i == len(batch_rows) or confirmed[i] != confirmed[start_index]:
                start_row = batch_rows[start_index]
                end_row = batch_rows[i - 1]
                segments.append({
                    "confirmed_market_regime": confirmed[start_index],
                    "start_date": start_row.get("signal_as_of_date"),
                    "end_date": end_row.get("signal_as_of_date"),
                    "signal_day_count": i - start_index,
                    "route_name": end_row.get("route_name"),
                })
                start_index = i
        latest = batch_rows[-1]
        return {
            "status": "OK",
            "signal_day_count": len(batch_rows),
            "latest_signal_as_of_date": latest.get("signal_as_of_date"),
            "latest_raw_market_regime": latest.get("raw_market_regime"),
            "latest_confirmed_market_regime": latest.get("confirmed_market_regime"),
            "latest_market_regime_display": latest.get("market_regime_display"),
            "latest_route_name": latest.get("route_name"),
            "latest_regime_days_in_state": latest.get("regime_days_in_state"),
            "latest_regime_confidence": latest.get("regime_confidence"),
            "latest_regime_transition_flag": latest.get("regime_transition_flag"),
            "latest_regime_reason_code": latest.get("regime_reason_code"),
            "raw_market_regime_counts": dict(Counter(raw)),
            "confirmed_market_regime_counts": dict(Counter(confirmed)),
            "route_name_counts": dict(Counter(route)),
            "raw_transition_count": transitions(raw),
            "confirmed_transition_count": transitions(confirmed),
            "segments": segments,
        }

    def _top_industry_rows(self, rows: list[dict[str, str]]) -> list[dict[str, Any]]:
        counts: Counter[str] = Counter()
        strengths: dict[str, list[Decimal]] = {}
        for row in rows:
            industry = row.get("industry_tag_name") or row.get("industry_tag_code") or "UNKNOWN"
            counts[industry] += 1
            value = _safe_decimal(row.get("feat_industry_strength_20"))
            if value is not None:
                strengths.setdefault(industry, []).append(value)
        output = []
        for industry, count in counts.most_common(10):
            values = strengths.get(industry) or []
            avg_strength = sum(values) / len(values) if values else None
            output.append({
                "industry": industry,
                "selected_count_in_latest_top20": count,
                "avg_industry_strength_20": str(avg_strength) if avg_strength is not None else None,
            })
        return output

    def _top_signal_rows(self, rows: list[dict[str, str]]) -> list[dict[str, Any]]:
        output = []
        for row in rows:
            output.append({
                "rank_in_batch": row.get("rank_in_batch"),
                "instrument_code": row.get("instrument_code") or row.get("subject_key"),
                "display_name": row.get("display_name"),
                "industry": row.get("industry_tag_name"),
                "normalized_score": row.get("normalized_score"),
                "confirmed_market_regime": row.get("confirmed_market_regime"),
                "route_name": row.get("route_name"),
                "reason_summary": row.get("reason_summary"),
            })
        return output

    def _parameter_rows(self, signal_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
        if not signal_rows:
            return []
        payload = {}
        raw = signal_rows[0].get("parameter_payload_json") or "{}"
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {}
        rows: list[dict[str, Any]] = []
        for key in sorted(payload.keys()):
            value = payload.get(key)
            rows.append({
                "parameter_name": key,
                "parameter_value": json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value,
                "category": self._parameter_category(key),
                "comment": self._parameter_comment(key),
            })
        if not any(row.get("parameter_name") == "optimization_boundary" for row in rows):
            rows.append({
                "parameter_name": "optimization_boundary",
                "parameter_value": "research_only_do_not_change_production_without_gate",
                "category": "governance",
                "comment": "参数优化必须新建研究版本并重新跑 M4/M5/M9，不允许直接覆盖生产版本。",
            })
        return rows

    def _parameter_value(self, rows: list[dict[str, Any]], name: str) -> Any:
        for row in rows:
            if row.get("parameter_name") == name:
                return row.get("parameter_value")
        return None

    def _parameter_category(self, name: str) -> str:
        if "regime" in name or "route" in name or "market" in name or "benchmark" in name:
            return "market_regime_and_route"
        if "concept" in name:
            return "concept_domain"
        if "formula" in name or "weight" in name or "score" in name:
            return "scoring"
        if "top_n" in name or "write" in name:
            return "execution_boundary"
        return "strategy_metadata"

    def _parameter_comment(self, name: str) -> str:
        comments = {
            "market_regime_confirmation_policy": "控制 raw_market_regime 到 confirmed_market_regime 的确认规则，是本版本核心差异。",
            "route_name": "当前 confirmed_market_regime 对应的策略路由。",
            "concept_strength_enabled": "概念域当前保持关闭，后续 v1.1 再引入。",
            "target_top_n": "每个信号日最多输出的候选数量。",
            "formula_refs": "评分公式与风险惩罚的引用说明。",
        }
        return comments.get(name, "研究参数；如需优化，应复制为新版本并重新跑完整研究链路。")

    def _previous_comparison(self, backtest: dict[str, Any], previous_m5_bridge: dict[str, Any]) -> dict[str, Any]:
        latest = previous_m5_bridge.get("latest_result") or {}
        if not latest:
            return {"status": "MISSING"}
        return {
            "status": "OK",
            "previous_run_id": previous_m5_bridge.get("latest_run_id") or latest.get("run_id"),
            "previous_backtest_request_id": previous_m5_bridge.get("backtest_request_id") or latest.get("backtest_request_id"),
            "previous_strategy_version_code": previous_m5_bridge.get("strategy_version_code"),
            "previous_total_return": latest.get("total_return"),
            "current_total_return": backtest.get("total_return"),
            "delta_total_return": self._decimal_delta(backtest.get("total_return"), latest.get("total_return")),
            "previous_max_drawdown": latest.get("max_drawdown"),
            "current_max_drawdown": backtest.get("max_drawdown"),
            "delta_max_drawdown": self._decimal_delta(backtest.get("max_drawdown"), latest.get("max_drawdown")),
            "previous_sharpe_ratio": latest.get("sharpe_ratio"),
            "current_sharpe_ratio": backtest.get("sharpe_ratio"),
            "delta_sharpe_ratio": self._decimal_delta(backtest.get("sharpe_ratio"), latest.get("sharpe_ratio")),
        }

    def _decimal_delta(self, current: Any, previous: Any) -> str | None:
        c = _safe_decimal(current)
        p = _safe_decimal(previous)
        if c is None or p is None:
            return None
        return str(c - p)

    def _diagnostics(self, backtest: dict[str, Any]) -> dict[str, Any]:
        warnings = backtest.get("quality_warning_codes") or []
        stats = backtest.get("preview_warning_stats") or {}
        return {
            "quality_warning_codes": warnings,
            "preview_warning_stats": stats,
            "zero_lot_rate": self._safe_ratio(stats.get("zero_lot_skipped"), stats.get("target_rows")),
            "submitted_ratio": stats.get("submitted_ratio"),
            "performance_claim_allowed": backtest.get("performance_claim_allowed"),
            "main_interpretation": "链路已打通，但收益、回撤、Sharpe 仍不支持晋级生产端。",
        }

    def _safe_ratio(self, numerator: Any, denominator: Any) -> str | None:
        ratio = _ratio(numerator, denominator)
        return str(ratio) if ratio is not None else None

    def _next_experiments(self) -> list[dict[str, Any]]:
        return [
            {
                "experiment_code": "route_weight_sensitivity",
                "priority": "P1",
                "change_area": "策略路由权重",
                "what_to_change": "TREND_ON/RANGE/RISK_OFF 下 industry_strength、stock_alpha、risk_penalty 的权重。",
                "why": "确认亏损是否来自路由权重过度偏向行业强度或动量。",
                "how_to_validate": "新建 strategy_version，重跑 M4 signal、M5 backtest、M9 snapshot，与当前版本并排比较。",
            },
            {
                "experiment_code": "market_regime_threshold_sensitivity",
                "priority": "P1",
                "change_area": "市场状态确认规则",
                "what_to_change": "确认窗口、3/5 规则、最短驻留期、RISK_OFF 快速触发阈值。",
                "why": "验证状态切换是否过慢或过于保守。",
                "how_to_validate": "检查 confirmed_transition_count、各状态收益、benchmark excess、回撤变化。",
            },
            {
                "experiment_code": "stock_factor_ablation",
                "priority": "P1",
                "change_area": "个股因子消融",
                "what_to_change": "分别去掉 momentum、trend、low_vol、liquidity、industry_strength 或 risk_penalty。",
                "why": "定位负收益来自哪组因子，而不是直接猜参数。",
                "how_to_validate": "每个消融版本单独回测，比较收益、回撤、Sharpe 和行业集中度。",
            },
            {
                "experiment_code": "holding_period_design",
                "priority": "P2",
                "change_area": "持有周期",
                "what_to_change": "从 close→next close 扩展到 3/5/10 日持有，但需先设计重叠持仓和现金占用规则。",
                "why": "当前一日持有可能不适合行业增强选股策略。",
                "how_to_validate": "先做 design artifact，再 controlled dry-run，不直接写生产。",
            },
            {
                "experiment_code": "concept_domain_v1_1",
                "priority": "P2",
                "change_area": "概念域",
                "what_to_change": "引入 concept_strength 输入，但不接外部 API，先从 CSV/artifact 开始。",
                "why": "满足后续概念强弱增强诉求，同时保持可审计。",
                "how_to_validate": "概念域独立 readiness + M4 preview + M5 回测。",
            },
        ]

    def _source_rows(self, items: list[tuple[str, Path | None]]) -> list[dict[str, Any]]:
        rows = []
        for code, path in items:
            exists = bool(path and path.exists())
            rows.append({
                "source_code": code,
                "path": "" if path is None else str(path.relative_to(self.repo_root) if path.exists() else path),
                "status": "USED" if exists else "MISSING",
            })
        return rows

    def _to_markdown(self, snapshot: dict[str, Any]) -> str:
        s = snapshot.get("strategy") or {}
        r = snapshot.get("market_regime") or {}
        b = snapshot.get("backtest") or {}
        d = snapshot.get("diagnostics") or {}
        comp = snapshot.get("previous_version_comparison") or {}
        gate = snapshot.get("gate_decision") or {}
        lines: list[str] = []
        lines.append(f"# M9 研究策略快照｜{s.get('strategy_version_code') or 'unknown_version'}")
        lines.append("")
        lines.append(f"- Report Date: {snapshot.get('report_date')}")
        lines.append(f"- Generated At: {snapshot.get('generated_at')}")
        lines.append(f"- Overall Status: {snapshot.get('overall_status')}")
        lines.append(f"- Strategy: {s.get('strategy_code')} / {s.get('strategy_version_code')} / strategy_version_id={s.get('strategy_version_id')}")
        lines.append(f"- Source Signal Run: {s.get('source_signal_run_id')}")
        lines.append(f"- Production Allowed: {s.get('production_allowed')}")
        lines.append("")
        lines.append("## 1. 当前结论")
        lines.append("")
        lines.append("- 链路已经打通：M4 signal → M5 controlled backtest → M9 research insight。")
        lines.append("- 状态机版本已经解决 raw_market_regime 日级跳变导致的策略路由不稳定问题。")
        lines.append("- 当前收益、回撤、Sharpe 仍不支持进入 M6 或生产端。")
        lines.append(f"- Gate Decision: can_enter_m6={gate.get('can_enter_m6')}, can_publish_to_production={gate.get('can_publish_to_production')}。")
        lines.append("")
        lines.append("## 2. 市场状态与策略路由")
        lines.append("")
        lines.append(f"- 最新 as_of_date: {r.get('latest_signal_as_of_date') or 'N/A'}")
        lines.append(f"- raw_market_regime: {r.get('latest_raw_market_regime') or 'N/A'}")
        lines.append(f"- confirmed_market_regime: {r.get('latest_confirmed_market_regime') or 'N/A'}")
        lines.append(f"- route_name: {r.get('latest_route_name') or 'N/A'}")
        lines.append(f"- regime_days_in_state: {r.get('latest_regime_days_in_state') or 'N/A'}")
        lines.append(f"- raw_transition_count: {r.get('raw_transition_count') or 'N/A'}")
        lines.append(f"- confirmed_transition_count: {r.get('confirmed_transition_count') or 'N/A'}")
        lines.append("")
        lines.append("### 状态分段")
        for seg in (r.get("segments") or [])[:12]:
            lines.append(f"- {seg.get('confirmed_market_regime')}: {seg.get('start_date')} ~ {seg.get('end_date')}，{seg.get('signal_day_count')} 个信号日，route={seg.get('route_name')}")
        lines.append("")
        lines.append("## 3. 行业与信号样例")
        lines.append("")
        for row in snapshot.get("industry_focus") or []:
            lines.append(f"- {row.get('industry')}: latest_top20_count={row.get('selected_count_in_latest_top20')}，avg_industry_strength_20={row.get('avg_industry_strength_20') or 'N/A'}")
        lines.append("")
        lines.append("### 最新 Top 信号")
        for row in snapshot.get("top_signals") or []:
            lines.append(f"- #{row.get('rank_in_batch')} {row.get('instrument_code')} {row.get('display_name') or ''}｜行业={row.get('industry') or 'N/A'}｜score={row.get('normalized_score') or 'N/A'}｜route={row.get('route_name') or 'N/A'}")
        lines.append("")
        lines.append("## 4. 回测表现")
        lines.append("")
        lines.append(f"- run_id: {b.get('run_id')}")
        lines.append(f"- backtest_request_id: {b.get('backtest_request_id')}")
        lines.append(f"- execution_mode: {b.get('execution_mode')}")
        lines.append(f"- period: {b.get('start_date')} ~ {b.get('end_date')}，trading_days={b.get('trading_days')}")
        lines.append(f"- final_equity: {_fmt_money(b.get('final_equity'))}")
        lines.append(f"- total_return: {_fmt_pct(b.get('total_return'), signed=True)}")
        lines.append(f"- annual_return: {_fmt_pct(b.get('annual_return'), signed=True)}")
        lines.append(f"- max_drawdown: {_fmt_pct(b.get('max_drawdown'), signed=True)}")
        lines.append(f"- sharpe_ratio: {_fmt_metric(b.get('sharpe_ratio'))}")
        lines.append(f"- volatility: {_fmt_pct(b.get('volatility'))}")
        lines.append("")
        if comp.get("status") == "OK":
            lines.append("## 5. 与上一研究版本对比")
            lines.append("")
            lines.append(f"- previous_run_id: {comp.get('previous_run_id')}，previous_version={comp.get('previous_strategy_version_code')}")
            lines.append(f"- total_return: {_fmt_pct(comp.get('previous_total_return'), signed=True)} → {_fmt_pct(comp.get('current_total_return'), signed=True)}，delta={_fmt_pct(comp.get('delta_total_return'), signed=True)}")
            lines.append(f"- max_drawdown: {_fmt_pct(comp.get('previous_max_drawdown'), signed=True)} → {_fmt_pct(comp.get('current_max_drawdown'), signed=True)}，delta={_fmt_pct(comp.get('delta_max_drawdown'), signed=True)}")
            lines.append(f"- sharpe_ratio: {_fmt_metric(comp.get('previous_sharpe_ratio'))} → {_fmt_metric(comp.get('current_sharpe_ratio'))}，delta={_fmt_metric(comp.get('delta_sharpe_ratio'))}")
            lines.append("")
        lines.append("## 6. 风险与 WARN")
        lines.append("")
        lines.append(f"- quality_warning_codes: {', '.join(str(x) for x in d.get('quality_warning_codes') or []) or 'N/A'}")
        stats = d.get("preview_warning_stats") or {}
        lines.append(f"- zero_lot_skipped: {stats.get('zero_lot_skipped') or 0} / target_rows={stats.get('target_rows') or 0}，zero_lot_rate={_fmt_pct(d.get('zero_lot_rate'))}")
        lines.append(f"- missing_exit_date_skipped: {stats.get('missing_exit_date_skipped') or 0}")
        lines.append(f"- performance_claim_allowed: {d.get('performance_claim_allowed')}")
        lines.append("")
        lines.append("## 7. 当前参数在哪里改")
        lines.append("")
        lines.append("详见同目录 `_parameters.csv`。参数修改必须复制为新的 strategy_version 后重跑完整研究链路，不能直接覆盖当前版本。")
        lines.append("")
        lines.append("## 8. 下一步实验候选")
        lines.append("")
        for row in snapshot.get("next_experiments") or []:
            lines.append(f"- [{row.get('priority')}] {row.get('experiment_code')}：{row.get('what_to_change')} 验证方式：{row.get('how_to_validate')}")
        lines.append("")
        lines.append("## 9. 生产端门禁")
        lines.append("")
        lines.append(f"- can_enter_m6: {gate.get('can_enter_m6')}")
        lines.append(f"- can_publish_to_production: {gate.get('can_publish_to_production')}")
        lines.append(f"- reason: {gate.get('reason')}")
        return "\n".join(lines).rstrip() + "\n"

    def _write_rows(self, path: Path, rows: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        normalized = [_to_jsonable(row) for row in rows]
        fieldnames: list[str] = []
        for row in normalized:
            for key in row.keys():
                if key not in fieldnames:
                    fieldnames.append(key)
        if not fieldnames:
            fieldnames = ["status", "message"]
            normalized = [{"status": "EMPTY", "message": "no rows"}]
        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in normalized:
                safe_row = {}
                for key in fieldnames:
                    value = row.get(key, "")
                    if isinstance(value, (dict, list)):
                        value = json.dumps(value, ensure_ascii=False)
                    safe_row[key] = value
                writer.writerow(safe_row)


class ResearchPortfolioDailyReportExporter:
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)

    def export(self, report: ResearchPortfolioDailyReport) -> dict[str, Path]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        stem = f"m9_research_portfolio_daily_p1_{report.report_date}"
        paths = {
            "markdown": self.output_dir / f"{stem}.md",
            "json": self.output_dir / f"{stem}.json",
            "selected_stocks_csv": self.output_dir / f"{stem}_selected_stocks.csv",
            "position_summary_csv": self.output_dir / f"{stem}_position_summary.csv",
            "action_items_csv": self.output_dir / f"{stem}_action_items.csv",
            "sources_csv": self.output_dir / f"{stem}_sources.csv",
        }
        paths["markdown"].write_text(self._to_markdown(report), encoding="utf-8")
        paths["json"].write_text(
            json.dumps(_to_jsonable(self._to_dict(report)), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._write_rows(paths["selected_stocks_csv"], report.selected_stocks)
        self._write_rows(paths["position_summary_csv"], report.position_summary_rows)
        self._write_rows(paths["action_items_csv"], report.action_items)
        self._write_rows(paths["sources_csv"], [s.__dict__ for s in report.sources])
        return paths

    def _to_dict(self, report: ResearchPortfolioDailyReport) -> dict[str, Any]:
        return {
            "report_date": report.report_date,
            "generated_at": report.generated_at,
            "scope": report.scope,
            "overall_status": report.overall_status,
            "sections": [s.__dict__ for s in report.sections],
            "selected_stocks": report.selected_stocks,
            "position_summary_rows": report.position_summary_rows,
            "action_items": report.action_items,
            "sources": [s.__dict__ for s in report.sources],
            "facts": report.facts,
        }

    def _to_markdown(self, report: ResearchPortfolioDailyReport) -> str:
        lines: list[str] = []
        lines.append(f"# M9.1.1-B 专业版市场 / 策略 / 组合日报")
        lines.append("")
        lines.append(f"- Report Date: {report.report_date}")
        lines.append(f"- Generated At: {report.generated_at}")
        lines.append(f"- Scope: {report.scope}")
        lines.append(f"- Overall Status: {report.overall_status}")
        layers = report.facts.get("status_layers") or {}
        if layers:
            lines.append(f"- DATA_STATUS: {layers.get('DATA_STATUS') or 'N/A'}")
            lines.append(f"- RESEARCH_STATUS: {layers.get('RESEARCH_STATUS') or 'N/A'}")
            lines.append(f"- PORTFOLIO_STATUS: {layers.get('PORTFOLIO_STATUS') or 'N/A'}")
            lines.append(f"- CAMPAIGN_STATUS: {layers.get('CAMPAIGN_STATUS') or 'N/A'}")
            lines.append(f"- RISK_REVIEW_STATUS: {layers.get('RISK_REVIEW_STATUS') or 'N/A'}")
            lines.append(f"- FINAL_REVIEW_CONCLUSION: {layers.get('FINAL_REVIEW_CONCLUSION') or 'N/A'}")
        lines.append("")
        for section in report.sections:
            lines.append(f"## {section.section_id}. {section.title}")
            lines.append("")
            lines.append(f"- Status: {section.status}")
            lines.append(f"- Summary: {section.summary}")
            lines.append("")
            if section.details:
                lines.append("### Details")
                lines.append("")
                for detail in section.details:
                    lines.append(f"- {detail}")
                lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def _write_rows(self, path: Path, rows: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        normalized = [_to_jsonable(row) for row in rows]
        fieldnames: list[str] = []
        for row in normalized:
            for key in row.keys():
                if key not in fieldnames:
                    fieldnames.append(key)
        if not fieldnames:
            fieldnames = ["status", "message"]
            normalized = [{"status": "EMPTY", "message": "no rows"}]
        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in normalized:
                safe_row = {}
                for key in fieldnames:
                    value = row.get(key, "")
                    if isinstance(value, (dict, list)):
                        value = json.dumps(value, ensure_ascii=False)
                    safe_row[key] = value
                writer.writerow(safe_row)

class ProductionObservationReportExporter(ResearchPortfolioDailyReportExporter):
    """Export the research/portfolio report as a production observation report MVP.

    This exporter deliberately reuses the existing M9 research portfolio daily
    report facts instead of creating a parallel reporting framework. The output
    is artifact-only: it does not write DB rows, create trading signals, route to
    M6, or authorize live trading.
    """

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)

    def export(self, report: ResearchPortfolioDailyReport) -> dict[str, Path]:
        by_date_dir = self.output_dir / "by_date" / report.report_date
        latest_dir = self.output_dir / "latest"
        sections_dir = by_date_dir / "sections"
        latest_sections_dir = latest_dir / "sections"
        for path in (by_date_dir, latest_dir, sections_dir, latest_sections_dir):
            path.mkdir(parents=True, exist_ok=True)

        payload = self._build_payload(report)
        markdown = self._to_production_observation_markdown(payload)

        dated_md = by_date_dir / "production_observation_report.md"
        dated_json = by_date_dir / "production_observation_report.json"
        latest_md = latest_dir / "production_observation_report_latest.md"
        latest_json = latest_dir / "production_observation_report_latest.json"

        dated_md.write_text(markdown, encoding="utf-8")
        latest_md.write_text(markdown, encoding="utf-8")
        dated_json.write_text(json.dumps(_to_jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8")
        latest_json.write_text(json.dumps(_to_jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8")

        section_outputs = self._write_section_csvs(payload, sections_dir)
        latest_section_outputs = self._write_section_csvs(payload, latest_sections_dir)

        outputs: dict[str, Path] = {
            "production_observation_markdown": dated_md,
            "production_observation_json": dated_json,
            "production_observation_latest_markdown": latest_md,
            "production_observation_latest_json": latest_json,
        }
        outputs.update({f"production_observation_section_{k}": v for k, v in section_outputs.items()})
        outputs.update({f"production_observation_latest_section_{k}": v for k, v in latest_section_outputs.items()})
        return outputs

    def _build_payload(self, report: ResearchPortfolioDailyReport) -> dict[str, Any]:
        facts = report.facts or {}
        selected = facts.get("selected") or {}
        portfolio = facts.get("portfolio") or {}
        positions = facts.get("positions") or {}
        market = facts.get("market") or {}
        db_market = facts.get("db_market") or {}
        risk = facts.get("risk") or {}
        backtest = facts.get("backtest") or {}
        strategy = facts.get("strategy") or {}
        status_layers = facts.get("status_layers") or {}

        gates = [
            {
                "gate": "can_publish_report_to_production",
                "value": True,
                "status": "PASS",
                "reason": "This is an observation/report artifact and can be published to production.",
            },
            {
                "gate": "can_publish_strategy_to_production",
                "value": False,
                "status": "BLOCKED",
                "reason": "Strategy has not passed M6 promotion gates; report is not strategy productionization.",
            },
            {
                "gate": "can_route_to_m6",
                "value": False,
                "status": "BLOCKED",
                "reason": "M6 requires full sample-out validation, attribution, drawdown/Sharpe/cost gates, and human review.",
            },
            {
                "gate": "can_trade_live",
                "value": False,
                "status": "BLOCKED",
                "reason": "This stage is paper/observation only and must not trigger live trading.",
            },
            {
                "gate": "needs_research_review",
                "value": True,
                "status": "REQUIRED",
                "reason": "The report is intended to reveal research follow-up items before any promotion decision.",
            },
        ]

        data_sources = [
            {
                "layer": "L0_data_quality",
                "dataset": "core_daily_bar/core_adjust_factor/core_price_limit_daily/core_instrument_status_daily",
                "status": "READY_OR_SYNCED",
                "usage": "Data freshness, tradability, ST/suspension/listing status and limit checks.",
            },
            {
                "layer": "L1_market_state",
                "dataset": "market_index_bar",
                "status": "READY_OR_SYNCED",
                "usage": "Index and market regime context.",
            },
            {
                "layer": "L2_risk_budget",
                "dataset": "risk/execution policy artifacts",
                "status": "PARTIAL_READY",
                "usage": "Position cap, cash preference and new-entry allowance display.",
            },
            {
                "layer": "L3_strategy_allocator",
                "dataset": "candidate_strategy_policies / strategy artifacts",
                "status": "PARTIAL_READY",
                "usage": "Strategy enable/disable/observation-only display.",
            },
            {
                "layer": "L4_market_breadth",
                "dataset": "core_market_breadth",
                "status": "READY_OR_SYNCED",
                "usage": "Breadth, limit structure and market赚钱效应.",
            },
            {
                "layer": "L5_liquidity_volatility",
                "dataset": "feat_tradability_score / feat_volatility_rank_20 / amount / turnover proxy",
                "status": "PARTIAL_READY",
                "usage": "Trading difficulty, liquidity shrinkage and volatility environment.",
            },
            {
                "layer": "L6_industry_structure",
                "dataset": "industry features / candidate industry tags",
                "status": "PARTIAL_READY",
                "usage": "Industry strength, concentration and industry exposure.",
            },
            {
                "layer": "L7_concept_theme",
                "dataset": "concept_strength / capital_flow",
                "status": "NOT_READY_STAGE7_BACKLOG",
                "usage": "Displayed as readiness gap only; not used for buy/sell decisions in this MVP.",
            },
            {
                "layer": "L8_style_environment",
                "dataset": "feat_mom_20 / feat_trend_strength_20 / feat_volatility_rank_20",
                "status": "PARTIAL_READY",
                "usage": "Style proxy and factor tailwind/headwind.",
            },
            {
                "layer": "L9_portfolio_exposure",
                "dataset": "paper portfolio / dry-run / position lifecycle artifacts",
                "status": "PARTIAL_READY",
                "usage": "Paper exposure, cash, concentration and PnL display.",
            },
        ]

        executive_summary = {
            "report_date": report.report_date,
            "generated_at": report.generated_at,
            "overall_status": report.overall_status,
            "scope": "Production Observation Report MVP",
            "market_status": (market.get("status") or db_market.get("status") or "UNKNOWN"),
            "strategy_code": strategy.get("strategy_code"),
            "strategy_version_code": strategy.get("version_code"),
            "selected_count": selected.get("selected_count") or selected.get("target_count") or len(report.selected_stocks),
            "position_count": positions.get("position_count") or len(report.position_summary_rows),
            "cash": portfolio.get("cash"),
            "total_equity": portfolio.get("total_equity"),
            "total_return": backtest.get("total_return"),
            "max_drawdown": backtest.get("max_drawdown"),
            "risk_status": risk.get("status"),
            "final_review_conclusion": status_layers.get("FINAL_REVIEW_CONCLUSION"),
        }

        return {
            "stage": "Stage 6.17c",
            "name": "production_observation_report_mvp",
            "report_date": report.report_date,
            "generated_at": _utc_now_iso(),
            "artifact_only": True,
            "not_m6": True,
            "not_stage7": True,
            "db_write_rows": 0,
            "can_trade_live": False,
            "gates": gates,
            "executive_summary": executive_summary,
            "data_sources": data_sources,
            "status_layers": status_layers,
            "sections": [s.__dict__ for s in report.sections],
            "selected_stocks": report.selected_stocks,
            "position_summary_rows": report.position_summary_rows,
            "action_items": report.action_items,
            "sources": [s.__dict__ for s in report.sources],
            "facts": facts,
        }

    def _write_section_csvs(self, payload: dict[str, Any], sections_dir: Path) -> dict[str, Path]:
        outputs = {
            "gates_csv": sections_dir / "gates.csv",
            "data_sources_csv": sections_dir / "data_sources.csv",
            "selected_stocks_csv": sections_dir / "selected_stocks.csv",
            "position_summary_csv": sections_dir / "position_summary.csv",
            "action_items_csv": sections_dir / "action_items.csv",
            "sources_csv": sections_dir / "sources.csv",
            "status_layers_csv": sections_dir / "status_layers.csv",
        }
        self._write_rows(outputs["gates_csv"], payload.get("gates") or [])
        self._write_rows(outputs["data_sources_csv"], payload.get("data_sources") or [])
        self._write_rows(outputs["selected_stocks_csv"], payload.get("selected_stocks") or [])
        self._write_rows(outputs["position_summary_csv"], payload.get("position_summary_rows") or [])
        self._write_rows(outputs["action_items_csv"], payload.get("action_items") or [])
        self._write_rows(outputs["sources_csv"], payload.get("sources") or [])
        status_rows = [
            {"status_layer": key, "value": value}
            for key, value in sorted((payload.get("status_layers") or {}).items())
        ]
        self._write_rows(outputs["status_layers_csv"], status_rows)
        return outputs

    def _to_production_observation_markdown(self, payload: dict[str, Any]) -> str:
        summary = payload.get("executive_summary") or {}
        lines: list[str] = [
            "# Production Observation Report MVP",
            "",
            f"- Report Date: {payload.get('report_date')}",
            f"- Generated At: {payload.get('generated_at')}",
            "- Stage: Stage 6.17c",
            "- Artifact Only: true",
            "- Not M6: true",
            "- Not Stage 7: true",
            "- Can Trade Live: false",
            "- DB Write Rows: 0",
            "",
            "## Executive Summary",
            "",
            f"- Overall Status: {summary.get('overall_status') or 'UNKNOWN'}",
            f"- Market Status: {summary.get('market_status') or 'UNKNOWN'}",
            f"- Strategy: {summary.get('strategy_code') or 'UNKNOWN'} / {summary.get('strategy_version_code') or 'UNKNOWN'}",
            f"- Selected Count: {summary.get('selected_count') or 0}",
            f"- Position Count: {summary.get('position_count') or 0}",
            f"- Cash: {_fmt_money(summary.get('cash'))}",
            f"- Total Equity: {_fmt_money(summary.get('total_equity'))}",
            f"- Backtest Total Return: {_fmt_pct(summary.get('total_return'), signed=True)}",
            f"- Backtest Max Drawdown: {_fmt_pct(summary.get('max_drawdown'))}",
            f"- Final Review: {summary.get('final_review_conclusion') or 'N/A'}",
            "",
            "## Gates",
            "",
        ]
        for gate in payload.get("gates") or []:
            lines.append(
                f"- {gate.get('gate')}: `{gate.get('value')}` / {gate.get('status')} — {gate.get('reason')}"
            )

        lines.extend(["", "## L0-L9 Data Sources", ""])
        for item in payload.get("data_sources") or []:
            lines.append(
                f"- {item.get('layer')} / {item.get('dataset')}: `{item.get('status')}` — {item.get('usage')}"
            )

        lines.extend(["", "## Report Sections", ""])
        for section in payload.get("sections") or []:
            lines.append(
                f"- {section.get('section_id')} / {section.get('title')}: `{section.get('status')}` — {section.get('summary')}"
            )

        lines.extend([
            "",
            "## Boundary",
            "",
            "This report is for production-side observation and paper review only. It must not be used as an M6 promotion decision, live-trading signal, or unattended execution approval.",
            "",
        ])
        return "\n".join(lines).rstrip() + "\n"

