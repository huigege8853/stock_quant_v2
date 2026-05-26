"""M5 adaptive execution dry-run skeleton.

This service is the V2 Stage-2 artifact-only execution lifecycle preview. It
consumes the Stage-1 adaptive execution policy design artifact plus a candidate
signal artifact and builds a deterministic dry-run package.

Guardrails:
- no database read/write;
- no Backtrader execution;
- no research_backtest_result write;
- no M6 paper routing;
- no performance claim;
- missing execution inputs block entries instead of being guessed.
"""

from __future__ import annotations

import csv
import json
import os
import uuid
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

STAGE = "M5_ADAPTIVE_EXECUTION_DRY_RUN"
SOURCE_STAGE = "M5_ADAPTIVE_EXECUTION_POLICY_DESIGN"
STRATEGY_CODE = "regime_sector_industry_selection_v1"
DEFAULT_CANDIDATE_POOL_PROVIDER_VERSION = "v1_regime_state_machine"
DEFAULT_POLICY_ARTIFACT_DIR = Path("artifacts") / "m5" / "adaptive_execution_design"
DEFAULT_CANDIDATE_SIGNAL_ARTIFACT_DIR = Path("artifacts") / "m4" / "historical_signal_generation_preview_v1_regime_state_machine"
DEFAULT_OUTPUT_DIR = Path("artifacts") / "m5" / "adaptive_execution_dry_run"

ACCEPTED_NOT_LIMIT_UP_STATUSES = {"NORMAL", "NOT_LIMIT_UP", "NO_LIMIT_UP", "TRADABLE", "OK", "未涨停"}
REJECTED_LIMIT_UP_STATUSES = {"LIMIT_UP", "UP_LIMIT", "涨停"}
FATAL_ENTRY_INPUT_REASONS = {
    "missing_execution_price",
    "missing_limit_status_not_guessing_not_limit_up",
    "unknown_limit_status_not_accepted",
}

OBSERVATION_ONLY_ENTRY_MODES = {"OBSERVATION_ONLY", "DISABLED", "BLOCKED", "NO_TRADE"}



R29_HISTORICAL_FALLBACK_BALANCED_ROUTE_MATCH_MARKER = "R29_HISTORICAL_FALLBACK_BALANCED_ROUTE_MATCH"


def _r29_env_flag(name: str, default: str = "0") -> bool:
    value = str(os.getenv(name, default) or "").strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


def _r29_historical_fallback_balanced_route_match_enabled() -> bool:
    return _r29_env_flag("SQV2_RESEARCH_M5_HISTORICAL_FALLBACK_BALANCED_ROUTE_MATCH", "0")

R27_HISTORICAL_UNKNOWN_REGIME_RISK_BUDGET_FALLBACK_MARKER = "R27_HISTORICAL_UNKNOWN_REGIME_RISK_BUDGET_FALLBACK"


def _r27_env_flag(name: str, default: str = "0") -> bool:
    value = str(os.getenv(name, default) or "").strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


def _r27_unknown_regime_risk_budget_fallback_enabled() -> bool:
    return _r27_env_flag("SQV2_RESEARCH_M5_UNKNOWN_REGIME_RISK_BUDGET_FALLBACK", "0")


def _r27_unknown_regime_risk_budget_fallback_key() -> str:
    return str(os.getenv("SQV2_RESEARCH_M5_UNKNOWN_REGIME_RISK_BUDGET_FALLBACK_KEY", "RANGE") or "RANGE").strip().upper()


DAILY_PORTFOLIO_COLUMNS = (
    "trade_date",
    "confirmed_market_regime",
    "total_position_cap",
    "max_new_positions_per_day",
    "begin_cash",
    "sell_notional",
    "buy_notional",
    "transaction_cost",
    "ending_cash",
    "gross_exposure",
    "total_equity",
    "position_count",
    "industry_exposure_json",
    "sell_before_buy_verified",
    "cash_non_negative",
    "position_cap_ok",
    "industry_cap_ok",
    "status",
    "detail",
)
TRADE_LOG_COLUMNS = (
    "trade_id",
    "trade_date",
    "sequence_no",
    "instrument_code",
    "display_name",
    "side",
    "quantity",
    "price",
    "notional",
    "transaction_cost",
    "cash_after",
    "entry_reason",
    "exit_reason",
    "exit_type",
    "holding_days",
    "max_floating_profit",
    "max_floating_loss",
    "confirmed_market_regime",
    "route_name",
    "candidate_strategy_code",
    "candidate_strategy_name",
    "candidate_strategy_bucket",
    "candidate_strategy_score",
    "industry_tag_name",
    "status",
    "detail",
)
POSITION_LIFECYCLE_COLUMNS = (
    "position_id",
    "instrument_code",
    "display_name",
    "industry_tag_name",
    "candidate_strategy_code",
    "candidate_strategy_name",
    "candidate_strategy_bucket",
    "candidate_strategy_score",
    "entry_date",
    "exit_date",
    "quantity",
    "entry_price",
    "exit_price",
    "entry_notional",
    "exit_notional",
    "realized_pnl",
    "realized_return",
    "holding_days",
    "max_floating_profit",
    "max_floating_loss",
    "entry_reason",
    "exit_reason",
    "exit_type",
    "status",
)
REASON_SUMMARY_COLUMNS = ("reason", "status", "count", "detail")
REGIME_PERFORMANCE_COLUMNS = (
    "confirmed_market_regime",
    "trade_count",
    "realized_pnl",
    "realized_return",
    "avg_holding_days",
    "status",
    "detail",
)
INDUSTRY_PERFORMANCE_COLUMNS = (
    "industry_tag_name",
    "trade_count",
    "realized_pnl",
    "realized_return",
    "avg_holding_days",
    "status",
    "detail",
)
STRATEGY_PERFORMANCE_COLUMNS = (
    "candidate_strategy_code",
    "trade_count",
    "realized_pnl",
    "realized_return",
    "avg_holding_days",
    "status",
    "detail",
)
CONTRACT_CHECK_COLUMNS = ("check_name", "status", "row_count", "detail")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat(timespec="seconds")


def json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return str(value)


def parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if value is None:
        return None
    text_value = str(value).strip()
    if not text_value:
        return None
    try:
        return date.fromisoformat(text_value[:10])
    except Exception:
        return None


def to_decimal(value: Any) -> Decimal | None:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return None
    text_value = str(value).strip()
    if not text_value:
        return None
    try:
        return Decimal(text_value)
    except Exception:
        return None


def decimal_or_zero(value: Any) -> Decimal:
    return to_decimal(value) or Decimal("0")


def safe_int(value: Any) -> int | None:
    if value is None:
        return None
    text_value = str(value).strip()
    if not text_value:
        return None
    try:
        return int(Decimal(text_value))
    except Exception:
        return None


def quantize_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.000001"))


def quantize_ratio(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0000000001"))


def status_from_checks(rows: Sequence[Mapping[str, Any]]) -> str:
    statuses = {str(row.get("status") or "").upper() for row in rows}
    if "FAIL" in statuses:
        return "FAIL"
    if "WARN" in statuses:
        return "PASS_WITH_WARN"
    return "PASS"


def is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text_value = str(value).strip().lower()
    if not text_value:
        return False
    if text_value in {"true", "yes", "y", "pass", "ok"}:
        return True
    if text_value in {"false", "no", "n", "fail", "ng"}:
        return False
    parsed = to_decimal(text_value)
    if parsed is not None:
        return parsed > 0
    return False


def floor_to_board_lot(raw_shares: Decimal, board_lot_size: int) -> int:
    if raw_shares <= 0 or board_lot_size <= 0:
        return 0
    lots = (raw_shares / Decimal(board_lot_size)).to_integral_value(rounding=ROUND_DOWN)
    return int(lots) * board_lot_size


def normalize_regime(value: Any) -> str:
    regime = str(value or "").strip().upper()
    if regime in {"TREND", "RISK_ON", "TREND_ON"}:
        return "RISK_ON"
    if regime in {"RANGE", "NEUTRAL"}:
        return "RANGE"
    if regime == "RISK_OFF":
        return "RISK_OFF"
    return regime


def pick_first(row: Mapping[str, Any], names: Sequence[str]) -> Any:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip() != "":
            return value
    return None


@dataclass(slots=True)
class AdaptiveExecutionDryRunConfig:
    report_date: str
    policy_artifact_dir: Path = DEFAULT_POLICY_ARTIFACT_DIR
    candidate_signal_artifact_dir: Path = DEFAULT_CANDIDATE_SIGNAL_ARTIFACT_DIR
    output_dir: Path = DEFAULT_OUTPUT_DIR
    request_id: int = 47
    initial_cash: Decimal | None = None
    transaction_cost_bps: Decimal = Decimal("0")
    max_candidate_dates: int | None = None
    candidate_signal_csv: Path | None = None
    execution_price_column: str | None = None


@dataclass(slots=True)
class AdaptiveExecutionDryRunArtifacts:
    metrics_path: str
    markdown_path: str
    daily_portfolio_path: str
    trade_log_path: str
    position_lifecycle_path: str
    entry_reason_summary_path: str
    exit_reason_summary_path: str
    by_regime_performance_path: str
    by_industry_performance_path: str
    by_strategy_performance_path: str
    contract_checks_path: str


@dataclass(slots=True)
class _OpenPosition:
    position_id: str
    instrument_code: str
    display_name: str
    industry_tag_name: str
    entry_date: date
    quantity: int
    entry_price: Decimal
    entry_notional: Decimal
    entry_reason: str
    confirmed_market_regime: str
    route_name: str
    candidate_strategy_code: str = "UNKNOWN"
    candidate_strategy_name: str = ""
    candidate_strategy_bucket: str = ""
    candidate_strategy_score: str = ""
    max_floating_profit: Decimal = Decimal("0")
    max_floating_loss: Decimal = Decimal("0")
    last_price: Decimal | None = None
    max_price: Decimal | None = None


@dataclass(slots=True)
class AdaptiveExecutionDryRunResult:
    status: str
    generated_at: str
    report_date: str
    request_id: int
    stage: str
    source_stage: str
    metrics: dict[str, Any]
    validation_decision: dict[str, Any]
    contract_checks: list[dict[str, Any]]
    guardrails: list[str]
    daily_portfolio_rows: list[dict[str, Any]] = field(default_factory=list)
    trade_log_rows: list[dict[str, Any]] = field(default_factory=list)
    position_lifecycle_rows: list[dict[str, Any]] = field(default_factory=list)
    entry_reason_summary_rows: list[dict[str, Any]] = field(default_factory=list)
    exit_reason_summary_rows: list[dict[str, Any]] = field(default_factory=list)
    by_regime_performance_rows: list[dict[str, Any]] = field(default_factory=list)
    by_industry_performance_rows: list[dict[str, Any]] = field(default_factory=list)
    by_strategy_performance_rows: list[dict[str, Any]] = field(default_factory=list)
    artifacts: AdaptiveExecutionDryRunArtifacts | None = None

    def to_metrics_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "generated_at": self.generated_at,
            "report_date": self.report_date,
            "request_id": self.request_id,
            "stage": self.stage,
            "source_stage": self.source_stage,
            "metrics": self.metrics,
            "validation_decision": self.validation_decision,
            "contract_checks": self.contract_checks,
            "guardrails": self.guardrails,
            "artifacts": asdict(self.artifacts) if self.artifacts else None,
        }


@dataclass(slots=True)
class AdaptiveExecutionDryRunTaskResult:
    result: AdaptiveExecutionDryRunResult


class AdaptiveExecutionDryRunService:
    def dry_run(
        self,
        config: AdaptiveExecutionDryRunConfig,
        *,
        progress_callback: Callable[[str], None] | None = None,
    ) -> AdaptiveExecutionDryRunResult:
        progress = progress_callback or (lambda message: None)
        request_output_dir = Path(config.output_dir) / f"request_{config.request_id}"
        request_output_dir.mkdir(parents=True, exist_ok=True)
        progress(f"ADAPTIVE_EXECUTION_DRY_RUN_START request_id={config.request_id} output_dir={request_output_dir}")

        policy = self._load_policy(config)
        candidate_rows = self._load_candidate_rows(config)
        result = self.dry_run_from_rows(
            config=config,
            policy=policy,
            candidate_rows=candidate_rows,
            progress_callback=progress,
        )
        return self._write_artifacts(request_output_dir, result)

    def dry_run_from_rows(
        self,
        *,
        config: AdaptiveExecutionDryRunConfig,
        policy: Mapping[str, Any],
        candidate_rows: Sequence[Mapping[str, Any]],
        progress_callback: Callable[[str], None] | None = None,
    ) -> AdaptiveExecutionDryRunResult:
        progress = progress_callback or (lambda message: None)
        contract_checks = self._source_contract_checks(config=config, policy=policy, candidate_rows=candidate_rows)
        if config.initial_cash is None or config.initial_cash <= 0:
            contract_checks.append(self._check("initial_cash_required", "FAIL", "initial_cash must be explicitly provided for artifact-only dry-run; it is not guessed.", rows=0))
            result = self._empty_result(config, contract_checks)
            return result

        if not policy:
            result = self._empty_result(config, contract_checks)
            return result

        risk_budget_policy = policy.get("risk_budget_policy") if isinstance(policy.get("risk_budget_policy"), dict) else {}
        execution_policy = policy.get("execution_policy") if isinstance(policy.get("execution_policy"), dict) else {}
        portfolio_constraints = execution_policy.get("portfolio_constraints") if isinstance(execution_policy.get("portfolio_constraints"), dict) else {}
        exit_policy = execution_policy.get("exit_policy_v1") if isinstance(execution_policy.get("exit_policy_v1"), dict) else {}
        candidate_strategy_policies = self._candidate_strategy_policies(policy)
        market_structure_gate_policy = self._market_structure_gate_policy(policy)
        parameter_version_id = self._policy_parameter_version_id(policy)
        policy_effective_hash = self._policy_effective_hash(policy)

        cash = quantize_money(config.initial_cash)
        open_positions: dict[str, _OpenPosition] = {}
        closed_lifecycles: list[dict[str, Any]] = []
        trade_rows: list[dict[str, Any]] = []
        daily_rows: list[dict[str, Any]] = []
        entry_reason_counter: Counter[str] = Counter()
        entry_block_counter: Counter[str] = Counter()
        exit_reason_counter: Counter[str] = Counter()
        regime_realized: dict[str, dict[str, Decimal | int]] = defaultdict(lambda: {"trade_count": 0, "pnl": Decimal("0"), "notional": Decimal("0"), "holding_days": 0})
        industry_realized: dict[str, dict[str, Decimal | int]] = defaultdict(lambda: {"trade_count": 0, "pnl": Decimal("0"), "notional": Decimal("0"), "holding_days": 0})
        strategy_realized: dict[str, dict[str, Decimal | int]] = defaultdict(lambda: {"trade_count": 0, "pnl": Decimal("0"), "notional": Decimal("0"), "holding_days": 0})

        rows_by_date = self._group_candidate_rows_by_effective_date(candidate_rows)
        if config.max_candidate_dates is not None:
            rows_by_date = dict(list(rows_by_date.items())[: config.max_candidate_dates])

        max_total_positions = safe_int(portfolio_constraints.get("max_total_positions")) or 0
        single_position_weight = decimal_or_zero(portfolio_constraints.get("single_position_weight"))
        max_industry_weight = decimal_or_zero(portfolio_constraints.get("max_industry_weight"))
        min_cash_reserve = decimal_or_zero(portfolio_constraints.get("min_cash_reserve"))
        board_lot_size = safe_int(portfolio_constraints.get("order_round_lot")) or 100
        hard_stop_loss = decimal_or_zero(exit_policy.get("hard_stop_loss"))
        max_holding_days = safe_int(exit_policy.get("max_holding_days")) or 20
        trailing_profit_start = decimal_or_zero(exit_policy.get("trailing_profit_start"))
        trailing_profit_drawdown = decimal_or_zero(exit_policy.get("trailing_profit_drawdown"))

        for trade_date, day_rows in rows_by_date.items():
            regime = normalize_regime(pick_first(day_rows[0], ["confirmed_market_regime", "market_regime", "market_regime_display"]))
            execution_regime = regime
            risk_budget = risk_budget_policy.get(regime) if isinstance(risk_budget_policy.get(regime), dict) else {}
            if (not risk_budget) and _r27_unknown_regime_risk_budget_fallback_enabled():
                fallback_regime = _r27_unknown_regime_risk_budget_fallback_key()
                fallback_budget = risk_budget_policy.get(fallback_regime)
                if isinstance(fallback_budget, dict):
                    risk_budget = fallback_budget
                    execution_regime = fallback_regime
            total_position_cap = decimal_or_zero(risk_budget.get("total_position_cap"))
            max_new_positions_per_day = safe_int(risk_budget.get("max_new_positions_per_day")) or 0
            begin_cash = cash
            sell_notional = Decimal("0")
            buy_notional = Decimal("0")
            transaction_cost = Decimal("0")
            sequence = 0

            # Step 1: update floating P/L from same-day candidate prices where available.
            price_by_symbol = {str(row.get("instrument_code") or row.get("subject_key") or ""): self._extract_execution_price(row, config.execution_price_column) for row in day_rows}
            for symbol, position in list(open_positions.items()):
                current_price = price_by_symbol.get(symbol) or position.last_price or position.entry_price
                self._update_position_float(position, current_price)

            # Step 2: sell before buy.
            for symbol, position in list(open_positions.items()):
                current_price = price_by_symbol.get(symbol) or position.last_price or position.entry_price
                exit_reason = self._resolve_exit_reason(
                    position=position,
                    trade_date=trade_date,
                    current_regime=regime,
                    current_price=current_price,
                    hard_stop_loss=hard_stop_loss,
                    max_holding_days=max_holding_days,
                    trailing_profit_start=trailing_profit_start,
                    trailing_profit_drawdown=trailing_profit_drawdown,
                )
                if not exit_reason:
                    continue
                sequence += 1
                notional = quantize_money(Decimal(position.quantity) * current_price)
                cost = self._estimate_transaction_cost(notional, config.transaction_cost_bps)
                cash = quantize_money(cash + notional - cost)
                sell_notional += notional
                transaction_cost += cost
                holding_days = max((trade_date - position.entry_date).days, 0)
                realized_pnl = quantize_money(notional - position.entry_notional - cost)
                realized_return = quantize_ratio(realized_pnl / position.entry_notional) if position.entry_notional > 0 else Decimal("0")
                exit_reason_counter[exit_reason] += 1
                trade_rows.append(
                    self._trade_row(
                        trade_date=trade_date,
                        sequence_no=sequence,
                        position=position,
                        side="SELL",
                        quantity=position.quantity,
                        price=current_price,
                        notional=notional,
                        transaction_cost=cost,
                        cash_after=cash,
                        entry_reason=position.entry_reason,
                        exit_reason=exit_reason,
                        exit_type=exit_reason,
                        holding_days=holding_days,
                        confirmed_market_regime=regime,
                        status="PASS",
                        detail="sell_before_buy_exit_executed",
                    )
                )
                lifecycle = self._position_lifecycle_row(
                    position=position,
                    exit_date=trade_date,
                    exit_price=current_price,
                    exit_notional=notional,
                    realized_pnl=realized_pnl,
                    realized_return=realized_return,
                    holding_days=holding_days,
                    exit_reason=exit_reason,
                    exit_type=exit_reason,
                    status="CLOSED",
                )
                closed_lifecycles.append(lifecycle)
                regime_bucket = regime_realized[position.confirmed_market_regime]
                industry_bucket = industry_realized[position.industry_tag_name or "UNKNOWN"]
                strategy_bucket = strategy_realized[position.candidate_strategy_code or "UNKNOWN"]
                for bucket in (regime_bucket, industry_bucket, strategy_bucket):
                    bucket["trade_count"] = int(bucket["trade_count"]) + 1
                    bucket["pnl"] = Decimal(bucket["pnl"]) + realized_pnl
                    bucket["notional"] = Decimal(bucket["notional"]) + position.entry_notional
                    bucket["holding_days"] = int(bucket["holding_days"]) + holding_days
                del open_positions[symbol]

            # Step 3: buy after sells.
            new_positions = 0
            ranked_candidates = sorted(day_rows, key=lambda row: safe_int(row.get("rank_in_batch")) or 999999)
            for row in ranked_candidates:
                if new_positions >= max_new_positions_per_day:
                    entry_block_counter["max_new_positions_per_day_reached"] += 1
                    continue
                symbol = str(row.get("instrument_code") or row.get("subject_key") or "").strip()
                if not symbol or symbol in open_positions:
                    entry_block_counter["duplicate_or_missing_symbol"] += 1
                    continue
                gate_result = self._entry_gate_result(
                    row=row,
                    regime=execution_regime,
                    cash=cash,
                    open_positions=open_positions,
                    initial_cash=config.initial_cash,
                    total_position_cap=total_position_cap,
                    max_total_positions=max_total_positions,
                    single_position_weight=single_position_weight,
                    max_industry_weight=max_industry_weight,
                    min_cash_reserve=min_cash_reserve,
                    board_lot_size=board_lot_size,
                    execution_price_column=config.execution_price_column,
                    candidate_strategy_policies=candidate_strategy_policies,
                    market_structure_gate_policy=market_structure_gate_policy,
                )
                if gate_result["status"] != "PASS":
                    entry_block_counter[str(gate_result["reason"])] += 1
                    continue
                quantity = int(gate_result["quantity"])
                price = Decimal(str(gate_result["price"]))
                notional = quantize_money(Decimal(quantity) * price)
                cost = self._estimate_transaction_cost(notional, config.transaction_cost_bps)
                cash = quantize_money(cash - notional - cost)
                buy_notional += notional
                transaction_cost += cost
                sequence += 1
                entry_reason = str(gate_result["entry_reason"])
                entry_reason_counter[entry_reason] += 1
                position = _OpenPosition(
                    position_id=f"pos:{trade_date.isoformat()}:{symbol}",
                    instrument_code=symbol,
                    display_name=str(row.get("display_name") or ""),
                    industry_tag_name=str(row.get("industry_tag_name") or row.get("industry") or "UNKNOWN"),
                    entry_date=trade_date,
                    quantity=quantity,
                    entry_price=price,
                    entry_notional=notional,
                    entry_reason=entry_reason,
                    confirmed_market_regime=regime,
                    route_name=str(row.get("route_name") or ""),
                    candidate_strategy_code=str(row.get("candidate_strategy_code") or "UNKNOWN"),
                    candidate_strategy_name=str(row.get("candidate_strategy_name") or ""),
                    candidate_strategy_bucket=str(row.get("candidate_strategy_bucket") or ""),
                    candidate_strategy_score=str(row.get("candidate_strategy_score") or ""),
                    last_price=price,
                    max_price=price,
                )
                open_positions[symbol] = position
                new_positions += 1
                trade_rows.append(
                    self._trade_row(
                        trade_date=trade_date,
                        sequence_no=sequence,
                        position=position,
                        side="BUY",
                        quantity=quantity,
                        price=price,
                        notional=notional,
                        transaction_cost=cost,
                        cash_after=cash,
                        entry_reason=entry_reason,
                        exit_reason="",
                        exit_type="",
                        holding_days=0,
                        confirmed_market_regime=regime,
                        status="PASS",
                        detail="buy_after_sell_entry_executed",
                    )
                )

            gross_exposure = quantize_money(sum((position.entry_notional for position in open_positions.values()), Decimal("0")))
            total_equity = quantize_money(cash + gross_exposure)
            industry_exposure = self._industry_exposure(open_positions, total_equity)
            sell_before_buy_verified = self._sell_before_buy_verified([row for row in trade_rows if row.get("trade_date") == trade_date.isoformat()])
            cash_non_negative = cash >= 0
            position_cap_ok = len(open_positions) <= max_total_positions and (total_equity <= 0 or gross_exposure / total_equity <= total_position_cap)
            industry_cap_ok = all(exposure <= max_industry_weight for exposure in industry_exposure.values())
            day_status = "PASS" if sell_before_buy_verified and cash_non_negative and position_cap_ok and industry_cap_ok else "FAIL"
            daily_rows.append(
                {
                    "trade_date": trade_date.isoformat(),
                    "confirmed_market_regime": regime,
                    "total_position_cap": total_position_cap,
                    "max_new_positions_per_day": max_new_positions_per_day,
                    "begin_cash": begin_cash,
                    "sell_notional": quantize_money(sell_notional),
                    "buy_notional": quantize_money(buy_notional),
                    "transaction_cost": quantize_money(transaction_cost),
                    "ending_cash": cash,
                    "gross_exposure": gross_exposure,
                    "total_equity": total_equity,
                    "position_count": len(open_positions),
                    "industry_exposure_json": json.dumps({k: str(v) for k, v in industry_exposure.items()}, ensure_ascii=False),
                    "sell_before_buy_verified": sell_before_buy_verified,
                    "cash_non_negative": cash_non_negative,
                    "position_cap_ok": position_cap_ok,
                    "industry_cap_ok": industry_cap_ok,
                    "status": day_status,
                    "detail": "daily lifecycle order completed" if day_status == "PASS" else "daily guardrail violation",
                }
            )

        open_lifecycles = [self._open_position_lifecycle_row(position) for position in open_positions.values()]
        lifecycle_rows = [*closed_lifecycles, *open_lifecycles]
        entry_summary = self._reason_rows(entry_reason_counter, status="PASS", detail="executed entry reason") + self._reason_rows(entry_block_counter, status="WARN", detail="blocked entry reason")
        exit_summary = self._reason_rows(exit_reason_counter, status="PASS", detail="executed exit reason")
        by_regime_rows = self._performance_rows(regime_realized, REGIME_PERFORMANCE_COLUMNS[0])
        by_industry_rows = self._performance_rows(industry_realized, INDUSTRY_PERFORMANCE_COLUMNS[0])
        by_strategy_rows = self._performance_rows(strategy_realized, STRATEGY_PERFORMANCE_COLUMNS[0])

        contract_checks.extend(
            self._execution_contract_checks(
                daily_rows=daily_rows,
                trade_rows=trade_rows,
                lifecycle_rows=lifecycle_rows,
                entry_summary=entry_summary,
                exit_summary=exit_summary,
                candidate_row_count=len(candidate_rows),
            )
        )
        all_status_rows = [*contract_checks, *daily_rows]
        status = status_from_checks(all_status_rows)
        blocker_count = sum(1 for row in all_status_rows if row.get("status") == "FAIL")
        warn_count = sum(1 for row in all_status_rows if row.get("status") == "WARN")
        no_trade_by_design = len(candidate_rows) == 0 and len(trade_rows) == 0
        metrics = {
            "candidate_row_count": len(candidate_rows),
            "candidate_date_count": len(rows_by_date),
            "no_trade_by_design": no_trade_by_design,
            "no_trade_reason": "zero_candidate_rows_after_top_down_or_window_filter" if no_trade_by_design else "",
            "trade_count": len(trade_rows),
            "buy_count": sum(1 for row in trade_rows if row.get("side") == "BUY"),
            "sell_count": sum(1 for row in trade_rows if row.get("side") == "SELL"),
            "closed_position_count": len(closed_lifecycles),
            "open_position_count": len(open_positions),
            "initial_cash": config.initial_cash,
            "ending_cash": cash,
            "blocker_count": blocker_count,
            "warn_count": warn_count,
            "entry_block_reasons": dict(entry_block_counter),
            "candidate_strategy_policy_count": len(candidate_strategy_policies),
            "market_structure_gate_policy_enabled": bool(market_structure_gate_policy.get("enabled")),
            "parameter_version_id": parameter_version_id,
            "policy_effective_hash": policy_effective_hash,
        }
        validation_decision = {
            "can_write_strategy_signal": False,
            "can_write_research_backtest_result": False,
            "can_route_to_m6": False,
            "can_claim_strategy_effective": False,
            "can_start_m9_adaptive_execution_attribution": status in {"PASS", "PASS_WITH_WARN"},
            "manual_review_required": True,
            "interpretation_scope": "v2_stage2_adaptive_execution_dry_run_artifact_only",
            "blocker_count": blocker_count,
            "warn_count": warn_count,
            "next_research_step": "Review dry-run lifecycle artifacts before any M9 attribution or DB-write design.",
        }
        progress(f"ADAPTIVE_EXECUTION_DRY_RUN_DONE status={status} trades={len(trade_rows)} blockers={blocker_count}")
        return AdaptiveExecutionDryRunResult(
            status=status,
            generated_at=utc_now_iso(),
            report_date=config.report_date,
            request_id=config.request_id,
            stage=STAGE,
            source_stage=SOURCE_STAGE,
            metrics=metrics,
            validation_decision=validation_decision,
            contract_checks=contract_checks,
            guardrails=[
                "artifact_only_adaptive_execution_dry_run",
                "does_not_read_database",
                "does_not_write_database",
                "does_not_call_backtrader",
                "does_not_write_research_backtest_result",
                "does_not_route_to_m6",
                "does_not_claim_performance",
                "missing_execution_price_blocks_entry_instead_of_guessing",
                "sell_before_buy_ordering_enforced",
                "R62P9_V2_STRUCTURAL_GATE_top_down_market_structure_gate_enforced_if_configured",
            ],
            daily_portfolio_rows=daily_rows,
            trade_log_rows=trade_rows,
            position_lifecycle_rows=lifecycle_rows,
            entry_reason_summary_rows=entry_summary,
            exit_reason_summary_rows=exit_summary,
            by_regime_performance_rows=by_regime_rows,
            by_industry_performance_rows=by_industry_rows,
            by_strategy_performance_rows=by_strategy_rows,
        )

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_policy(self, config: AdaptiveExecutionDryRunConfig) -> dict[str, Any]:
        path = Path(config.policy_artifact_dir) / "adaptive_execution_policy_v1.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {}

    def _load_candidate_rows(self, config: AdaptiveExecutionDryRunConfig) -> list[dict[str, Any]]:
        candidates: list[Path] = []
        if config.candidate_signal_csv:
            candidates.append(Path(config.candidate_signal_csv))
        candidates.extend(
            [
                Path(config.candidate_signal_artifact_dir) / f"m4_historical_signal_preview_rows_{config.report_date}.csv",
                Path(config.candidate_signal_artifact_dir) / f"m5_backtest_executor_implementation_order_plan_{config.report_date}.csv",
            ]
        )
        candidates.extend(sorted(Path(config.candidate_signal_artifact_dir).glob("*signal*preview*rows*.csv")))
        candidates.extend(sorted(Path(config.candidate_signal_artifact_dir).glob("*implementation_order_plan*.csv")))
        for path in candidates:
            if path and path.exists():
                with path.open("r", encoding="utf-8-sig", newline="") as f:
                    return [dict(row) for row in csv.DictReader(f)]
        return []

    # ------------------------------------------------------------------
    # Contract checks
    # ------------------------------------------------------------------

    def _source_contract_checks(
        self,
        *,
        config: AdaptiveExecutionDryRunConfig,
        policy: Mapping[str, Any],
        candidate_rows: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        checks = [
            self._check("policy_artifact_loaded", "PASS" if policy else "FAIL", f"policy_dir={config.policy_artifact_dir}", rows=1 if policy else 0),
            self._check("candidate_rows_loaded", "PASS" if candidate_rows else "FAIL", f"candidate_rows={len(candidate_rows)}", rows=len(candidate_rows)),
            self._check("artifact_only_boundary", "PASS", "Service is artifact-only and has no DB engine dependency.", rows=0),
            self._check("m6_boundary", "PASS", "M6 routing is forced false for adaptive execution dry-run.", rows=0),
        ]
        if policy:
            decision = policy.get("validation_decision") if isinstance(policy.get("validation_decision"), dict) else {}
            checks.append(
                self._check(
                    "stage1_policy_allows_stage2_dry_run",
                    "PASS" if decision.get("can_start_adaptive_execution_dry_run") is True else "FAIL",
                    f"can_start_adaptive_execution_dry_run={decision.get('can_start_adaptive_execution_dry_run')}",
                    rows=1,
                )
            )
        checks.extend(self._candidate_input_coverage_checks(config=config, candidate_rows=candidate_rows))
        return checks

    def _candidate_input_coverage_checks(
        self,
        *,
        config: AdaptiveExecutionDryRunConfig,
        candidate_rows: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        if not candidate_rows:
            return []
        total = len(candidate_rows)
        price_count = sum(1 for row in candidate_rows if self._extract_execution_price(row, config.execution_price_column) is not None)
        limit_count = sum(1 for row in candidate_rows if str(row.get("limit_status") or "").strip())
        tradable_flag_count = sum(1 for row in candidate_rows if row.get("feat_tradable_flag") not in (None, ""))
        parsed_tradable_count = sum(1 for row in candidate_rows if is_truthy(row.get("feat_tradable_flag")))

        def coverage_status(count: int) -> str:
            if count == total:
                return "PASS"
            if count == 0:
                return "FAIL"
            return "WARN"

        return [
            self._check(
                "candidate_execution_price_coverage",
                coverage_status(price_count),
                f"execution_price_available={price_count}/{total}; entries without execution price are blocked, never guessed.",
                rows=price_count,
            ),
            self._check(
                "candidate_limit_status_coverage",
                coverage_status(limit_count),
                f"limit_status_available={limit_count}/{total}; entries without limit_status are blocked, never treated as not_limit_up by default.",
                rows=limit_count,
            ),
            self._check(
                "candidate_tradability_flag_parse",
                "PASS" if tradable_flag_count == 0 or parsed_tradable_count > 0 else "WARN",
                f"feat_tradable_flag_present={tradable_flag_count}/{total}; parsed_truthy={parsed_tradable_count}/{total}; decimal flags such as 1.0000000000 are accepted.",
                rows=parsed_tradable_count,
            ),
        ]

    def _execution_contract_checks(
        self,
        *,
        daily_rows: Sequence[Mapping[str, Any]],
        trade_rows: Sequence[Mapping[str, Any]],
        lifecycle_rows: Sequence[Mapping[str, Any]],
        entry_summary: Sequence[Mapping[str, Any]],
        exit_summary: Sequence[Mapping[str, Any]],
        candidate_row_count: int = 0,
    ) -> list[dict[str, Any]]:
        buy_rows = [row for row in trade_rows if row.get("side") == "BUY"]
        sell_rows = [row for row in trade_rows if row.get("side") == "SELL"]
        fatal_entry_input_rows = [
            row for row in entry_summary if str(row.get("reason") or "").strip() in FATAL_ENTRY_INPUT_REASONS
        ]
        if int(candidate_row_count or 0) == 0 and not daily_rows and not trade_rows and not lifecycle_rows:
            return [
                self._check(
                    "no_trade_by_design",
                    "PASS",
                    "zero candidate rows after top-down/window filter; safe no-trade research window.",
                    rows=0,
                ),
                self._check("daily_portfolio_rows", "PASS", "no daily rows expected for zero-candidate no-trade window", rows=0),
                self._check("trade_log_empty_by_design", "PASS", "trade_count=0 expected for no-trade-by-design window", rows=0),
                self._check("position_lifecycle_empty_by_design", "PASS", "no positions expected for no-trade-by-design window", rows=0),
            ]
        return [
            self._check("daily_portfolio_rows", "PASS" if daily_rows else "FAIL", f"rows={len(daily_rows)}", rows=len(daily_rows)),
            self._check("sell_before_buy_order", "PASS" if all(is_truthy(row.get("sell_before_buy_verified")) for row in daily_rows) else "FAIL", "All daily rows must verify sell-before-buy order.", rows=len(daily_rows)),
            self._check("cash_non_negative", "PASS" if all(is_truthy(row.get("cash_non_negative")) for row in daily_rows) else "FAIL", "Cash must remain non-negative.", rows=len(daily_rows)),
            self._check("position_cap_enforced", "PASS" if all(is_truthy(row.get("position_cap_ok")) for row in daily_rows) else "FAIL", "Position count and regime exposure cap must hold.", rows=len(daily_rows)),
            self._check("industry_cap_enforced", "PASS" if all(is_truthy(row.get("industry_cap_ok")) for row in daily_rows) else "FAIL", "Industry concentration cap must hold.", rows=len(daily_rows)),
            self._check(
                "entry_input_contract",
                "FAIL" if fatal_entry_input_rows else "PASS",
                "Fatal entry input evidence blockers must be resolved before dry-run validation.",
                rows=sum(int(row.get("count") or 0) for row in fatal_entry_input_rows),
            ),
            self._check("buy_trade_entry_reason", "PASS" if all(str(row.get("entry_reason") or "").strip() for row in buy_rows) else "FAIL", f"buy_count={len(buy_rows)}", rows=len(buy_rows)),
            self._check("sell_trade_exit_reason", "PASS" if all(str(row.get("exit_reason") or "").strip() for row in sell_rows) else ("WARN" if not sell_rows else "FAIL"), f"sell_count={len(sell_rows)}", rows=len(sell_rows)),
            self._check("trade_holding_days", "PASS" if all(row.get("holding_days") not in (None, "") for row in trade_rows) else "FAIL", f"trade_count={len(trade_rows)}", rows=len(trade_rows)),
            self._check("lifecycle_float_fields", "PASS" if all(row.get("max_floating_profit") not in (None, "") and row.get("max_floating_loss") not in (None, "") for row in lifecycle_rows) else "FAIL", f"lifecycle_count={len(lifecycle_rows)}", rows=len(lifecycle_rows)),
            self._check("entry_reason_summary_rows", "PASS" if entry_summary else "WARN", f"rows={len(entry_summary)}", rows=len(entry_summary)),
            self._check("exit_reason_summary_rows", "PASS" if exit_summary else "WARN", f"rows={len(exit_summary)}", rows=len(exit_summary)),
        ]

    # ------------------------------------------------------------------
    # Entry and exit logic
    # ------------------------------------------------------------------

    def _group_candidate_rows_by_effective_date(self, rows: Sequence[Mapping[str, Any]]) -> dict[date, list[Mapping[str, Any]]]:
        grouped: dict[date, list[Mapping[str, Any]]] = defaultdict(list)
        for row in rows:
            trade_date = parse_date(pick_first(row, ["effective_date", "entry_date", "trade_date", "as_of_date"]))
            if trade_date:
                grouped[trade_date].append(row)
        return dict(sorted(grouped.items(), key=lambda item: item[0]))

    def _candidate_strategy_policies(self, policy: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
        execution_policy = policy.get("execution_policy") if isinstance(policy.get("execution_policy"), Mapping) else {}
        candidates = []
        if isinstance(execution_policy, Mapping):
            candidates.extend(
                [
                    execution_policy.get("candidate_strategy_policies"),
                    execution_policy.get("candidate_strategy_execution_policy"),
                    execution_policy.get("candidate_bucket_policy"),
                ]
            )
        candidates.extend(
            [
                policy.get("candidate_strategy_policies"),
                policy.get("candidate_strategy_execution_policy"),
                policy.get("candidate_bucket_policy"),
            ]
        )

        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                continue
            normalized: dict[str, Mapping[str, Any]] = {}
            for key, value in candidate.items():
                if isinstance(value, Mapping):
                    normalized[str(key)] = value
            if normalized:
                return normalized
        return {}


    def _resolve_candidate_strategy_policy(
        self,
        *,
        candidate_strategy_policies: Mapping[str, Mapping[str, Any]],
        candidate_strategy_code: str,
        candidate_strategy_bucket: str,
    ) -> tuple[dict[str, Any], str]:
        """Resolve allocator policy from M4 strategy code/bucket aliases.

        R62P11E fixes a runtime bug introduced during allocator hardening: the
        caller expects ``(policy, resolved_key)`` but the previous resolver
        returned only a dict.  This function intentionally keeps explicit alias
        literals for regression checks while also supporting generic ``*_strategy``
        and ``*_strategy_code`` normalization.
        """
        if not candidate_strategy_policies:
            return {}, ""

        explicit_alias_map = {
            "range_pullback_quality_strategy": "range_pullback_quality",
            "trend_growth_strategy": "trend_growth",
            "risk_off_defensive_strategy": "risk_off_defensive",
            "oversold_reversal_strategy": "oversold_reversal",
            "concept_strength_strategy": "concept_strength",
            "capital_flow_strategy": "capital_flow",
        }

        aliases: list[str] = []

        def add_alias(value: Any) -> None:
            text_value = str(value or "").strip()
            if not text_value:
                return
            candidates = [text_value, text_value.lower()]
            lower_value = text_value.lower()
            mapped = explicit_alias_map.get(lower_value)
            if mapped:
                candidates.append(mapped)
            for suffix in ("_strategy", "_strategy_code"):
                if lower_value.endswith(suffix):
                    stripped = lower_value[: -len(suffix)]
                    if stripped:
                        candidates.append(stripped)
            for candidate in candidates:
                if candidate and candidate not in aliases:
                    aliases.append(candidate)

        add_alias(candidate_strategy_code)
        add_alias(candidate_strategy_bucket)

        for alias in aliases:
            policy = candidate_strategy_policies.get(alias)
            if isinstance(policy, Mapping):
                return dict(policy), str(alias)

        lower_key_map = {
            str(key).lower(): (str(key), value)
            for key, value in candidate_strategy_policies.items()
            if isinstance(value, Mapping)
        }
        for alias in aliases:
            matched = lower_key_map.get(alias.lower())
            if matched:
                matched_key, policy = matched
                return dict(policy), matched_key
        return {}, ""

    def _strategy_position_weight_multiplier(self, strategy_policy: Mapping[str, Any]) -> Decimal:
        raw_value = (
            strategy_policy.get("position_weight_multiplier")
            if strategy_policy.get("position_weight_multiplier") is not None
            else strategy_policy.get("allocation_multiplier")
        )
        if raw_value is None:
            return Decimal("1")
        parsed = to_decimal(raw_value)
        if parsed is None:
            return Decimal("1")
        if parsed < 0:
            return Decimal("0")
        return parsed

    def _market_structure_gate_policy(self, policy: Mapping[str, Any]) -> dict[str, Any]:
        execution_policy = policy.get("execution_policy") if isinstance(policy.get("execution_policy"), Mapping) else {}
        candidates = [
            policy.get("market_structure_gate_policy"),
            policy.get("v2_market_structure_gate_policy"),
        ]
        if isinstance(execution_policy, Mapping):
            candidates.append(execution_policy.get("market_structure_gate_policy"))
        for candidate in candidates:
            if isinstance(candidate, Mapping):
                return dict(candidate)
        return {}

    def _policy_parameter_version_id(self, policy: Mapping[str, Any]) -> str:
        pvc = policy.get("parameter_version_control") if isinstance(policy.get("parameter_version_control"), Mapping) else {}
        return str(pvc.get("parameter_version_id") or policy.get("parameter_version_id") or "UNKNOWN")

    def _policy_effective_hash(self, policy: Mapping[str, Any]) -> str:
        pvc = policy.get("parameter_version_control") if isinstance(policy.get("parameter_version_control"), Mapping) else {}
        return str(pvc.get("policy_effective_hash") or policy.get("policy_effective_hash") or "")

    def _gate_policy_for_regime(self, gate_policy: Mapping[str, Any], regime: str) -> dict[str, Any]:
        by_regime = gate_policy.get("by_regime") if isinstance(gate_policy.get("by_regime"), Mapping) else {}
        for alias in self._regime_aliases(regime):
            item = by_regime.get(alias)
            if isinstance(item, Mapping):
                return dict(item)
        return {}

    def _row_decimal_from_sources(self, row: Mapping[str, Any], sources: Sequence[str]) -> Decimal | None:
        for source in sources:
            value: Any = None
            source_text = str(source or "")
            if source_text.startswith("reason_payload_json."):
                payload = self._reason_payload(row)
                value = self._nested_payload_value(payload, source_text.split(".")[1:])
            else:
                value = row.get(source_text)
            parsed = to_decimal(value)
            if parsed is not None:
                return parsed
        return None

    def _row_bool_from_sources(self, row: Mapping[str, Any], sources: Sequence[str]) -> bool | None:
        for source in sources:
            source_text = str(source or "")
            value = row.get(source_text)
            if value in (None, ""):
                continue
            return is_truthy(value)
        return None

    def _reason_payload(self, row: Mapping[str, Any]) -> dict[str, Any]:
        raw = row.get("reason_payload_json")
        if not raw:
            return {}
        try:
            payload = json.loads(str(raw))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _nested_payload_value(self, payload: Mapping[str, Any], keys: Sequence[str]) -> Any:
        current: Any = payload
        for key in keys:
            if not isinstance(current, Mapping):
                return None
            current = current.get(key)
        return current

    def _top_down_entry_gate_result(
        self,
        *,
        row: Mapping[str, Any],
        regime: str,
        strategy_policy: Mapping[str, Any],
        market_structure_gate_policy: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not market_structure_gate_policy or market_structure_gate_policy.get("enabled") is False:
            return {"status": "PASS", "reason": "top_down_gate_disabled"}
        regime_policy = self._gate_policy_for_regime(market_structure_gate_policy, regime)

        transition_sources = market_structure_gate_policy.get("transition_flag_sources") or ["transition_flag"]
        block_transition = bool(strategy_policy.get("block_transition_new_entries") or regime_policy.get("block_transition_new_entries"))
        if block_transition and self._row_bool_from_sources(row, transition_sources) is True:
            return {"status": "FAIL", "reason": "top_down_transition_block"}

        confidence_sources = market_structure_gate_policy.get("regime_confidence_sources") or ["regime_confidence", "confidence_score"]
        min_confidence = to_decimal(strategy_policy.get("min_signal_confidence") or regime_policy.get("min_signal_confidence"))
        confidence = self._row_decimal_from_sources(row, confidence_sources)
        if min_confidence is not None and confidence is not None and confidence < min_confidence:
            return {"status": "FAIL", "reason": "top_down_low_confidence"}

        breadth_sources = market_structure_gate_policy.get("market_breadth_sources") or ["market_breadth_score", "breadth_score"]
        min_breadth = to_decimal(strategy_policy.get("min_market_breadth_score") or regime_policy.get("min_market_breadth_score"))
        breadth = self._row_decimal_from_sources(row, breadth_sources)
        if min_breadth is not None and breadth is not None and breadth < min_breadth:
            return {"status": "FAIL", "reason": "top_down_market_breadth_block"}

        return {"status": "PASS", "reason": "top_down_gate_pass"}

    def _extract_execution_price(self, row: Mapping[str, Any], explicit_column: str | None = None) -> Decimal | None:
        names = [explicit_column] if explicit_column else []
        names.extend(["execution_price", "preview_entry_price", "entry_price", "close", "trade_price"])
        value = pick_first(row, [name for name in names if name])
        price = to_decimal(value)
        if price is None or price <= 0:
            return None
        return price

    def _regime_aliases(self, regime: str) -> tuple[str, ...]:
        normalized = str(regime or "").strip().upper()
        if normalized == "RANGE":
            return ("RANGE", "NEUTRAL")
        if normalized == "NEUTRAL":
            return ("NEUTRAL", "RANGE")
        return (normalized,) if normalized else tuple()

    def _strategy_policy_for_regime(
        self,
        strategy_policy: Mapping[str, Any],
        regime: str,
    ) -> dict[str, Any]:
        """Return strategy policy merged with optional regime-specific overrides.

        R62P11D fail_closed behavior:
        - Flat legacy policies continue to work.
        - If a strategy policy declares regime-specific rules, the current regime must
          resolve to one of them; otherwise new entries are blocked instead of being
          silently allowed by the base description-only policy.
        """
        regime_specific_keys = {"RISK_ON", "RANGE", "NEUTRAL", "RISK_OFF"}
        nested_policy_keys = {"policy_by_regime", "by_regime", "regime_policies"}

        merged: dict[str, Any] = {
            key: value
            for key, value in strategy_policy.items()
            if str(key).upper() not in regime_specific_keys and key not in nested_policy_keys
        }
        has_regime_specific_policy = False

        for key in nested_policy_keys:
            nested = strategy_policy.get(key)
            if not isinstance(nested, Mapping):
                continue
            has_regime_specific_policy = True
            for alias in self._regime_aliases(regime):
                alias_policy = nested.get(alias)
                if isinstance(alias_policy, Mapping):
                    merged.update(alias_policy)
                    return merged

        for alias in self._regime_aliases(regime):
            alias_policy = strategy_policy.get(alias)
            if isinstance(alias_policy, Mapping):
                has_regime_specific_policy = True
                merged.update(alias_policy)
                return merged

        if has_regime_specific_policy:
            merged.update(
                {
                    "entry_mode": "OBSERVATION_ONLY",
                    "allow_entry": False,
                    "policy_missing_regime_override_fail_closed": True,
                    "fail_closed_reason": "candidate_strategy_policy_missing_regime_override_fail_closed",
                }
            )
        return merged


    def _policy_allowed_regimes(self, strategy_policy: Mapping[str, Any]) -> set[str]:
        raw = (
            strategy_policy.get("allowed_market_regimes")
            or strategy_policy.get("allowed_regimes")
            or strategy_policy.get("allowed_confirmed_market_regimes")
        )
        if raw is None:
            return set()
        if isinstance(raw, str):
            values = [item.strip() for item in raw.split(",")]
        elif isinstance(raw, Sequence) and not isinstance(raw, (bytes, bytearray)):
            values = [str(item).strip() for item in raw]
        else:
            values = [str(raw).strip()]

        result: set[str] = set()
        for value in values:
            if not value:
                continue
            result.update(self._regime_aliases(value))
        return result

    def _entry_gate_result(
        self,
        *,
        row: Mapping[str, Any],
        regime: str,
        cash: Decimal,
        open_positions: Mapping[str, _OpenPosition],
        initial_cash: Decimal,
        total_position_cap: Decimal,
        max_total_positions: int,
        single_position_weight: Decimal,
        max_industry_weight: Decimal,
        min_cash_reserve: Decimal,
        board_lot_size: int,
        execution_price_column: str | None,
        candidate_strategy_policies: Mapping[str, Mapping[str, Any]],
        market_structure_gate_policy: Mapping[str, Any],
    ) -> dict[str, Any]:
        candidate_strategy_code = str(row.get("candidate_strategy_code") or "UNKNOWN")
        candidate_strategy_bucket = str(row.get("candidate_strategy_bucket") or "")
        raw_strategy_policy, resolved_strategy_policy_key = self._resolve_candidate_strategy_policy(
            candidate_strategy_policies=candidate_strategy_policies,
            candidate_strategy_code=candidate_strategy_code,
            candidate_strategy_bucket=candidate_strategy_bucket,
        )
        strategy_policy = self._strategy_policy_for_regime(raw_strategy_policy, regime)
        if not raw_strategy_policy:
            return {"status": "FAIL", "reason": "candidate_strategy_policy_missing_fail_closed"}
        if strategy_policy.get("policy_missing_regime_override_fail_closed"):
            return {"status": "FAIL", "reason": "candidate_strategy_policy_missing_regime_override_fail_closed"}

        top_down_gate = self._top_down_entry_gate_result(
            row=row,
            regime=regime,
            strategy_policy=strategy_policy,
            market_structure_gate_policy=market_structure_gate_policy,
        )
        if top_down_gate["status"] != "PASS":
            return top_down_gate

        allowed_regimes = self._policy_allowed_regimes(strategy_policy)
        if allowed_regimes and not (set(self._regime_aliases(regime)) & allowed_regimes):
            return {"status": "FAIL", "reason": "candidate_strategy_regime_disabled"}

        entry_mode = str(strategy_policy.get("entry_mode") or strategy_policy.get("execution_mode") or "NORMAL").strip().upper()
        if entry_mode in OBSERVATION_ONLY_ENTRY_MODES:
            return {"status": "FAIL", "reason": "candidate_strategy_observation_only"}
        if strategy_policy.get("allow_entry") is False:
            return {"status": "FAIL", "reason": "candidate_strategy_entry_disabled"}

        position_weight_multiplier = self._strategy_position_weight_multiplier(strategy_policy)
        if position_weight_multiplier <= 0:
            return {"status": "FAIL", "reason": "candidate_strategy_allocation_disabled"}

        if str(row.get("strategy_code") or STRATEGY_CODE) != STRATEGY_CODE:
            return {"status": "FAIL", "reason": "candidate_pool_mismatch"}
        if str(row.get("strategy_version_code") or DEFAULT_CANDIDATE_POOL_PROVIDER_VERSION) != DEFAULT_CANDIDATE_POOL_PROVIDER_VERSION:
            return {"status": "FAIL", "reason": "candidate_pool_version_mismatch"}
        route_name = str(row.get("route_name") or "")
        if not self._route_matches_regime(route_name, regime):
            return {"status": "FAIL", "reason": "route_mismatch"}
        tradable_flag = row.get("feat_tradable_flag")
        tradability_score = decimal_or_zero(row.get("feat_tradability_score"))
        if tradable_flag not in (None, "") and not is_truthy(tradable_flag):
            return {"status": "FAIL", "reason": "liquidity_not_tradable"}
        if tradability_score <= 0:
            return {"status": "FAIL", "reason": "liquidity_score_missing_or_zero"}
        limit_status = str(row.get("limit_status") or "").strip().upper()
        if not limit_status:
            return {"status": "FAIL", "reason": "missing_limit_status_not_guessing_not_limit_up"}
        if limit_status in REJECTED_LIMIT_UP_STATUSES:
            return {"status": "FAIL", "reason": "limit_up"}
        if limit_status not in ACCEPTED_NOT_LIMIT_UP_STATUSES:
            return {"status": "FAIL", "reason": "unknown_limit_status_not_accepted"}
        price = self._extract_execution_price(row, execution_price_column)
        if price is None:
            return {"status": "FAIL", "reason": "missing_execution_price"}
        if max_total_positions > 0 and len(open_positions) >= max_total_positions:
            return {"status": "FAIL", "reason": "max_total_positions_reached"}
        current_exposure = sum((position.entry_notional for position in open_positions.values()), Decimal("0"))
        current_equity = quantize_money(cash + current_exposure)
        if current_equity <= 0:
            return {"status": "FAIL", "reason": "risk_budget_total_cap_reached"}

        target_notional = quantize_money(initial_cash * single_position_weight * position_weight_multiplier)
        required_cash_reserve = quantize_money(initial_cash * min_cash_reserve)
        cash_available_notional = quantize_money(cash - required_cash_reserve)
        if cash_available_notional <= 0:
            return {"status": "FAIL", "reason": "cash_reserve_required"}

        risk_budget_limit = quantize_money(current_equity * total_position_cap)
        risk_budget_available = quantize_money(risk_budget_limit - current_exposure)
        if risk_budget_available <= 0:
            return {"status": "FAIL", "reason": "risk_budget_total_cap_reached"}

        industry = str(row.get("industry_tag_name") or row.get("industry") or "UNKNOWN")
        industry_exposure = sum((position.entry_notional for position in open_positions.values() if position.industry_tag_name == industry), Decimal("0"))
        industry_budget_limit = quantize_money(current_equity * max_industry_weight)
        industry_budget_available = quantize_money(industry_budget_limit - industry_exposure)
        if industry_budget_available <= 0:
            return {"status": "FAIL", "reason": "industry_weight_cap_reached"}

        allowed_notional = min(
            target_notional,
            cash_available_notional,
            risk_budget_available,
            industry_budget_available,
        )
        raw_quantity = allowed_notional / price if price > 0 else Decimal("0")
        quantity = floor_to_board_lot(raw_quantity, board_lot_size)
        if quantity <= 0:
            if risk_budget_available < price * Decimal(board_lot_size):
                return {"status": "FAIL", "reason": "risk_budget_total_cap_reached"}
            if industry_budget_available < price * Decimal(board_lot_size):
                return {"status": "FAIL", "reason": "industry_weight_cap_reached"}
            if cash_available_notional < price * Decimal(board_lot_size):
                return {"status": "FAIL", "reason": "cash_reserve_required"}
            return {"status": "FAIL", "reason": "board_lot_not_satisfied"}

        entry_reason = str(
            strategy_policy.get("entry_reason")
            or strategy_policy.get("entry_reason_override")
            or "candidate_pool_match+route_match+liquidity_ok+not_limit_up+risk_budget_available+board_lot_ok"
        )

        return {
            "status": "PASS",
            "reason": "entry_allowed",
            "entry_reason": entry_reason,
            "price": price,
            "quantity": quantity,
        }

    def _route_matches_regime(self, route_name: str, regime: str) -> bool:
        route = route_name.strip().lower()
        if not route:
            return False
        if regime == "RISK_ON":
            return any(token in route for token in ("risk_on", "trend", "growth"))
        if regime == "RANGE":
            if any(token in route for token in ("range", "pullback", "quality", "reversal", "trend")):
                return True
            # R29_HISTORICAL_FALLBACK_BALANCED_ROUTE_MATCH:
            # M4 historical UNKNOWN-regime preview intentionally emits fallback_balanced_route.
            # When R27 maps UNKNOWN to RANGE risk budget for artifact-only historical walk-forward,
            # accept that explicit balanced fallback route instead of blocking all entries as route_mismatch.
            if _r29_historical_fallback_balanced_route_match_enabled() and any(token in route for token in ("fallback_balanced", "balanced", "fallback")):
                return True
            return False
        if regime == "RISK_OFF":
            return any(token in route for token in ("risk_off", "defensive", "low_risk", "reversal"))
        return False

    def _resolve_exit_reason(
        self,
        *,
        position: _OpenPosition,
        trade_date: date,
        current_regime: str,
        current_price: Decimal,
        hard_stop_loss: Decimal,
        max_holding_days: int,
        trailing_profit_start: Decimal,
        trailing_profit_drawdown: Decimal,
    ) -> str | None:
        holding_days = max((trade_date - position.entry_date).days, 0)
        current_return = (current_price - position.entry_price) / position.entry_price if position.entry_price > 0 else Decimal("0")
        if current_return <= hard_stop_loss:
            return "hard_stop_loss"
        if holding_days >= max_holding_days:
            return "max_holding_days_exit"
        if position.max_price and position.entry_price > 0:
            peak_return = (position.max_price - position.entry_price) / position.entry_price
            drawdown_from_peak = (position.max_price - current_price) / position.max_price if position.max_price > 0 else Decimal("0")
            if peak_return >= trailing_profit_start and drawdown_from_peak >= trailing_profit_drawdown:
                return "trailing_profit_drawdown_exit"
        if current_regime == "RISK_OFF" and position.confirmed_market_regime != "RISK_OFF":
            return "market_regime_exit"
        return None

    def _update_position_float(self, position: _OpenPosition, current_price: Decimal) -> None:
        position.last_price = current_price
        if position.max_price is None or current_price > position.max_price:
            position.max_price = current_price
        floating = (current_price - position.entry_price) / position.entry_price if position.entry_price > 0 else Decimal("0")
        if floating > position.max_floating_profit:
            position.max_floating_profit = quantize_ratio(floating)
        if floating < position.max_floating_loss:
            position.max_floating_loss = quantize_ratio(floating)

    # ------------------------------------------------------------------
    # Row builders
    # ------------------------------------------------------------------

    def _trade_row(
        self,
        *,
        trade_date: date,
        sequence_no: int,
        position: _OpenPosition,
        side: str,
        quantity: int,
        price: Decimal,
        notional: Decimal,
        transaction_cost: Decimal,
        cash_after: Decimal,
        entry_reason: str,
        exit_reason: str,
        exit_type: str,
        holding_days: int,
        confirmed_market_regime: str,
        status: str,
        detail: str,
    ) -> dict[str, Any]:
        return {
            "trade_id": f"trade:{trade_date.isoformat()}:{sequence_no:04d}:{position.instrument_code}:{side}",
            "trade_date": trade_date.isoformat(),
            "sequence_no": sequence_no,
            "instrument_code": position.instrument_code,
            "display_name": position.display_name,
            "side": side,
            "quantity": quantity,
            "price": price,
            "notional": notional,
            "transaction_cost": transaction_cost,
            "cash_after": cash_after,
            "entry_reason": entry_reason,
            "exit_reason": exit_reason,
            "exit_type": exit_type,
            "holding_days": holding_days,
            "max_floating_profit": position.max_floating_profit,
            "max_floating_loss": position.max_floating_loss,
            "confirmed_market_regime": confirmed_market_regime,
            "route_name": position.route_name,
            "candidate_strategy_code": position.candidate_strategy_code,
            "candidate_strategy_name": position.candidate_strategy_name,
            "candidate_strategy_bucket": position.candidate_strategy_bucket,
            "candidate_strategy_score": position.candidate_strategy_score,
            "industry_tag_name": position.industry_tag_name,
            "status": status,
            "detail": detail,
        }

    def _position_lifecycle_row(
        self,
        *,
        position: _OpenPosition,
        exit_date: date,
        exit_price: Decimal,
        exit_notional: Decimal,
        realized_pnl: Decimal,
        realized_return: Decimal,
        holding_days: int,
        exit_reason: str,
        exit_type: str,
        status: str,
    ) -> dict[str, Any]:
        return {
            "position_id": position.position_id,
            "instrument_code": position.instrument_code,
            "display_name": position.display_name,
            "industry_tag_name": position.industry_tag_name,
            "candidate_strategy_code": position.candidate_strategy_code,
            "candidate_strategy_name": position.candidate_strategy_name,
            "candidate_strategy_bucket": position.candidate_strategy_bucket,
            "candidate_strategy_score": position.candidate_strategy_score,
            "entry_date": position.entry_date.isoformat(),
            "exit_date": exit_date.isoformat(),
            "quantity": position.quantity,
            "entry_price": position.entry_price,
            "exit_price": exit_price,
            "entry_notional": position.entry_notional,
            "exit_notional": exit_notional,
            "realized_pnl": realized_pnl,
            "realized_return": realized_return,
            "holding_days": holding_days,
            "max_floating_profit": position.max_floating_profit,
            "max_floating_loss": position.max_floating_loss,
            "entry_reason": position.entry_reason,
            "exit_reason": exit_reason,
            "exit_type": exit_type,
            "status": status,
        }

    def _open_position_lifecycle_row(self, position: _OpenPosition) -> dict[str, Any]:
        return {
            "position_id": position.position_id,
            "instrument_code": position.instrument_code,
            "display_name": position.display_name,
            "industry_tag_name": position.industry_tag_name,
            "candidate_strategy_code": position.candidate_strategy_code,
            "candidate_strategy_name": position.candidate_strategy_name,
            "candidate_strategy_bucket": position.candidate_strategy_bucket,
            "candidate_strategy_score": position.candidate_strategy_score,
            "entry_date": position.entry_date.isoformat(),
            "exit_date": "",
            "quantity": position.quantity,
            "entry_price": position.entry_price,
            "exit_price": "",
            "entry_notional": position.entry_notional,
            "exit_notional": "",
            "realized_pnl": "",
            "realized_return": "",
            "holding_days": "",
            "max_floating_profit": position.max_floating_profit,
            "max_floating_loss": position.max_floating_loss,
            "entry_reason": position.entry_reason,
            "exit_reason": "",
            "exit_type": "",
            "status": "OPEN",
        }

    def _reason_rows(self, counter: Counter[str], *, status: str, detail: str) -> list[dict[str, Any]]:
        return [{"reason": reason, "status": status, "count": count, "detail": detail} for reason, count in sorted(counter.items())]

    def _performance_rows(self, buckets: Mapping[str, Mapping[str, Any]], key_name: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for key, bucket in sorted(buckets.items()):
            trade_count = int(bucket.get("trade_count") or 0)
            pnl = quantize_money(Decimal(bucket.get("pnl") or 0))
            notional = Decimal(bucket.get("notional") or 0)
            holding_days = int(bucket.get("holding_days") or 0)
            rows.append(
                {
                    key_name: key,
                    "trade_count": trade_count,
                    "realized_pnl": pnl,
                    "realized_return": quantize_ratio(pnl / notional) if notional > 0 else Decimal("0"),
                    "avg_holding_days": quantize_ratio(Decimal(holding_days) / Decimal(trade_count)) if trade_count > 0 else Decimal("0"),
                    "status": "PASS" if trade_count > 0 else "WARN",
                    "detail": "closed trade attribution only; not a performance claim",
                }
            )
        return rows

    def _industry_exposure(self, positions: Mapping[str, _OpenPosition], total_equity: Decimal) -> dict[str, Decimal]:
        exposure: dict[str, Decimal] = defaultdict(Decimal)
        for position in positions.values():
            exposure[position.industry_tag_name or "UNKNOWN"] += position.entry_notional
        if total_equity <= 0:
            return {key: Decimal("0") for key in exposure}
        return {key: quantize_ratio(value / total_equity) for key, value in exposure.items()}

    def _sell_before_buy_verified(self, day_trade_rows: Sequence[Mapping[str, Any]]) -> bool:
        first_buy_seq = min((safe_int(row.get("sequence_no")) or 0 for row in day_trade_rows if row.get("side") == "BUY"), default=None)
        if first_buy_seq is None:
            return True
        sell_after_buy = [row for row in day_trade_rows if row.get("side") == "SELL" and (safe_int(row.get("sequence_no")) or 0) > first_buy_seq]
        return not sell_after_buy

    def _estimate_transaction_cost(self, notional: Decimal, bps: Decimal) -> Decimal:
        if notional <= 0 or bps <= 0:
            return Decimal("0")
        return quantize_money(notional * bps / Decimal("10000"))

    # ------------------------------------------------------------------
    # Artifact writing
    # ------------------------------------------------------------------

    def _write_artifacts(self, output_dir: Path, result: AdaptiveExecutionDryRunResult) -> AdaptiveExecutionDryRunResult:
        metrics_path = output_dir / "metrics.json"
        md_path = output_dir / "adaptive_execution_dry_run_report.md"
        daily_path = output_dir / "daily_portfolio.csv"
        trade_path = output_dir / "trade_log.csv"
        lifecycle_path = output_dir / "position_lifecycle.csv"
        entry_path = output_dir / "entry_reason_summary.csv"
        exit_path = output_dir / "exit_reason_summary.csv"
        regime_path = output_dir / "by_regime_performance.csv"
        industry_path = output_dir / "by_industry_performance.csv"
        strategy_path = output_dir / "by_strategy_performance.csv"
        contract_path = output_dir / "contract_checks.csv"
        result.artifacts = AdaptiveExecutionDryRunArtifacts(
            metrics_path=str(metrics_path),
            markdown_path=str(md_path),
            daily_portfolio_path=str(daily_path),
            trade_log_path=str(trade_path),
            position_lifecycle_path=str(lifecycle_path),
            entry_reason_summary_path=str(entry_path),
            exit_reason_summary_path=str(exit_path),
            by_regime_performance_path=str(regime_path),
            by_industry_performance_path=str(industry_path),
            by_strategy_performance_path=str(strategy_path),
            contract_checks_path=str(contract_path),
        )
        metrics_path.write_text(json.dumps(result.to_metrics_dict(), ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
        md_path.write_text(self._build_markdown(result), encoding="utf-8")
        self._write_csv(daily_path, DAILY_PORTFOLIO_COLUMNS, result.daily_portfolio_rows)
        self._write_csv(trade_path, TRADE_LOG_COLUMNS, result.trade_log_rows)
        self._write_csv(lifecycle_path, POSITION_LIFECYCLE_COLUMNS, result.position_lifecycle_rows)
        self._write_csv(entry_path, REASON_SUMMARY_COLUMNS, result.entry_reason_summary_rows)
        self._write_csv(exit_path, REASON_SUMMARY_COLUMNS, result.exit_reason_summary_rows)
        self._write_csv(regime_path, REGIME_PERFORMANCE_COLUMNS, result.by_regime_performance_rows)
        self._write_csv(industry_path, INDUSTRY_PERFORMANCE_COLUMNS, result.by_industry_performance_rows)
        self._write_csv(strategy_path, STRATEGY_PERFORMANCE_COLUMNS, result.by_strategy_performance_rows)
        self._write_csv(contract_path, CONTRACT_CHECK_COLUMNS, result.contract_checks)
        return result

    def _build_markdown(self, result: AdaptiveExecutionDryRunResult) -> str:
        lines = [
            f"# M5 Adaptive Execution Dry-Run - request_{result.request_id}",
            "",
            f"- status: `{result.status}`",
            f"- report_date: `{result.report_date}`",
            f"- candidate_row_count: `{result.metrics.get('candidate_row_count')}`",
            f"- candidate_date_count: `{result.metrics.get('candidate_date_count')}`",
            f"- trade_count: `{result.metrics.get('trade_count')}`",
            f"- buy_count: `{result.metrics.get('buy_count')}`",
            f"- sell_count: `{result.metrics.get('sell_count')}`",
            f"- closed_position_count: `{result.metrics.get('closed_position_count')}`",
            f"- by_strategy_rows: `{len(result.by_strategy_performance_rows)}`",
            f"- open_position_count: `{result.metrics.get('open_position_count')}`",
            f"- blocker_count: `{result.validation_decision.get('blocker_count')}`",
            f"- warn_count: `{result.validation_decision.get('warn_count')}`",
            f"- can_write_research_backtest_result: `{result.validation_decision.get('can_write_research_backtest_result')}`",
            f"- can_route_to_m6: `{result.validation_decision.get('can_route_to_m6')}`",
            "",
            "## Guardrails",
        ]
        lines.extend(f"- {item}" for item in result.guardrails)
        lines.extend(["", "## Contract Checks"])
        for row in result.contract_checks:
            lines.append(f"- **{row.get('status')}** `{row.get('check_name')}`: {row.get('detail')}")
        lines.append("")
        return "\n".join(lines)

    def _write_csv(self, path: Path, columns: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(columns), extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({key: json_default(row.get(key)) if row.get(key) is not None else "" for key in columns})

    def _empty_result(self, config: AdaptiveExecutionDryRunConfig, contract_checks: list[dict[str, Any]]) -> AdaptiveExecutionDryRunResult:
        status = status_from_checks(contract_checks)
        blocker_count = sum(1 for row in contract_checks if row.get("status") == "FAIL")
        warn_count = sum(1 for row in contract_checks if row.get("status") == "WARN")
        return AdaptiveExecutionDryRunResult(
            status=status,
            generated_at=utc_now_iso(),
            report_date=config.report_date,
            request_id=config.request_id,
            stage=STAGE,
            source_stage=SOURCE_STAGE,
            metrics={
                "candidate_row_count": 0,
                "candidate_date_count": 0,
                "trade_count": 0,
                "buy_count": 0,
                "sell_count": 0,
                "closed_position_count": 0,
                "open_position_count": 0,
                "blocker_count": blocker_count,
                "warn_count": warn_count,
            },
            validation_decision={
                "can_write_strategy_signal": False,
                "can_write_research_backtest_result": False,
                "can_route_to_m6": False,
                "can_claim_strategy_effective": False,
                "can_start_m9_adaptive_execution_attribution": False,
                "manual_review_required": True,
                "interpretation_scope": "v2_stage2_adaptive_execution_dry_run_artifact_only",
                "blocker_count": blocker_count,
                "warn_count": warn_count,
                "next_research_step": "Fix adaptive execution dry-run input blockers.",
            },
            contract_checks=contract_checks,
            guardrails=[
                "artifact_only_adaptive_execution_dry_run",
                "does_not_read_database",
                "does_not_write_database",
                "does_not_route_to_m6",
                "missing_required_inputs_block_run_instead_of_guessing",
            ],
        )

    def _check(self, name: str, status: str, detail: str, *, rows: int = 0) -> dict[str, Any]:
        return {"check_name": name, "status": status, "row_count": rows, "detail": detail}


# === STAGE6_19B_2K_ADAPTIVE_EXECUTION_DRY_RUN_GATE BEGIN ===
# This block is intentionally self-contained and research-only.  It converts the
# Stage 6.19B 2J eligible candidate rows into an artifact-only adaptive execution
# dry-run input.  It must not create research_backtest_request rows, execute a
# backtest, or route anything to paper trading / production.
from typing import Any as _Stage619B2KAny
from typing import Mapping as _Stage619B2KMapping
from typing import Sequence as _Stage619B2KSequence

STAGE6_19B_2K_SCORE_POLICY = "cleaned_v1_1_preview_score"
STAGE6_19B_2K_DRY_RUN_POLICY_VERSION = "adaptive_execution_dry_run_cleaned_v1_1_v0"
STAGE6_19B_2K_SCOPE = "RESEARCH_ARTIFACT_ONLY_ADAPTIVE_EXECUTION_DRY_RUN"


def _stage6_19b_2k_bool(value: _Stage619B2KAny) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y", "pass"}


def _stage6_19b_2k_float(value: _Stage619B2KAny) -> float | None:
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(value)
    except Exception:
        return None


def build_stage6_19b_2k_adaptive_execution_dry_run_rows(
    candidate_rows: _Stage619B2KSequence[_Stage619B2KMapping[str, _Stage619B2KAny]],
) -> dict[str, _Stage619B2KAny]:
    """Build Stage 6.19B-2K adaptive execution dry-run rows from 2J eligible inputs.

    Contract boundaries:
    - input rows must already be 2J eligible candidate-enrichment rows;
    - output is artifact-only and may feed the next review/design step only;
    - this function never creates research_backtest_request rows;
    - this function never executes a backtest;
    - this function never routes rows to paper trading or production.
    """
    input_rows = [dict(row) for row in candidate_rows]
    dry_run_rows: list[dict[str, _Stage619B2KAny]] = []
    rejected_rows: list[dict[str, _Stage619B2KAny]] = []

    for index, row in enumerate(input_rows, start=1):
        price = _stage6_19b_2k_float(row.get("execution_price"))
        score_policy = str(row.get("score_policy") or "").strip()
        eligible = (
            _stage6_19b_2k_bool(row.get("can_start_adaptive_execution_dry_run"))
            and _stage6_19b_2k_bool(row.get("eligible_for_m5_candidate_enrichment_dry_run"))
            and _stage6_19b_2k_bool(row.get("not_limit_up"))
            and str(row.get("entry_input_status") or "").upper() == "PASS"
            and str(row.get("candidate_enrichment_status") or "").upper() == "PASS"
            and score_policy == STAGE6_19B_2K_SCORE_POLICY
            and price is not None
            and price > 0
        )
        out = dict(row)
        out.update(
            {
                "adaptive_execution_dry_run_policy_version": STAGE6_19B_2K_DRY_RUN_POLICY_VERSION,
                "adaptive_execution_dry_run_scope": STAGE6_19B_2K_SCOPE,
                "adaptive_execution_dry_run_row_id": row.get("handoff_row_id") or f"M5_DRY_RUN:{row.get('source_run_id', '')}:{index:05d}",
                "adaptive_execution_dry_run_status": "PASS" if eligible else "FAIL",
                "adaptive_execution_dry_run_action": "PREPARE_ENTRY_DRY_RUN_ARTIFACT_ONLY" if eligible else "FILTER_BEFORE_ADAPTIVE_EXECUTION_DRY_RUN",
                "planned_side": row.get("planned_side") or "BUY",
                "planned_quantity": row.get("planned_quantity") or "",
                "planned_notional": "",
                "execution_price_for_dry_run": price if price is not None else "",
                "can_create_research_backtest_request_now": "false",
                "can_execute_backtest_now": "false",
                "can_route_to_paper_trading_now": "false",
                "can_route_to_m6_now": "false",
                "can_claim_strategy_effective_now": "false",
            }
        )
        if eligible:
            dry_run_rows.append(out)
        else:
            rejected_rows.append(out)

    source_run_ids = sorted({str(row.get("source_run_id") or "").strip() for row in dry_run_rows if str(row.get("source_run_id") or "").strip()})
    effective_dates = sorted({str(row.get("effective_date") or "").strip() for row in dry_run_rows if str(row.get("effective_date") or "").strip()})
    score_policies = sorted({str(row.get("score_policy") or "").strip() for row in dry_run_rows if str(row.get("score_policy") or "").strip()})
    request_true_count = sum(1 for row in dry_run_rows if _stage6_19b_2k_bool(row.get("can_create_research_backtest_request_now")))
    execute_true_count = sum(1 for row in dry_run_rows if _stage6_19b_2k_bool(row.get("can_execute_backtest_now")))
    paper_true_count = sum(1 for row in dry_run_rows if _stage6_19b_2k_bool(row.get("can_route_to_paper_trading_now")))

    return {
        "status": "PASS" if dry_run_rows and not rejected_rows and request_true_count == 0 and execute_true_count == 0 and paper_true_count == 0 else "PASS_WITH_WARN" if dry_run_rows else "FAIL",
        "input_row_count": len(input_rows),
        "dry_run_row_count": len(dry_run_rows),
        "rejected_row_count": len(rejected_rows),
        "source_run_ids": source_run_ids,
        "effective_dates": effective_dates,
        "score_policies": score_policies,
        "request_true_count": request_true_count,
        "execute_true_count": execute_true_count,
        "paper_true_count": paper_true_count,
        "dry_run_rows": dry_run_rows,
        "rejected_rows": rejected_rows,
        "decision": {
            "can_review_adaptive_execution_dry_run_artifacts": bool(dry_run_rows),
            "can_create_research_backtest_request_now": False,
            "can_execute_backtest_now": False,
            "can_route_to_paper_trading_now": False,
            "can_route_to_m6": False,
            "can_claim_strategy_effective": False,
        },
    }
# === STAGE6_19B_2K_ADAPTIVE_EXECUTION_DRY_RUN_GATE END ===
