from __future__ import annotations

import csv
import json
import math
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

        m3 = _read_json(m3_path)
        m4 = _read_json(m4_path)
        m5 = _read_json(m5_path)
        daily_ops = _read_json(daily_ops_path)
        paper_chain = _read_json(paper_chain_path)
        portfolio_snapshot = _read_json(portfolio_snapshot_path)
        risk = _read_json(risk_path)
        alert = _read_json(alert_path)

        selected_rows = _read_csv_rows(paper_targets_path)
        if not selected_rows:
            selected_rows = self._load_selected_stock_rows_from_db(daily_ops, paper_chain, report_date)
        position_rows = _read_csv_rows(paper_positions_path)
        snapshot_csv_rows = _read_csv_rows(portfolio_snapshot_csv_path)

        strategy_fact = self._extract_strategy(m4)
        backtest_fact = self._extract_backtest(m5, daily_ops)
        portfolio_fact = self._extract_portfolio(daily_ops, paper_chain, portfolio_snapshot, snapshot_csv_rows)
        risk_fact = self._extract_risk(risk, daily_ops, alert)
        market_fact = self._extract_market(m3)
        db_market_fact = self._try_extract_market_from_db()
        selected_stock_rows = self._normalize_selected_stock_rows(selected_rows)
        selected_fact = self._extract_selected_stocks(selected_stock_rows, paper_chain)
        position_fact = self._extract_positions(position_rows, portfolio_fact)

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
            return None
        candidates.sort(key=lambda path: (str(path), path.stat().st_mtime), reverse=True)
        path = candidates[0]
        self.sources.append(
            ReportSource(
                source_code,
                str(path.relative_to(self.repo_root)),
                "USED",
                f"latest matching artifact from pattern: {selected_pattern}",
            )
        )
        return path

    def _extract_strategy(self, m4: dict[str, Any]) -> dict[str, Any]:
        strategies = m4.get("strategies") or []
        versions = m4.get("versions") or []
        schemas = m4.get("schemas") or []
        strategy = strategies[0] if strategies else {}
        version = next((v for v in versions if v.get("is_current") is True), versions[0] if versions else {})
        schema = schemas[0] if schemas else {}
        example = schema.get("example_payload_json") or {}
        return {
            "status": m4.get("status") or ("OK" if strategies else "MISSING"),
            "strategy_code": strategy.get("strategy_code"),
            "strategy_name": strategy.get("strategy_name"),
            "strategy_type": strategy.get("strategy_type"),
            "engine_type": strategy.get("engine_type"),
            "version_code": version.get("version_code"),
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
        }

    def _extract_backtest(self, m5: dict[str, Any], daily_ops: dict[str, Any]) -> dict[str, Any]:
        latest = m5.get("latest_result") or (daily_ops.get("m5_backtest") or {})
        result_summary = latest.get("result_summary") or {}
        return {
            "status": m5.get("status") or daily_ops.get("m5_backtest", {}).get("overall_status"),
            "run_id": m5.get("latest_run_id") or latest.get("run_id"),
            "backtest_request_id": m5.get("backtest_request_id") or latest.get("backtest_request_id"),
            "execution_mode": m5.get("execution_mode") or daily_ops.get("m5_backtest", {}).get("execution_mode") or result_summary.get("execution_mode"),
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
            "message": daily_ops.get("m5_backtest", {}).get("message") or m5.get("human_summary"),
            "stage": result_summary.get("stage"),
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

        data_status = "OK"
        if _is_warnish_status(market.get("status")) or _is_warnish_status(db_market.get("status")):
            data_status = "WARN"
        if selected.get("identity_missing_count"):
            data_status = "WARN"

        research_status = "OK" if not _is_warnish_status(backtest.get("status")) else "WARN"
        portfolio_status = "OK" if portfolio.get("total_equity") else "WARN"
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
        elif "WARN" in {data_status, research_status, portfolio_status, risk_review_status}:
            final = "WARN，谨慎参考，需要人工复核后使用。"

        return {
            "DATA_STATUS": data_status,
            "RESEARCH_STATUS": research_status,
            "PORTFOLIO_STATUS": portfolio_status,
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

        def add(priority: str, category: str, item: str, reason: str, suggested_action: str, source: str) -> None:
            flags.append({
                "priority": priority,
                "category": category,
                "item": item,
                "reason": reason,
                "suggested_action": suggested_action,
                "source": source,
            })

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

        if _is_warnish_status(backtest.get("status")):
            add(
                "P1", "回测", f"回测状态 {backtest.get('status') or 'N/A'}",
                "当前回测结果可读，但尚不能直接视为生产级实盘执行结论。",
                "确认 HISTORICAL_SIGNAL_REPLAY_P1 是否已作为正式研究回测链使用。",
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
        layers = facts.get("status_layers") or {}
        details = [
            f"报告生成日：{facts.get('report_date') or 'N/A'}。",
            f"组合快照日：{portfolio.get('snapshot_date') or 'N/A'}。",
            f"目标仓位日期：as_of_date={self._selected_date(selected, 'as_of_date')}，effective_date={self._selected_date(selected, 'effective_date')}。",
            f"最新信号水位：as_of_date={strategy.get('signal_latest_as_of_date') or 'N/A'}，effective_date={strategy.get('signal_latest_effective_date') or 'N/A'}。",
            f"回测区间：{backtest.get('start_date') or 'N/A'} 至 {backtest.get('end_date') or 'N/A'}，run_id={backtest.get('run_id') or 'N/A'}。",
            f"风控决策日期：{risk.get('min_decision_date') or 'N/A'} 至 {risk.get('max_decision_date') or 'N/A'}。",
            "状态分层："
            f"DATA={layers.get('DATA_STATUS') or 'N/A'}，"
            f"RESEARCH={layers.get('RESEARCH_STATUS') or 'N/A'}，"
            f"PORTFOLIO={layers.get('PORTFOLIO_STATUS') or 'N/A'}，"
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
        layers = facts.get("status_layers") or {}
        flags = facts.get("review_flags") or []
        cash_ratio = _ratio(portfolio.get("cash_balance"), portfolio.get("total_equity"))
        summary = layers.get("FINAL_REVIEW_CONCLUSION") or "WARN，谨慎参考，需要人工复核后使用。"
        details = [
            f"当前策略：{strategy.get('strategy_code') or 'N/A'} / {strategy.get('version_code') or 'N/A'}。",
            f"目标股票：{selected.get('row_count') or selected.get('target_count') or 'N/A'} 只；组合持仓：{portfolio.get('holding_count') or portfolio.get('open_position_count') or 'N/A'} 只。",
            f"组合敞口：{_fmt_pct(portfolio.get('exposure_ratio'))}；现金占比：{_fmt_pct(cash_ratio)}。",
            f"回测表现：累计收益 {_fmt_pct(backtest.get('total_return'))}，最大回撤 {_fmt_pct(backtest.get('max_drawdown'), signed=True)}，Sharpe {_fmt_metric(backtest.get('sharpe_ratio'))}。",
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
            f"版本：{s.get('version_code') or 'N/A'}，输出契约={s.get('output_contract_version') or 'N/A'}。",
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
        if b.get("execution_mode"):
            details.append(
                f"解释：当前回测模式为 {b.get('execution_mode')}。若该模式仍属于历史信号回放验证，则本节用于研究参考，不能直接视为生产级实盘执行结论。"
            )
        elif b.get("message"):
            details.append(f"说明：{b.get('message')}")
        summary = "回测用于提供研究证据；P1 先展示核心收益风险指标，后续再补交易成本敏感性和收益归因。"
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
            "09",
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
            "本报告可作为 paper trading 复盘、人工检查和后续策略研究依据。",
            "本报告不应作为自动调仓、自动下单或无人值守执行依据。",
        ]
        if flags:
            details.append("建议优先处理 P0/P1 复核项，再决定是否采信本轮组合结论。")
        status = "WARN" if flags else "OK"
        return ReportSection("10", "结论与人工动作建议", status, "本节给出最终可采信程度和人工动作边界。", details)

    def _section_sources(self) -> ReportSection:
        used = [s for s in self.sources if s.status == "USED"]
        missing = [s for s in self.sources if s.status != "USED"]
        details = [f"已使用来源 {len(used)} 个，缺失/不可用来源 {len(missing)} 个。"]
        for src in self.sources:
            details.append(f"{src.status}: {src.source_code} -> {src.path or src.note}")
        return ReportSection("11", "来源文件与 run_id 血缘", "OK" if used else "WARN", "报告只基于已落地 artifact 和可选 DB 快照生成，保留完整来源索引。", details)

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
        return ReportSection("12", "附录索引", "OK", "本节列出本次报告同步输出的结构化附件。", details)

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
