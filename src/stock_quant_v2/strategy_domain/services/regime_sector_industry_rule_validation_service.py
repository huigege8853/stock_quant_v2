"""M4 S2 rule validation for regime / sector / industry selection.

This module is intentionally read-only. It reads DB inputs and writes only file
artifacts through the task layer. It does not create strategy_signal rows, does
not submit M5 backtests, does not touch paper trading, and does not alter risk
rules.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

STRATEGY_CODE = "regime_sector_industry_selection_v1"
STRATEGY_STAGE = "M4_S2_RULE_VALIDATION"
FEATURE_SET_CODE = "fs_daily_alpha_v1"
FEATURE_SET_VERSION = "v1"
DEFAULT_REPORT_DIR = Path("artifacts") / "m4" / "strategy_rule_validation"
DEFAULT_INDUSTRY_TAG_TYPE = "SW_INDUSTRY_L2"
DEFAULT_BENCHMARK_INDEX_CODE = "000300.SH"
DEFAULT_LOOKBACK_DAYS = 20
DEFAULT_MIN_PREVIEW_ROWS = 50
DEFAULT_TOP_N = 100

REQUIRED_FEATURE_CODES = (
    "feat_mom_20",
    "feat_trend_strength_20",
    "feat_volatility_rank_20",
    "feat_tradability_score",
    "feat_tradable_flag",
    "feat_industry_strength_20",
)
OPTIONAL_FEATURE_CODES = (
    "feat_industry_ret_20",
    "feat_industry_breadth_20",
)
ALL_VALIDATION_FEATURE_CODES = REQUIRED_FEATURE_CODES + OPTIONAL_FEATURE_CODES

REGIME_ROUTE_CONFIG: dict[str, dict[str, Any]] = {
    "RISK_ON": {
        "industry_strength_weight": Decimal("0.30"),
        "stock_alpha_weight": Decimal("0.60"),
        "risk_penalty_weight": Decimal("0.10"),
        "candidate_top_n": 80,
    },
    "NEUTRAL": {
        "industry_strength_weight": Decimal("0.35"),
        "stock_alpha_weight": Decimal("0.50"),
        "risk_penalty_weight": Decimal("0.15"),
        "candidate_top_n": 60,
    },
    "RISK_OFF": {
        "industry_strength_weight": Decimal("0.25"),
        "stock_alpha_weight": Decimal("0.35"),
        "risk_penalty_weight": Decimal("0.40"),
        "candidate_top_n": 30,
    },
}

REGIME_DISPLAY_LABELS: dict[str, str] = {
    # Keep the existing internal codes for backward compatibility, while
    # exposing the strategy language used in the PRD and M9 reports.
    "RISK_ON": "TREND_ON",
    "NEUTRAL": "RANGE",
    "RISK_OFF": "RISK_OFF",
    "UNKNOWN": "UNKNOWN",
}

REGIME_ROUTE_NAMES: dict[str, str] = {
    "RISK_ON": "trend_industry_momentum_route",
    "NEUTRAL": "range_balanced_quality_route",
    "RISK_OFF": "risk_off_defensive_route",
    "UNKNOWN": "fallback_balanced_route",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def quantize(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(Decimal("0.0000000001"), rounding=ROUND_HALF_UP)


def clamp_0_1(value: Any, *, default: Decimal | None = None) -> Decimal | None:
    decimal_value = to_decimal(value)
    if decimal_value is None:
        return default
    if decimal_value < Decimal("0"):
        return Decimal("0")
    if decimal_value > Decimal("1"):
        return Decimal("1")
    return decimal_value


def safe_ratio(numerator: Any, denominator: Any) -> Decimal | None:
    n = to_decimal(numerator)
    d = to_decimal(denominator)
    if n is None or d is None or d == 0:
        return None
    return n / d


def classify_market_regime(*, index_ret_20: Any, advancer_ratio: Any) -> str:
    """Candidate S2 market-regime rule.

    This is a validation rule, not a production trading decision. It is used to
    produce traceable preview artifacts for manual review before M4 signal code.
    """

    index_ret = to_decimal(index_ret_20)
    breadth = to_decimal(advancer_ratio)
    if index_ret is None and breadth is None:
        return "UNKNOWN"
    if (index_ret is not None and index_ret <= Decimal("-0.03")) or (
        breadth is not None and breadth <= Decimal("0.35")
    ):
        return "RISK_OFF"
    if (index_ret is not None and index_ret >= Decimal("0.02")) and (
        breadth is not None and breadth >= Decimal("0.55")
    ):
        return "RISK_ON"
    return "NEUTRAL"


def stock_alpha_score(*, mom_20: Any, trend_strength_20: Any, volatility_rank_20: Any, tradability_score: Any) -> Decimal | None:
    mom = clamp_0_1(mom_20)
    trend = clamp_0_1(trend_strength_20)
    vol = clamp_0_1(volatility_rank_20)
    tradability = clamp_0_1(tradability_score)
    if mom is None or trend is None or vol is None or tradability is None:
        return None
    low_vol = Decimal("1") - vol
    return quantize(
        Decimal("0.40") * mom
        + Decimal("0.30") * trend
        + Decimal("0.20") * tradability
        + Decimal("0.10") * low_vol
    )


def risk_penalty_score(*, volatility_rank_20: Any, tradability_score: Any) -> Decimal | None:
    vol = clamp_0_1(volatility_rank_20)
    tradability = clamp_0_1(tradability_score)
    if vol is None or tradability is None:
        return None
    illiquidity_penalty = Decimal("1") - tradability
    return quantize(Decimal("0.70") * vol + Decimal("0.30") * illiquidity_penalty)


def final_preview_score(
    *,
    market_regime: str,
    industry_strength_20: Any,
    alpha_score: Any,
    risk_penalty: Any,
) -> Decimal | None:
    route = REGIME_ROUTE_CONFIG.get(market_regime) or REGIME_ROUTE_CONFIG["NEUTRAL"]
    industry_strength = clamp_0_1(industry_strength_20)
    alpha = to_decimal(alpha_score)
    risk = to_decimal(risk_penalty)
    if industry_strength is None or alpha is None or risk is None:
        return None
    return quantize(
        route["industry_strength_weight"] * industry_strength
        + route["stock_alpha_weight"] * alpha
        - route["risk_penalty_weight"] * risk
    )


def market_regime_display_label(market_regime: str | None) -> str:
    return REGIME_DISPLAY_LABELS.get(str(market_regime or "UNKNOWN"), str(market_regime or "UNKNOWN"))


def route_name_for_regime(market_regime: str | None) -> str:
    return REGIME_ROUTE_NAMES.get(str(market_regime or "UNKNOWN"), REGIME_ROUTE_NAMES["UNKNOWN"])


def _score_text(value: Any) -> str:
    decimal_value = to_decimal(value)
    if decimal_value is None:
        return "NA"
    return str(quantize(decimal_value))


def reason_summary_for_row(row: Mapping[str, Any], *, market_regime: str) -> str:
    display_regime = market_regime_display_label(market_regime)
    route_name = route_name_for_regime(market_regime)
    reason_code = str(row.get("reason_code") or "UNKNOWN")
    if reason_code == "FILTER_NOT_TRADABLE":
        return f"市场状态={display_regime}，但个股未通过可交易性过滤，未进入候选。"
    if reason_code == "FILTER_MISSING_SCORE_INPUT":
        return f"市场状态={display_regime}，但个股缺少必要评分输入，未进入候选。"

    industry = row.get("industry_tag_name") or row.get("industry_tag_code") or "UNKNOWN"
    concept_note = "概念域暂未启用，concept_strength_enabled=false。"
    return (
        f"市场状态={display_regime}（内部码={market_regime}），采用{route_name}；"
        f"行业={industry}，行业强度20日={_score_text(row.get('feat_industry_strength_20'))}，"
        f"行业20日收益={_score_text(row.get('feat_industry_ret_20'))}，"
        f"行业20日宽度={_score_text(row.get('feat_industry_breadth_20'))}；"
        f"个股动量={_score_text(row.get('feat_mom_20'))}，"
        f"趋势={_score_text(row.get('feat_trend_strength_20'))}，"
        f"波动排名={_score_text(row.get('feat_volatility_rank_20'))}，"
        f"流动性={_score_text(row.get('feat_tradability_score'))}，"
        f"最终评分={_score_text(row.get('final_preview_score'))}。{concept_note}"
    )


def feature_quality_status(
    *,
    feature_code: str,
    required: bool,
    ready_rows: int,
    min_value: Any,
    max_value: Any,
) -> tuple[str, str | None]:
    """Return S2 feature quality status beyond mere row presence.

    Row coverage alone is insufficient for boolean / score-like features. The
    tradability features are gating inputs, so an all-zero distribution must not
    be treated as valid coverage.
    """

    if ready_rows <= 0:
        return ("FAIL" if required else "WARN", "no_ready_rows")

    min_decimal = to_decimal(min_value)
    max_decimal = to_decimal(max_value)

    if feature_code == "feat_tradable_flag":
        if max_decimal is None:
            return "FAIL", "tradable_flag_missing_numeric_values"
        if max_decimal < Decimal("1"):
            return "FAIL", "tradable_flag_has_no_tradable_samples"
        if min_decimal is not None and min_decimal < Decimal("0"):
            return "FAIL", "tradable_flag_below_zero"
        if max_decimal > Decimal("1"):
            return "FAIL", "tradable_flag_above_one"

    if feature_code == "feat_tradability_score":
        if max_decimal is None:
            return "FAIL", "tradability_score_missing_numeric_values"
        if max_decimal <= Decimal("0"):
            return "FAIL", "tradability_score_all_zero_or_negative"
        if min_decimal is not None and min_decimal < Decimal("0"):
            return "FAIL", "tradability_score_below_zero"
        if max_decimal > Decimal("1"):
            return "FAIL", "tradability_score_above_one"
        if min_decimal is not None and min_decimal == max_decimal:
            return "WARN", "tradability_score_has_no_cross_sectional_spread"

    return "PASS", None


def reason_code_for_row(row: Mapping[str, Any], *, market_regime: str) -> str:
    if clamp_0_1(row.get("feat_tradable_flag"), default=Decimal("0")) != Decimal("1"):
        return "FILTER_NOT_TRADABLE"
    if to_decimal(row.get("final_preview_score")) is None:
        return "FILTER_MISSING_SCORE_INPUT"
    industry_strength = clamp_0_1(row.get("feat_industry_strength_20"))
    risk_penalty = to_decimal(row.get("risk_penalty_score"))
    if market_regime == "RISK_OFF":
        return "RISK_OFF_LOW_RISK_ROUTE"
    if industry_strength is not None and industry_strength >= Decimal("0.80"):
        return "HIGH_INDUSTRY_STRENGTH"
    if risk_penalty is not None and risk_penalty >= Decimal("0.80"):
        return "HIGH_RISK_PENALTY_REVIEW"
    return "BALANCED_ALPHA_ROUTE"


@dataclass(slots=True)
class RuleValidationConfig:
    report_date: str
    trade_date: date
    output_dir: Path
    feature_set_code: str = FEATURE_SET_CODE
    feature_set_version: str = FEATURE_SET_VERSION
    industry_tag_type: str = DEFAULT_INDUSTRY_TAG_TYPE
    benchmark_index_code: str = DEFAULT_BENCHMARK_INDEX_CODE
    lookback_days: int = DEFAULT_LOOKBACK_DAYS
    min_preview_rows: int = DEFAULT_MIN_PREVIEW_ROWS
    top_n: int = DEFAULT_TOP_N


@dataclass(slots=True)
class RuleValidationArtifacts:
    json_path: str
    markdown_path: str
    factor_coverage_path: str
    score_preview_path: str
    rule_decision_trace_path: str
    validation_action_items_path: str


@dataclass(slots=True)
class RuleValidationResult:
    status: str
    generated_at: str
    report_date: str
    requested_trade_date: date
    actual_trade_date: date | None
    strategy_code: str
    stage: str
    market_regime: str
    route_config: dict[str, Any]
    market_inputs: dict[str, Any]
    factor_coverage: list[dict[str, Any]]
    preview_summary: dict[str, Any]
    validation_decision: dict[str, Any]
    action_items: list[dict[str, Any]]
    guardrails: list[str]
    artifacts: RuleValidationArtifacts | None = None
    score_preview_rows: list[dict[str, Any]] = field(default_factory=list)
    rule_decision_trace_rows: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self, *, include_rows: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "generated_at": self.generated_at,
            "report_date": self.report_date,
            "requested_trade_date": self.requested_trade_date,
            "actual_trade_date": self.actual_trade_date,
            "strategy_code": self.strategy_code,
            "stage": self.stage,
            "market_regime": self.market_regime,
            "route_config": self.route_config,
            "market_inputs": self.market_inputs,
            "factor_coverage": self.factor_coverage,
            "preview_summary": self.preview_summary,
            "validation_decision": self.validation_decision,
            "action_items": self.action_items,
            "guardrails": self.guardrails,
            "artifacts": asdict(self.artifacts) if self.artifacts else None,
        }
        if include_rows:
            payload["score_preview_rows"] = self.score_preview_rows
            payload["rule_decision_trace_rows"] = self.rule_decision_trace_rows
        return payload


class RegimeSectorIndustryRuleValidationService:
    def __init__(self, session: Session):
        self.session = session

    def validate(self, config: RuleValidationConfig, *, progress_callback: Callable[[str], None] | None = None) -> RuleValidationResult:
        actual_trade_date = self._resolve_actual_trade_date(
            requested_trade_date=config.trade_date,
            feature_set_code=config.feature_set_code,
            feature_set_version=config.feature_set_version,
        )
        if progress_callback:
            progress_callback(f"TRADE_DATE_RESOLVED requested={config.trade_date} actual={actual_trade_date}")

        action_items: list[dict[str, Any]] = []
        if actual_trade_date is None:
            action_items.append(
                {
                    "severity": "BLOCKER",
                    "item": "actual_trade_date",
                    "reason": "No analytics_feature_snapshot trade_date found on or before requested date.",
                    "next_step": "Run S1.2 industry strength and M3 feature builds, then rerun S2 validation.",
                }
            )
            result = RuleValidationResult(
                status="FAIL",
                generated_at=utc_now_iso(),
                report_date=config.report_date,
                requested_trade_date=config.trade_date,
                actual_trade_date=None,
                strategy_code=STRATEGY_CODE,
                stage=STRATEGY_STAGE,
                market_regime="UNKNOWN",
                route_config={},
                market_inputs={},
                factor_coverage=[],
                preview_summary={"preview_row_count": 0},
                validation_decision={
                    "can_start_s3_signal_preview_design": False,
                    "can_generate_strategy_signal_now": False,
                    "reason": "No actual feature date resolved.",
                },
                action_items=action_items,
                guardrails=self._guardrails(),
            )
            return self._write_artifacts(config=config, result=result)

        market_inputs = self._load_market_inputs(
            trade_date=actual_trade_date,
            benchmark_index_code=config.benchmark_index_code,
            lookback_days=config.lookback_days,
        )
        market_regime = classify_market_regime(
            index_ret_20=market_inputs.get("benchmark_ret_20"),
            advancer_ratio=market_inputs.get("advancer_ratio"),
        )
        route_config = self._route_config_for_json(market_regime)
        if progress_callback:
            progress_callback(f"MARKET_REGIME market_regime={market_regime} inputs={market_inputs}")

        factor_coverage = self._load_factor_coverage(
            trade_date=actual_trade_date,
            feature_set_code=config.feature_set_code,
            feature_set_version=config.feature_set_version,
            industry_tag_type=config.industry_tag_type,
        )
        coverage_by_code = {row["feature_code"]: row for row in factor_coverage}
        invalid_required = [
            f"{code}:{coverage_by_code.get(code, {}).get('quality_issue') or coverage_by_code.get(code, {}).get('status')}"
            for code in REQUIRED_FEATURE_CODES
            if coverage_by_code.get(code, {}).get("status") != "PASS"
        ]
        if invalid_required:
            action_items.append(
                {
                    "severity": "BLOCKER",
                    "item": "required_feature_quality",
                    "reason": f"Required feature coverage or quality failed: {','.join(invalid_required)}",
                    "next_step": "Rerun or repair M3/S1.2 feature builds before S3 preview. Pay special attention to all-zero tradability features.",
                }
            )

        score_rows = self._load_score_input_rows(
            trade_date=actual_trade_date,
            feature_set_code=config.feature_set_code,
            feature_set_version=config.feature_set_version,
            industry_tag_type=config.industry_tag_type,
        )
        if progress_callback:
            progress_callback(f"SCORE_INPUT_ROWS loaded={len(score_rows)}")

        scored_rows = self._score_rows(score_rows, market_regime=market_regime)
        eligible_rows = [row for row in scored_rows if row.get("is_candidate")]
        eligible_rows.sort(key=lambda row: (to_decimal(row.get("final_preview_score")) or Decimal("-999"), str(row.get("instrument_code") or "")), reverse=True)
        for rank, row in enumerate(eligible_rows, start=1):
            row["preview_rank"] = rank

        score_preview_rows = eligible_rows[: config.top_n]
        trace_rows = scored_rows[:]
        trace_rows.sort(key=lambda row: (0 if row.get("is_candidate") else 1, -(int(row.get("preview_rank") or 0)), str(row.get("instrument_code") or "")))

        if len(eligible_rows) < config.min_preview_rows:
            action_items.append(
                {
                    "severity": "BLOCKER",
                    "item": "candidate_preview_rows",
                    "reason": f"Eligible preview rows {len(eligible_rows)} below min_preview_rows {config.min_preview_rows}.",
                    "next_step": "Review feature coverage, tradable flags, and taxonomy mapping before S3 preview.",
                }
            )

        if market_regime == "UNKNOWN":
            action_items.append(
                {
                    "severity": "WARN",
                    "item": "market_regime",
                    "reason": "Market regime could not be classified from benchmark return and market breadth.",
                    "next_step": "Review market_index_bar and core_market_breadth coverage.",
                }
            )

        action_items.extend(self._manual_review_action_items())
        blocker_count = sum(1 for item in action_items if item.get("severity") == "BLOCKER")
        warn_count = sum(1 for item in action_items if item.get("severity") == "WARN")
        status = "PASS_WITH_WARN" if blocker_count == 0 else "FAIL"
        validation_decision = {
            "can_start_s3_signal_preview_design": blocker_count == 0,
            "can_generate_strategy_signal_now": False,
            "can_submit_m5_backtest_now": False,
            "manual_review_required": True,
            "blocker_count": blocker_count,
            "warn_count": warn_count,
            "reason": (
                "S2 validation artifacts are ready for manual review; formal strategy_signal generation remains blocked by stage boundary."
                if blocker_count == 0
                else "S2 validation blockers remain. Do not proceed to S3 preview design."
            ),
        }
        preview_summary = self._build_preview_summary(
            scored_rows=scored_rows,
            eligible_rows=eligible_rows,
            score_preview_rows=score_preview_rows,
            market_regime=market_regime,
            config=config,
        )

        result = RuleValidationResult(
            status=status,
            generated_at=utc_now_iso(),
            report_date=config.report_date,
            requested_trade_date=config.trade_date,
            actual_trade_date=actual_trade_date,
            strategy_code=STRATEGY_CODE,
            stage=STRATEGY_STAGE,
            market_regime=market_regime,
            route_config=route_config,
            market_inputs=market_inputs,
            factor_coverage=factor_coverage,
            preview_summary=preview_summary,
            validation_decision=validation_decision,
            action_items=action_items,
            guardrails=self._guardrails(),
            score_preview_rows=score_preview_rows,
            rule_decision_trace_rows=trace_rows,
        )
        return self._write_artifacts(config=config, result=result)

    def _resolve_actual_trade_date(self, *, requested_trade_date: date, feature_set_code: str, feature_set_version: str) -> date | None:
        row = self.session.execute(
            text(
                """
                select max(trade_date) as trade_date
                from analytics_feature_snapshot
                where trade_date <= :requested_trade_date
                  and feature_set_code = :feature_set_code
                  and feature_set_version = :feature_set_version
                  and sample_status = 'ready'
                """
            ),
            {
                "requested_trade_date": requested_trade_date,
                "feature_set_code": feature_set_code,
                "feature_set_version": feature_set_version,
            },
        ).mappings().first()
        return row["trade_date"] if row and row.get("trade_date") else None

    def _load_market_inputs(self, *, trade_date: date, benchmark_index_code: str, lookback_days: int) -> dict[str, Any]:
        breadth = self.session.execute(
            text(
                """
                select trade_date, market_scope, universe_count, bar_count, advancers, decliners, unchanged,
                       suspended_count, total_turnover_amount_cny, mean_return, median_return
                from core_market_breadth
                where trade_date <= :trade_date
                order by trade_date desc
                limit 1
                """
            ),
            {"trade_date": trade_date},
        ).mappings().first()

        index_rows = self.session.execute(
            text(
                """
                select mib.trade_date, mib.close
                from market_index_bar mib
                join market_index mi on mi.id = mib.market_index_id
                where mi.index_code = :index_code
                  and mib.trade_date <= :trade_date
                order by mib.trade_date desc
                limit :limit_rows
                """
            ),
            {"index_code": benchmark_index_code, "trade_date": trade_date, "limit_rows": max(2, lookback_days + 1)},
        ).mappings().all()

        benchmark_latest_close: Decimal | None = None
        benchmark_start_close: Decimal | None = None
        benchmark_ret_20: Decimal | None = None
        if index_rows:
            latest = index_rows[0]
            oldest = index_rows[-1]
            benchmark_latest_close = to_decimal(latest.get("close"))
            benchmark_start_close = to_decimal(oldest.get("close"))
            if benchmark_latest_close is not None and benchmark_start_close not in (None, Decimal("0")):
                benchmark_ret_20 = quantize(benchmark_latest_close / benchmark_start_close - Decimal("1"))

        advancer_ratio = None
        breadth_payload: dict[str, Any] = {}
        if breadth:
            breadth_payload = dict(breadth)
            advancer_ratio = safe_ratio(breadth.get("advancers"), breadth.get("universe_count"))

        return {
            "benchmark_index_code": benchmark_index_code,
            "benchmark_observation_count": len(index_rows),
            "benchmark_latest_close": benchmark_latest_close,
            "benchmark_start_close": benchmark_start_close,
            "benchmark_ret_20": benchmark_ret_20,
            "breadth_trade_date": breadth_payload.get("trade_date"),
            "market_scope": breadth_payload.get("market_scope"),
            "universe_count": breadth_payload.get("universe_count"),
            "advancers": breadth_payload.get("advancers"),
            "decliners": breadth_payload.get("decliners"),
            "advancer_ratio": quantize(advancer_ratio),
            "mean_return": breadth_payload.get("mean_return"),
            "median_return": breadth_payload.get("median_return"),
        }

    def _load_factor_coverage(self, *, trade_date: date, feature_set_code: str, feature_set_version: str, industry_tag_type: str) -> list[dict[str, Any]]:
        feature_rows = self.session.execute(
            text(
                """
                select feature_code,
                       count(*) as row_count,
                       count(*) filter (where sample_status = 'ready') as ready_rows,
                       count(distinct instrument_id) filter (where sample_status = 'ready') as ready_instrument_count,
                       min(feature_value_numeric) filter (where sample_status = 'ready') as min_value,
                       max(feature_value_numeric) filter (where sample_status = 'ready') as max_value,
                       avg(feature_value_numeric) filter (where sample_status = 'ready') as avg_value
                from analytics_feature_snapshot
                where trade_date = :trade_date
                  and feature_set_code = :feature_set_code
                  and feature_set_version = :feature_set_version
                  and feature_code = any(:feature_codes)
                group by feature_code
                """
            ),
            {
                "trade_date": trade_date,
                "feature_set_code": feature_set_code,
                "feature_set_version": feature_set_version,
                "feature_codes": list(ALL_VALIDATION_FEATURE_CODES),
            },
        ).mappings().all()
        rows_by_code = {row["feature_code"]: dict(row) for row in feature_rows}

        industry_row = self.session.execute(
            text(
                """
                select count(distinct t.id) as industry_count,
                       count(distinct it.instrument_id) as instrument_count
                from instrument_tag it
                join tag t on t.id = it.tag_id
                where t.tag_type = :industry_tag_type
                  and it.effective_from <= :trade_date
                  and (it.effective_to is null or it.effective_to >= :trade_date)
                """
            ),
            {"industry_tag_type": industry_tag_type, "trade_date": trade_date},
        ).mappings().first()
        industry_count = int(industry_row.get("industry_count") or 0) if industry_row else 0

        coverage: list[dict[str, Any]] = []
        for code in ALL_VALIDATION_FEATURE_CODES:
            row = rows_by_code.get(code, {})
            ready_rows = int(row.get("ready_rows") or 0)
            required = code in REQUIRED_FEATURE_CODES
            status, quality_issue = feature_quality_status(
                feature_code=code,
                required=required,
                ready_rows=ready_rows,
                min_value=row.get("min_value"),
                max_value=row.get("max_value"),
            )
            coverage.append(
                {
                    "feature_code": code,
                    "required": required,
                    "status": status,
                    "quality_issue": quality_issue,
                    "row_count": int(row.get("row_count") or 0),
                    "ready_rows": ready_rows,
                    "ready_instrument_count": int(row.get("ready_instrument_count") or 0),
                    "min_value": row.get("min_value"),
                    "max_value": row.get("max_value"),
                    "avg_value": row.get("avg_value"),
                }
            )
        coverage.append(
            {
                "feature_code": f"industry_mapping:{industry_tag_type}",
                "required": True,
                "status": "PASS" if industry_count >= 5 else "FAIL",
                "row_count": int(industry_row.get("instrument_count") or 0) if industry_row else 0,
                "ready_rows": int(industry_row.get("instrument_count") or 0) if industry_row else 0,
                "ready_instrument_count": int(industry_row.get("instrument_count") or 0) if industry_row else 0,
                "industry_count": industry_count,
                "min_value": None,
                "max_value": None,
                "avg_value": None,
            }
        )
        return coverage

    def _load_score_input_rows(self, *, trade_date: date, feature_set_code: str, feature_set_version: str, industry_tag_type: str) -> list[dict[str, Any]]:
        rows = self.session.execute(
            text(
                """
                with pivot as (
                    select
                        instrument_id,
                        max(case when feature_code = 'feat_mom_20' then feature_value_numeric end) as feat_mom_20,
                        max(case when feature_code = 'feat_trend_strength_20' then feature_value_numeric end) as feat_trend_strength_20,
                        max(case when feature_code = 'feat_volatility_rank_20' then feature_value_numeric end) as feat_volatility_rank_20,
                        max(case when feature_code = 'feat_tradability_score' then feature_value_numeric end) as feat_tradability_score,
                        max(case when feature_code = 'feat_tradable_flag' then feature_value_numeric end) as feat_tradable_flag,
                        max(case when feature_code = 'feat_industry_strength_20' then feature_value_numeric end) as feat_industry_strength_20,
                        max(case when feature_code = 'feat_industry_ret_20' then feature_value_numeric end) as feat_industry_ret_20,
                        max(case when feature_code = 'feat_industry_breadth_20' then feature_value_numeric end) as feat_industry_breadth_20
                    from analytics_feature_snapshot
                    where trade_date = :trade_date
                      and feature_set_code = :feature_set_code
                      and feature_set_version = :feature_set_version
                      and sample_status = 'ready'
                      and feature_code = any(:feature_codes)
                    group by instrument_id
                )
                select
                    p.*,
                    mi.instrument_code,
                    mi.symbol,
                    mi.display_name,
                    ind.industry_tag_code,
                    ind.industry_tag_name
                from pivot p
                join meta_instrument mi on mi.id = p.instrument_id
                left join lateral (
                    select t.tag_code as industry_tag_code, t.tag_name as industry_tag_name
                    from instrument_tag it
                    join tag t on t.id = it.tag_id
                    where it.instrument_id = p.instrument_id
                      and t.tag_type = :industry_tag_type
                      and it.effective_from <= :trade_date
                      and (it.effective_to is null or it.effective_to >= :trade_date)
                    order by it.effective_from desc, t.tag_code asc
                    limit 1
                ) ind on true
                """
            ),
            {
                "trade_date": trade_date,
                "feature_set_code": feature_set_code,
                "feature_set_version": feature_set_version,
                "feature_codes": list(ALL_VALIDATION_FEATURE_CODES),
                "industry_tag_type": industry_tag_type,
            },
        ).mappings().all()
        return [dict(row) for row in rows]

    def _score_rows(self, rows: Sequence[Mapping[str, Any]], *, market_regime: str) -> list[dict[str, Any]]:
        scored: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            alpha = stock_alpha_score(
                mom_20=row.get("feat_mom_20"),
                trend_strength_20=row.get("feat_trend_strength_20"),
                volatility_rank_20=row.get("feat_volatility_rank_20"),
                tradability_score=row.get("feat_tradability_score"),
            )
            risk = risk_penalty_score(
                volatility_rank_20=row.get("feat_volatility_rank_20"),
                tradability_score=row.get("feat_tradability_score"),
            )
            final_score = final_preview_score(
                market_regime=market_regime,
                industry_strength_20=row.get("feat_industry_strength_20"),
                alpha_score=alpha,
                risk_penalty=risk,
            )
            payload["stock_alpha_score"] = alpha
            payload["risk_penalty_score"] = risk
            payload["final_preview_score"] = final_score
            payload["market_regime"] = market_regime
            payload["market_regime_display"] = market_regime_display_label(market_regime)
            payload["route_name"] = route_name_for_regime(market_regime)
            payload["reason_code"] = reason_code_for_row(payload, market_regime=market_regime)
            payload["reason_summary"] = reason_summary_for_row(payload, market_regime=market_regime)
            payload["is_candidate"] = payload["reason_code"] not in {"FILTER_NOT_TRADABLE", "FILTER_MISSING_SCORE_INPUT"}
            payload["preview_rank"] = None
            scored.append(payload)
        return scored

    def _build_preview_summary(
        self,
        *,
        scored_rows: Sequence[Mapping[str, Any]],
        eligible_rows: Sequence[Mapping[str, Any]],
        score_preview_rows: Sequence[Mapping[str, Any]],
        market_regime: str,
        config: RuleValidationConfig,
    ) -> dict[str, Any]:
        reason_counts: dict[str, int] = {}
        industry_counts: dict[str, int] = {}
        for row in scored_rows:
            reason = str(row.get("reason_code") or "UNKNOWN")
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        for row in eligible_rows:
            industry = str(row.get("industry_tag_name") or row.get("industry_tag_code") or "UNKNOWN")
            industry_counts[industry] = industry_counts.get(industry, 0) + 1
        top_industries = [
            {"industry": industry, "candidate_count": count}
            for industry, count in sorted(industry_counts.items(), key=lambda item: (-item[1], item[0]))[:20]
        ]
        scores = [to_decimal(row.get("final_preview_score")) for row in eligible_rows]
        numeric_scores = [score for score in scores if score is not None]
        return {
            "market_regime": market_regime,
            "market_regime_display": market_regime_display_label(market_regime),
            "route_name": route_name_for_regime(market_regime),
            "score_input_row_count": len(scored_rows),
            "eligible_candidate_count": len(eligible_rows),
            "preview_row_count": len(score_preview_rows),
            "top_n_requested": config.top_n,
            "min_preview_rows": config.min_preview_rows,
            "max_final_preview_score": max(numeric_scores) if numeric_scores else None,
            "min_final_preview_score": min(numeric_scores) if numeric_scores else None,
            "reason_code_counts": reason_counts,
            "top_candidate_industries": top_industries,
        }

    def _manual_review_action_items(self) -> list[dict[str, Any]]:
        return [
            {
                "severity": "WARN",
                "item": "risk_penalty_formula",
                "reason": "S2 uses candidate formula 0.70*volatility_rank_20 + 0.30*(1-tradability_score).",
                "next_step": "Manual review before freezing the parameter schema for S3 preview.",
            },
            {
                "severity": "WARN",
                "item": "concept_strength_feature",
                "reason": "CONCEPT_EM mapping is available, but concept_strength_enabled remains false for the first strategy version.",
                "next_step": "Keep concept signals out of score formula until the separate v1.1/P2 concept strength validation.",
            },
            {
                "severity": "WARN",
                "item": "stage_boundary",
                "reason": "This task only validates formula coverage and score traces. It intentionally does not write strategy_signal.",
                "next_step": "After review, implement S3 signal preview as a separate patch with explicit approval.",
            },
        ]

    def _route_config_for_json(self, market_regime: str) -> dict[str, Any]:
        route = REGIME_ROUTE_CONFIG.get(market_regime) or REGIME_ROUTE_CONFIG["NEUTRAL"]
        return {key: value for key, value in route.items()}

    def _guardrails(self) -> list[str]:
        return [
            "read_only_database_queries",
            "no_strategy_signal_write",
            "no_m5_backtest_submit",
            "no_paper_trading",
            "no_risk_rule_change",
            "concept_strength_enabled_false",
        ]

    def _write_artifacts(self, *, config: RuleValidationConfig, result: RuleValidationResult) -> RuleValidationResult:
        output_dir = Path(config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        suffix = config.report_date
        json_path = output_dir / f"regime_sector_industry_rule_validation_{suffix}.json"
        md_path = output_dir / f"regime_sector_industry_rule_validation_{suffix}.md"
        factor_path = output_dir / f"factor_coverage_{suffix}.csv"
        preview_path = output_dir / f"score_preview_{suffix}.csv"
        trace_path = output_dir / f"rule_decision_trace_{suffix}.csv"
        action_path = output_dir / f"validation_action_items_{suffix}.csv"

        result.artifacts = RuleValidationArtifacts(
            json_path=str(json_path),
            markdown_path=str(md_path),
            factor_coverage_path=str(factor_path),
            score_preview_path=str(preview_path),
            rule_decision_trace_path=str(trace_path),
            validation_action_items_path=str(action_path),
        )

        json_path.write_text(json.dumps(result.to_dict(include_rows=False), ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
        md_path.write_text(self._render_markdown(result), encoding="utf-8")
        self._write_csv(factor_path, result.factor_coverage)
        self._write_csv(preview_path, result.score_preview_rows, fieldnames=self._score_preview_fieldnames())
        self._write_csv(trace_path, result.rule_decision_trace_rows, fieldnames=self._score_preview_fieldnames(include_trace=True))
        self._write_csv(action_path, result.action_items)
        return result

    def _render_markdown(self, result: RuleValidationResult) -> str:
        decision = result.validation_decision
        summary = result.preview_summary
        market = result.market_inputs
        lines = [
            f"# M4 S2 Rule Validation - {result.strategy_code}",
            "",
            f"- status: `{result.status}`",
            f"- report_date: `{result.report_date}`",
            f"- requested_trade_date: `{result.requested_trade_date}`",
            f"- actual_trade_date: `{result.actual_trade_date}`",
            f"- market_regime: `{result.market_regime}`",
            f"- market_regime_display: `{market_regime_display_label(result.market_regime)}`",
            f"- route_name: `{route_name_for_regime(result.market_regime)}`",
            f"- can_start_s3_signal_preview_design: `{decision.get('can_start_s3_signal_preview_design')}`",
            f"- can_generate_strategy_signal_now: `{decision.get('can_generate_strategy_signal_now')}`",
            f"- can_submit_m5_backtest_now: `{decision.get('can_submit_m5_backtest_now')}`",
            "",
            "## Market inputs",
            "",
            f"- benchmark_index_code: `{market.get('benchmark_index_code')}`",
            f"- benchmark_ret_20: `{market.get('benchmark_ret_20')}`",
            f"- advancer_ratio: `{market.get('advancer_ratio')}`",
            f"- breadth_trade_date: `{market.get('breadth_trade_date')}`",
            "",
            "## Preview summary",
            "",
            f"- score_input_row_count: `{summary.get('score_input_row_count')}`",
            f"- eligible_candidate_count: `{summary.get('eligible_candidate_count')}`",
            f"- preview_row_count: `{summary.get('preview_row_count')}`",
            f"- max_final_preview_score: `{summary.get('max_final_preview_score')}`",
            f"- min_final_preview_score: `{summary.get('min_final_preview_score')}`",
            "",
            "## Guardrails",
            "",
        ]
        for guardrail in result.guardrails:
            lines.append(f"- {guardrail}")
        lines.extend(["", "## Action items", ""])
        for item in result.action_items:
            lines.append(f"- `{item.get('severity')}` **{item.get('item')}**: {item.get('reason')} Next: {item.get('next_step')}")
        lines.extend(["", "## Formula candidates", ""])
        lines.extend(
            [
                "- stock_alpha_score = 0.40*feat_mom_20 + 0.30*feat_trend_strength_20 + 0.20*feat_tradability_score + 0.10*(1-feat_volatility_rank_20)",
                "- risk_penalty_score = 0.70*feat_volatility_rank_20 + 0.30*(1-feat_tradability_score)",
                "- final_preview_score = route.industry_strength_weight*feat_industry_strength_20 + route.stock_alpha_weight*stock_alpha_score - route.risk_penalty_weight*risk_penalty_score",
                "",
                "This is a validation artifact only. It does not write M4 strategy_signal.",
            ]
        )
        return "\n".join(lines) + "\n"

    def _score_preview_fieldnames(self, *, include_trace: bool = False) -> list[str]:
        base = [
            "preview_rank",
            "instrument_id",
            "instrument_code",
            "symbol",
            "display_name",
            "industry_tag_code",
            "industry_tag_name",
            "market_regime",
            "market_regime_display",
            "route_name",
            "feat_industry_strength_20",
            "feat_industry_ret_20",
            "feat_industry_breadth_20",
            "feat_mom_20",
            "feat_trend_strength_20",
            "feat_volatility_rank_20",
            "feat_tradability_score",
            "feat_tradable_flag",
            "stock_alpha_score",
            "risk_penalty_score",
            "final_preview_score",
            "reason_code",
            "reason_summary",
        ]
        if include_trace:
            base.append("is_candidate")
        return base

    def _write_csv(self, path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str] | None = None) -> None:
        if fieldnames is None:
            inferred: list[str] = []
            for row in rows:
                for key in row.keys():
                    if key not in inferred:
                        inferred.append(str(key))
            fieldnames = inferred
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({key: json_default(row.get(key)) if key in row else "" for key in fieldnames})
