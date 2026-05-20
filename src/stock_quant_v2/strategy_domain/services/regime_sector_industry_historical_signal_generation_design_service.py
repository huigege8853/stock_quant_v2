"""M4 historical signal generation design dry-run.

This service consumes the M5 historical backtest request/span design artifact and
turns the planned signal/effective-date pairs into an M4 historical signal
generation design. It is intentionally read-only:
- it does not generate historical strategy_signal rows;
- it does not write strategy_signal;
- it does not write M5 backtest requests/results;
- it does not execute a backtest;
- it does not route anything to M6 paper trading.
"""

from __future__ import annotations

import csv
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Engine

STRATEGY_CODE = "regime_sector_industry_selection_v1"
DEFAULT_STRATEGY_VERSION_CODE = "v1"
STAGE = "M4_HISTORICAL_SIGNAL_GENERATION_DESIGN_DRY_RUN"
SOURCE_STAGE = "M5_HISTORICAL_BACKTEST_REQUEST_DESIGN_DRY_RUN"
DEFAULT_SOURCE_ARTIFACT_DIR = Path("artifacts") / "m5" / "historical_backtest_request_design"
DEFAULT_OUTPUT_DIR = Path("artifacts") / "m4" / "historical_signal_generation_design"
DEFAULT_SIGNAL_ROLE = "SELECTION"
DEFAULT_SIGNAL_SIDE = "LONG"
DEFAULT_SIGNAL_ACTION = "CANDIDATE"
DEFAULT_SUBJECT_TYPE = "INSTRUMENT"

CHECK_COLUMNS = ("check_name", "status", "row_count", "detail")
SIGNAL_BATCH_COLUMNS = (
    "sequence_no",
    "signal_as_of_date",
    "entry_effective_date",
    "signal_role",
    "signal_side",
    "signal_action",
    "target_top_n",
    "expected_signal_rows",
    "write_mode",
    "status",
    "detail",
)
DEPENDENCY_COLUMNS = (
    "dependency_name",
    "domain",
    "required_date_role",
    "required_before_generation",
    "status",
    "detail",
)
FEATURE_REQUIREMENT_COLUMNS = (
    "feature_name",
    "feature_scope",
    "required_on_date_role",
    "lookahead_guardrail",
    "status",
    "detail",
)
WRITE_BOUNDARY_COLUMNS = (
    "boundary_name",
    "allowed_now",
    "status",
    "detail",
)
ACTION_COLUMNS = ("severity", "item", "reason", "next_step")

REGIME_DISPLAY_LABELS: dict[str, str] = {
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

CANDIDATE_STRATEGY_CONFIG: dict[str, dict[str, str]] = {
    "RISK_ON": {
        "candidate_strategy_code": "trend_growth_strategy",
        "candidate_strategy_name": "Trend Growth Strategy",
        "candidate_strategy_bucket": "trend_growth",
        "candidate_strategy_reason": "confirmed_regime=RISK_ON; prioritize trend, momentum, industry strength, and tradability",
    },
    "NEUTRAL": {
        "candidate_strategy_code": "range_pullback_quality_strategy",
        "candidate_strategy_name": "Range Pullback Quality Strategy",
        "candidate_strategy_bucket": "range_pullback_quality",
        "candidate_strategy_reason": "confirmed_regime=NEUTRAL; prioritize quality proxy, lower volatility, tradability, and industry strength",
    },
    "RISK_OFF": {
        "candidate_strategy_code": "risk_off_defensive_strategy",
        "candidate_strategy_name": "Risk-off Defensive Strategy",
        "candidate_strategy_bucket": "risk_off_defensive",
        "candidate_strategy_reason": "confirmed_regime=RISK_OFF; prioritize lower volatility, tradability, defensive score, and industry resilience",
    },
    "UNKNOWN": {
        "candidate_strategy_code": "range_pullback_quality_strategy",
        "candidate_strategy_name": "Range Pullback Quality Strategy",
        "candidate_strategy_bucket": "range_pullback_quality",
        "candidate_strategy_reason": "confirmed_regime=UNKNOWN; fallback to balanced range-quality proxy until regime is confirmed",
    },
}


def candidate_strategy_config_for_regime_local(market_regime: str | None) -> dict[str, str]:
    return CANDIDATE_STRATEGY_CONFIG.get(str(market_regime or "UNKNOWN"), CANDIDATE_STRATEGY_CONFIG["UNKNOWN"])


def market_regime_display_label_local(market_regime: str | None) -> str:
    return REGIME_DISPLAY_LABELS.get(str(market_regime or "UNKNOWN"), str(market_regime or "UNKNOWN"))


def route_name_for_regime_local(market_regime: str | None) -> str:
    return REGIME_ROUTE_NAMES.get(str(market_regime or "UNKNOWN"), REGIME_ROUTE_NAMES["UNKNOWN"])


REGIME_CONFIRMATION_WINDOW_DAYS = 5
REGIME_CONFIRMATION_MIN_MATCHES = 3
REGIME_MIN_DAYS_IN_STATE = 5
REGIME_FAST_RISK_OFF_RET_20_THRESHOLD = Decimal("-0.05")
REGIME_FAST_RISK_OFF_BREADTH_THRESHOLD = Decimal("0.25")


def regime_transition_flag(confirmed: str, previous: str | None, raw: str) -> str:
    if previous is None:
        return "INITIAL"
    if confirmed != previous:
        return "CONFIRMED_SWITCH"
    if raw != confirmed:
        return "RAW_DIVERGENCE_WAITING_CONFIRMATION"
    return "STABLE"


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


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    text_value = str(value).strip()
    if not text_value:
        return None
    try:
        return float(Decimal(text_value))
    except Exception:
        return None


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y"}


def status_from_checks(checks: Sequence[Mapping[str, Any]]) -> str:
    statuses = {str(row.get("status", "")).upper() for row in checks}
    if "FAIL" in statuses:
        return "FAIL"
    if "WARN" in statuses:
        return "PASS_WITH_WARN"
    return "PASS"


def count_status(rows: Sequence[Mapping[str, Any]], status: str) -> int:
    expected = status.upper()
    return sum(1 for row in rows if str(row.get("status", "")).upper() == expected)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json_default(row.get(key, "")) for key in fieldnames})


def find_artifact_file(directory: Path, stem_prefix: str, report_date: str, suffix: str) -> Path:
    exact = directory / f"{stem_prefix}_{report_date}.{suffix}"
    if exact.exists():
        return exact
    matches = sorted(directory.glob(f"{stem_prefix}_*.{suffix}"))
    if not matches:
        return exact
    return matches[-1]


@dataclass(frozen=True)
class RegimeSectorIndustryHistoricalSignalGenerationDesignConfig:
    report_date: str
    historical_request_artifact_dir: Path = DEFAULT_SOURCE_ARTIFACT_DIR
    output_dir: Path = DEFAULT_OUTPUT_DIR
    strategy_code: str = STRATEGY_CODE
    strategy_version_code: str = DEFAULT_STRATEGY_VERSION_CODE
    research_backtest_request_id: int | None = None
    benchmark_index_code: str = "000300.SH"
    target_top_n: int = 100
    max_signal_batches: int = 120
    min_signal_pairs: int = 20


@dataclass(frozen=True)
class HistoricalSignalGenerationDesignArtifacts:
    json_path: str
    markdown_path: str
    contract_check_csv_path: str
    signal_batch_plan_csv_path: str
    dependency_plan_csv_path: str
    feature_requirements_csv_path: str
    write_boundary_csv_path: str
    action_items_csv_path: str


@dataclass(frozen=True)
class RegimeSectorIndustryHistoricalSignalGenerationDesignResult:
    status: str
    generated_at: str
    report_date: str
    strategy_code: str
    strategy_version_code: str
    stage: str
    source_stage: str
    source_historical_request_status: str | None
    research_backtest_request_id: int | None
    source_signal_run_id: int | None
    benchmark_index_code: str
    summary: dict[str, Any]
    validation_decision: dict[str, Any]
    contract_check: list[dict[str, Any]]
    signal_batch_plan: list[dict[str, Any]]
    dependency_plan: list[dict[str, Any]]
    feature_requirements: list[dict[str, Any]]
    write_boundary: list[dict[str, Any]]
    action_items: list[dict[str, Any]]
    artifacts: HistoricalSignalGenerationDesignArtifacts | None = None


@dataclass(frozen=True)
class RegimeSectorIndustryHistoricalSignalGenerationDesignTaskResult:
    result: RegimeSectorIndustryHistoricalSignalGenerationDesignResult


class RegimeSectorIndustryHistoricalSignalGenerationDesignService:
    def __init__(self, engine: Engine | None) -> None:
        self.engine = engine

    def design(
        self,
        config: RegimeSectorIndustryHistoricalSignalGenerationDesignConfig,
        *,
        progress_callback: Callable[[str], None] | None = None,
    ) -> RegimeSectorIndustryHistoricalSignalGenerationDesignResult:
        def progress(message: str) -> None:
            if progress_callback:
                progress_callback(message)

        source_dir = Path(config.historical_request_artifact_dir)
        output_dir = Path(config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        source_json_path = find_artifact_file(source_dir, "m5_historical_backtest_request_design", config.report_date, "json")
        source_payload = read_json(source_json_path) if source_json_path.exists() else {}
        progress(f"HISTORICAL_REQUEST_ARTIFACT_LOADED status={source_payload.get('status')} json={source_json_path}")

        source_summary = dict(source_payload.get("summary") or {})
        source_validation = dict(source_payload.get("validation_decision") or {})
        source_signal_plan = list(source_payload.get("signal_generation_plan") or [])
        source_data_requirements = list(source_payload.get("data_requirements") or [])

        request_id = config.research_backtest_request_id or safe_int(source_payload.get("research_backtest_request_id")) or safe_int(source_summary.get("research_backtest_request_id"))
        source_signal_run_id = safe_int(source_payload.get("source_signal_run_id")) or safe_int(source_summary.get("source_signal_run_id"))
        source_status = source_payload.get("status")
        planned_start = source_summary.get("planned_historical_start_date")
        planned_end = source_summary.get("planned_historical_end_date")
        planned_days = safe_int(source_summary.get("planned_historical_trading_day_count")) or 0
        source_signal_profile = dict(source_summary.get("source_signal_profile") or {})

        strategy_version_profile = self._inspect_strategy_version(config.strategy_code, config.strategy_version_code)
        table_profile = self._inspect_dependency_tables()
        signal_batch_plan = self._build_signal_batch_plan(
            source_signal_plan,
            target_top_n=config.target_top_n,
            max_rows=config.max_signal_batches,
        )
        dependency_plan = self._build_dependency_plan(
            table_profile=table_profile,
            source_data_requirements=source_data_requirements,
            planned_start=str(planned_start or ""),
            planned_end=str(planned_end or ""),
            benchmark_index_code=config.benchmark_index_code,
        )
        feature_requirements = self._build_feature_requirements()
        write_boundary = self._build_write_boundary()
        checks = self._build_contract_checks(
            source_json_present=source_json_path.exists(),
            source_status=source_status,
            source_allows_m4_design=bool_value(source_validation.get("can_start_m4_historical_signal_generation_design")),
            source_blocks_request_write_now=not bool_value(source_validation.get("can_start_m5_historical_backtest_request_write_preview")),
            source_blocks_backtest_now=not bool_value(source_validation.get("can_execute_backtest_now")),
            request_id=request_id,
            source_signal_run_id=source_signal_run_id,
            planned_days=planned_days,
            signal_pair_count=len([row for row in source_signal_plan if str(row.get("status", "")).upper() in {"PLANNED", "PASS", "WARN"}]),
            min_signal_pairs=config.min_signal_pairs,
            strategy_version_profile=strategy_version_profile,
            source_signal_profile=source_signal_profile,
        )
        status = status_from_checks(checks)
        actions = self._build_action_items(checks, dependency_plan, feature_requirements)

        signal_pair_count = len(signal_batch_plan)
        expected_signal_rows = sum(safe_int(row.get("expected_signal_rows")) or 0 for row in signal_batch_plan if str(row.get("status", "")).upper() == "PLANNED")
        blocker_count = count_status(checks, "FAIL")
        warn_count = (
            count_status(checks, "WARN")
            + count_status(dependency_plan, "WARN")
            + count_status(feature_requirements, "WARN")
            + count_status(write_boundary, "WARN")
        )

        summary = {
            "research_backtest_request_id": request_id,
            "source_signal_run_id": source_signal_run_id,
            "source_historical_request_status": source_status,
            "planned_historical_start_date": planned_start,
            "planned_historical_end_date": planned_end,
            "planned_historical_trading_day_count": planned_days,
            "planned_signal_pair_count": signal_pair_count,
            "target_top_n": config.target_top_n,
            "expected_signal_rows": expected_signal_rows,
            "benchmark_index_code": config.benchmark_index_code,
            "strategy_version_profile": strategy_version_profile,
            "source_signal_profile": source_signal_profile,
            "write_mode": "DESIGN_ARTIFACT_ONLY",
        }
        decision = {
            "manual_review_required": True,
            "blocker_count": blocker_count,
            "warn_count": warn_count,
            "can_start_m4_historical_signal_generation_preview_dry_run": status != "FAIL",
            "can_start_m4_historical_signal_db_write_preview": False,
            "can_start_m5_historical_backtest_request_write_preview": False,
            "can_start_m5_formal_backtest_executor_design": False,
            "can_execute_backtest_now": False,
            "can_create_research_backtest_result_now": False,
            "can_start_m5_backtest_result_write_preview": False,
            "can_route_to_paper_trading_now": False,
            "can_start_m6_paper_trading": False,
            "performance_claim_allowed": False,
            "historical_signal_generation_scope_locked": status != "FAIL",
            "historical_signal_db_write_allowed_now": False,
            "interpretation_scope": "m4_historical_signal_generation_design_artifact_only",
            "next_research_step": "Run M4 historical signal generation preview dry-run; do not write strategy_signal until preview coverage is validated.",
        }

        result = RegimeSectorIndustryHistoricalSignalGenerationDesignResult(
            status=status,
            generated_at=utc_now_iso(),
            report_date=config.report_date,
            strategy_code=config.strategy_code,
            strategy_version_code=config.strategy_version_code,
            stage=STAGE,
            source_stage=SOURCE_STAGE,
            source_historical_request_status=source_status,
            research_backtest_request_id=request_id,
            source_signal_run_id=source_signal_run_id,
            benchmark_index_code=config.benchmark_index_code,
            summary=summary,
            validation_decision=decision,
            contract_check=checks,
            signal_batch_plan=signal_batch_plan,
            dependency_plan=dependency_plan,
            feature_requirements=feature_requirements,
            write_boundary=write_boundary,
            action_items=actions,
            artifacts=None,
        )
        artifacts = self._write_artifacts(output_dir, config.report_date, result)
        return RegimeSectorIndustryHistoricalSignalGenerationDesignResult(**{**asdict(result), "artifacts": artifacts})

    def _inspect_strategy_version(self, strategy_code: str, strategy_version_code: str) -> dict[str, Any]:
        profile = {
            "query_status": "SKIPPED",
            "strategy_code": strategy_code,
            "strategy_version_code": strategy_version_code,
            "strategy_definition_id": None,
            "strategy_version_id": None,
            "version_status": None,
        }
        if self.engine is None:
            return profile
        try:
            with self.engine.connect() as conn:
                has_definition = conn.execute(text("select to_regclass('strategy_definition') is not null")).scalar()
                has_version = conn.execute(text("select to_regclass('strategy_version') is not null")).scalar()
                if not has_definition or not has_version:
                    profile["query_status"] = "MISSING_TABLE"
                    return profile
                columns = self._table_columns(conn, "strategy_version")
                version_code_column = "version_code" if "version_code" in columns else "code" if "code" in columns else None
                status_expr = "sv.status" if "status" in columns else "cast(null as text)"
                if version_code_column is None:
                    profile["query_status"] = "MISSING_VERSION_CODE_COLUMN"
                    return profile
                row = conn.execute(
                    text(
                        f"""
                        select sd.id as strategy_definition_id,
                               sv.id as strategy_version_id,
                               {status_expr} as version_status
                        from strategy_definition sd
                        join strategy_version sv on sv.strategy_definition_id = sd.id
                        where sd.strategy_code = :strategy_code
                          and sv.{version_code_column} = :strategy_version_code
                        order by sv.id desc
                        limit 1
                        """
                    ),
                    {"strategy_code": strategy_code, "strategy_version_code": strategy_version_code},
                ).mappings().first()
                if row:
                    profile.update({key: json_default(value) if value is not None else None for key, value in dict(row).items()})
                    profile["query_status"] = "PASS"
                else:
                    profile["query_status"] = "NOT_FOUND"
                return profile
        except Exception as exc:
            profile["query_status"] = "ERROR"
            profile["error"] = str(exc)[:500]
            return profile

    def _inspect_dependency_tables(self) -> dict[str, Any]:
        tables = [
            "meta_trading_calendar",
            "strategy_signal",
            "core_daily_bar",
            "market_index_bar",
            "analytics_feature_snapshot",
            "strategy_definition",
            "strategy_version",
        ]
        profile: dict[str, Any] = {"query_status": "SKIPPED", "tables": {}}
        if self.engine is None:
            profile["tables"] = {table: "SKIPPED" for table in tables}
            return profile
        try:
            with self.engine.connect() as conn:
                profile["tables"] = {
                    table: "PRESENT" if conn.execute(text("select to_regclass(:table_name) is not null"), {"table_name": table}).scalar() else "MISSING"
                    for table in tables
                }
                profile["query_status"] = "PASS"
                return profile
        except Exception as exc:
            profile["query_status"] = "ERROR"
            profile["error"] = str(exc)[:500]
            return profile

    def _table_columns(self, conn: Any, table_name: str) -> set[str]:
        rows = conn.execute(
            text(
                """
                select column_name
                from information_schema.columns
                where table_schema = current_schema()
                  and table_name = :table_name
                """
            ),
            {"table_name": table_name},
        ).all()
        return {str(row[0]) for row in rows}

    def _build_signal_batch_plan(
        self,
        source_signal_plan: Sequence[Mapping[str, Any]],
        *,
        target_top_n: int,
        max_rows: int,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        planned_rows = [row for row in source_signal_plan if str(row.get("status", "")).upper() in {"PLANNED", "PASS", "WARN"}]
        for idx, row in enumerate(planned_rows[: max(1, max_rows)], start=1):
            rows.append(
                {
                    "sequence_no": safe_int(row.get("sequence_no")) or idx,
                    "signal_as_of_date": row.get("signal_as_of_date"),
                    "entry_effective_date": row.get("entry_effective_date"),
                    "signal_role": DEFAULT_SIGNAL_ROLE,
                    "signal_side": DEFAULT_SIGNAL_SIDE,
                    "signal_action": DEFAULT_SIGNAL_ACTION,
                    "target_top_n": target_top_n,
                    "expected_signal_rows": target_top_n,
                    "write_mode": "DESIGN_ARTIFACT_ONLY",
                    "status": "PLANNED",
                    "detail": "Historical M4 signal preview should generate candidate rows for this as_of/effective pair without writing strategy_signal.",
                }
            )
        if len(planned_rows) > max_rows:
            rows.append(
                {
                    "sequence_no": max_rows + 1,
                    "signal_as_of_date": "TRUNCATED",
                    "entry_effective_date": "TRUNCATED",
                    "signal_role": DEFAULT_SIGNAL_ROLE,
                    "signal_side": DEFAULT_SIGNAL_SIDE,
                    "signal_action": DEFAULT_SIGNAL_ACTION,
                    "target_top_n": target_top_n,
                    "expected_signal_rows": 0,
                    "write_mode": "DESIGN_ARTIFACT_ONLY",
                    "status": "WARN",
                    "detail": f"Source plan contains {len(planned_rows)} rows; CSV preview capped at {max_rows}.",
                }
            )
        if not rows:
            rows.append(
                {
                    "sequence_no": 1,
                    "signal_as_of_date": "TO_RESOLVE_FROM_M5_HISTORICAL_DESIGN",
                    "entry_effective_date": "TO_RESOLVE_FROM_M5_HISTORICAL_DESIGN",
                    "signal_role": DEFAULT_SIGNAL_ROLE,
                    "signal_side": DEFAULT_SIGNAL_SIDE,
                    "signal_action": DEFAULT_SIGNAL_ACTION,
                    "target_top_n": target_top_n,
                    "expected_signal_rows": 0,
                    "write_mode": "DESIGN_ARTIFACT_ONLY",
                    "status": "WARN",
                    "detail": "No usable signal generation plan was found in the M5 historical request design artifact.",
                }
            )
        return rows

    def _build_dependency_plan(
        self,
        *,
        table_profile: Mapping[str, Any],
        source_data_requirements: Sequence[Mapping[str, Any]],
        planned_start: str,
        planned_end: str,
        benchmark_index_code: str,
    ) -> list[dict[str, Any]]:
        table_status = dict(table_profile.get("tables") or {})

        def status_for_table(table_name: str) -> str:
            value = str(table_status.get(table_name, "SKIPPED")).upper()
            if value == "MISSING":
                return "FAIL"
            if value == "PRESENT":
                return "PASS"
            return "WARN"

        window = f"{planned_start}..{planned_end}" if planned_start and planned_end else "TO_RESOLVE"
        return [
            {
                "dependency_name": "meta_trading_calendar",
                "domain": "M1/M2 metadata",
                "required_date_role": "signal_as_of_date and entry_effective_date calendar",
                "required_before_generation": True,
                "status": status_for_table("meta_trading_calendar"),
                "detail": f"Calendar must define historical signal/effective pairs for window={window}.",
            },
            {
                "dependency_name": "analytics_feature_snapshot",
                "domain": "M3 analytics_domain",
                "required_date_role": "signal_as_of_date",
                "required_before_generation": True,
                "status": status_for_table("analytics_feature_snapshot"),
                "detail": "Feature snapshots must be available on every signal_as_of_date; coverage dry-run is required before DB write.",
            },
            {
                "dependency_name": "core_daily_bar",
                "domain": "M2 data_domain",
                "required_date_role": "signal_as_of_date and entry_effective_date",
                "required_before_generation": True,
                "status": status_for_table("core_daily_bar"),
                "detail": "Scoring and later execution preview require stock daily bars for the resolved historical universe.",
            },
            {
                "dependency_name": "market_index_bar",
                "domain": "M2 data_domain",
                "required_date_role": "signal_as_of_date and benchmark evaluation dates",
                "required_before_generation": True,
                "status": status_for_table("market_index_bar"),
                "detail": f"Benchmark {benchmark_index_code} and regime index bars must cover the historical window.",
            },
            {
                "dependency_name": "strategy_signal",
                "domain": "M4 strategy_domain",
                "required_date_role": "DB write target later, not now",
                "required_before_generation": False,
                "status": status_for_table("strategy_signal"),
                "detail": "Table presence is checked for later write-preview compatibility; this design step does not write it.",
            },
            {
                "dependency_name": "coverage_preflight_after_preview_universe",
                "domain": "M2/M3/M4 cross-domain",
                "required_date_role": "after preview universe is resolved",
                "required_before_generation": True,
                "status": "WARN",
                "detail": "Historical signal preview must emit actual instruments before precise M2/M3 coverage can be fully validated.",
            },
        ]

    def _build_feature_requirements(self) -> list[dict[str, Any]]:
        feature_rows = [
            ("feat_industry_strength_20", "industry/SW_INDUSTRY_L2", "Must use as_of_date snapshot only; no effective-date price leakage."),
            ("feat_mom_20", "instrument", "Momentum must be computed using data available at signal_as_of_date."),
            ("feat_trend_strength_20", "instrument", "Trend strength must be computed using data available at signal_as_of_date."),
            ("feat_volatility_rank_20", "instrument", "Volatility rank must be computed using data available at signal_as_of_date."),
            ("feat_tradability_score", "instrument", "Tradability gate must be evaluated before ranking and cannot use future fills."),
            ("feat_tradable_flag", "instrument", "Non-tradable rows must not enter executable candidate output."),
            ("market_regime", "market", "Regime classification must use breadth/index state up to signal_as_of_date."),
        ]
        return [
            {
                "feature_name": name,
                "feature_scope": scope,
                "required_on_date_role": "signal_as_of_date",
                "lookahead_guardrail": guardrail,
                "status": "WARN",
                "detail": "Coverage is intentionally not asserted in design; next preview dry-run must check actual availability for every date.",
            }
            for name, scope, guardrail in feature_rows
        ]

    def _build_write_boundary(self) -> list[dict[str, Any]]:
        return [
            {
                "boundary_name": "strategy_signal_db_write",
                "allowed_now": False,
                "status": "PASS",
                "detail": "Historical signal DB write is blocked until preview rows and coverage pass validation.",
            },
            {
                "boundary_name": "research_backtest_request_write",
                "allowed_now": False,
                "status": "PASS",
                "detail": "Historical M5 request write is blocked until historical M4 signal generation is validated.",
            },
            {
                "boundary_name": "formal_backtest_execution",
                "allowed_now": False,
                "status": "PASS",
                "detail": "Backtest execution is blocked in M4 design stage.",
            },
            {
                "boundary_name": "research_backtest_result_write",
                "allowed_now": False,
                "status": "PASS",
                "detail": "Result rows cannot be written before formal engine execution and result gate validation.",
            },
            {
                "boundary_name": "paper_trading_route",
                "allowed_now": False,
                "status": "PASS",
                "detail": "M6 routing remains blocked throughout M4/M5 historical design.",
            },
        ]

    def _build_contract_checks(
        self,
        *,
        source_json_present: bool,
        source_status: Any,
        source_allows_m4_design: bool,
        source_blocks_request_write_now: bool,
        source_blocks_backtest_now: bool,
        request_id: int | None,
        source_signal_run_id: int | None,
        planned_days: int,
        signal_pair_count: int,
        min_signal_pairs: int,
        strategy_version_profile: Mapping[str, Any],
        source_signal_profile: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        preview_as_of_count = safe_int(source_signal_profile.get("distinct_as_of_dates")) or 0
        return [
            {
                "check_name": "historical_request_json_present",
                "status": "PASS" if source_json_present else "FAIL",
                "row_count": 1 if source_json_present else 0,
                "detail": f"present={source_json_present}",
            },
            {
                "check_name": "source_historical_request_status",
                "status": "PASS" if str(source_status) in {"PASS", "PASS_WITH_WARN"} else "FAIL",
                "row_count": 1 if source_status else 0,
                "detail": f"status={source_status}",
            },
            {
                "check_name": "source_allows_m4_historical_signal_design",
                "status": "PASS" if source_allows_m4_design else "FAIL",
                "row_count": 1 if source_allows_m4_design else 0,
                "detail": f"can_start_m4_historical_signal_generation_design={source_allows_m4_design}",
            },
            {
                "check_name": "m5_request_write_still_blocked",
                "status": "PASS" if source_blocks_request_write_now else "FAIL",
                "row_count": 1 if source_blocks_request_write_now else 0,
                "detail": "M4 design must start before M5 historical request write is allowed.",
            },
            {
                "check_name": "backtest_execution_still_blocked",
                "status": "PASS" if source_blocks_backtest_now else "FAIL",
                "row_count": 1 if source_blocks_backtest_now else 0,
                "detail": "Backtest execution must remain blocked in historical signal design.",
            },
            {
                "check_name": "research_backtest_request_id_present",
                "status": "PASS" if request_id is not None else "FAIL",
                "row_count": 1 if request_id is not None else 0,
                "detail": f"request_id={request_id}",
            },
            {
                "check_name": "source_signal_run_id_present",
                "status": "PASS" if source_signal_run_id is not None else "FAIL",
                "row_count": 1 if source_signal_run_id is not None else 0,
                "detail": f"source_signal_run_id={source_signal_run_id}",
            },
            {
                "check_name": "historical_span_days_available",
                "status": "PASS" if planned_days >= min_signal_pairs else "WARN",
                "row_count": planned_days,
                "detail": f"planned_days={planned_days}; min_signal_pairs={min_signal_pairs}",
            },
            {
                "check_name": "signal_generation_pairs_present",
                "status": "PASS" if signal_pair_count >= min_signal_pairs else "WARN",
                "row_count": signal_pair_count,
                "detail": f"signal_pair_count={signal_pair_count}; min_signal_pairs={min_signal_pairs}",
            },
            {
                "check_name": "strategy_version_resolved",
                "status": "PASS" if strategy_version_profile.get("query_status") in {"PASS", "SKIPPED"} else "WARN",
                "row_count": 1 if strategy_version_profile.get("strategy_version_id") else 0,
                "detail": json.dumps(strategy_version_profile, ensure_ascii=False, default=json_default),
            },
            {
                "check_name": "source_signal_is_preview_only",
                "status": "WARN" if preview_as_of_count <= 1 else "PASS",
                "row_count": preview_as_of_count,
                "detail": "Current source_signal_run is expected to be one-day preview; historical signals still need generation.",
            },
        ]

    def _build_action_items(
        self,
        checks: Sequence[Mapping[str, Any]],
        dependency_plan: Sequence[Mapping[str, Any]],
        feature_requirements: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        actions = [
            {
                "severity": "REQUIRED",
                "item": "Run historical signal preview dry-run",
                "reason": "This design has date pairs and feature requirements but does not generate historical signal rows.",
                "next_step": "Build M4 historical signal generation preview dry-run over the planned as_of/effective date pairs.",
            },
            {
                "severity": "REQUIRED",
                "item": "Check M2/M3 coverage on actual preview universe",
                "reason": "Precise stock universe is only known after historical preview rows are produced.",
                "next_step": "After preview generation, run coverage preflight for feature snapshots and entry/exit prices.",
            },
            {
                "severity": "REQUIRED",
                "item": "Keep DB write disabled",
                "reason": "Historical signal generation must be reviewed before writing strategy_signal rows.",
                "next_step": "Do not start M4 signal DB write preview until preview artifacts pass validation.",
            },
        ]
        if any(str(row.get("status", "")).upper() == "FAIL" for row in checks):
            actions.insert(
                0,
                {
                    "severity": "BLOCKER",
                    "item": "Fix historical signal design blockers",
                    "reason": "One or more source contract checks failed.",
                    "next_step": "Do not start historical signal preview generation until blockers are resolved.",
                },
            )
        return actions

    def _write_artifacts(
        self,
        output_dir: Path,
        report_date: str,
        result: RegimeSectorIndustryHistoricalSignalGenerationDesignResult,
    ) -> HistoricalSignalGenerationDesignArtifacts:
        json_path = output_dir / f"m4_historical_signal_generation_design_{report_date}.json"
        markdown_path = output_dir / f"m4_historical_signal_generation_design_{report_date}.md"
        contract_check_path = output_dir / f"m4_historical_signal_generation_contract_check_{report_date}.csv"
        signal_batch_plan_path = output_dir / f"m4_historical_signal_generation_batch_plan_{report_date}.csv"
        dependency_plan_path = output_dir / f"m4_historical_signal_generation_dependency_plan_{report_date}.csv"
        feature_requirements_path = output_dir / f"m4_historical_signal_generation_feature_requirements_{report_date}.csv"
        write_boundary_path = output_dir / f"m4_historical_signal_generation_write_boundary_{report_date}.csv"
        action_items_path = output_dir / f"m4_historical_signal_generation_action_items_{report_date}.csv"

        artifact_payload = asdict(result)
        artifact_payload["artifacts"] = None
        json_path.write_text(json.dumps(artifact_payload, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
        write_csv(contract_check_path, result.contract_check, CHECK_COLUMNS)
        write_csv(signal_batch_plan_path, result.signal_batch_plan, SIGNAL_BATCH_COLUMNS)
        write_csv(dependency_plan_path, result.dependency_plan, DEPENDENCY_COLUMNS)
        write_csv(feature_requirements_path, result.feature_requirements, FEATURE_REQUIREMENT_COLUMNS)
        write_csv(write_boundary_path, result.write_boundary, WRITE_BOUNDARY_COLUMNS)
        write_csv(action_items_path, result.action_items, ACTION_COLUMNS)
        markdown_path.write_text(self._build_markdown(result), encoding="utf-8")
        return HistoricalSignalGenerationDesignArtifacts(
            json_path=str(json_path),
            markdown_path=str(markdown_path),
            contract_check_csv_path=str(contract_check_path),
            signal_batch_plan_csv_path=str(signal_batch_plan_path),
            dependency_plan_csv_path=str(dependency_plan_path),
            feature_requirements_csv_path=str(feature_requirements_path),
            write_boundary_csv_path=str(write_boundary_path),
            action_items_csv_path=str(action_items_path),
        )

    def _build_markdown(self, result: RegimeSectorIndustryHistoricalSignalGenerationDesignResult) -> str:
        summary = result.summary
        decision = result.validation_decision
        lines = [
            f"# M4 Historical Signal Generation Design - {result.report_date}",
            "",
            f"- status: `{result.status}`",
            f"- request_id: `{result.research_backtest_request_id}`",
            f"- source_signal_run_id: `{result.source_signal_run_id}`",
            f"- planned_historical_window: `{summary.get('planned_historical_start_date')}` .. `{summary.get('planned_historical_end_date')}`",
            f"- planned_signal_pair_count: `{summary.get('planned_signal_pair_count')}`",
            f"- target_top_n: `{summary.get('target_top_n')}`",
            f"- expected_signal_rows: `{summary.get('expected_signal_rows')}`",
            f"- can_start_m4_historical_signal_generation_preview_dry_run: `{decision.get('can_start_m4_historical_signal_generation_preview_dry_run')}`",
            f"- can_start_m4_historical_signal_db_write_preview: `{decision.get('can_start_m4_historical_signal_db_write_preview')}`",
            f"- can_execute_backtest_now: `{decision.get('can_execute_backtest_now')}`",
            "",
            "## Boundary",
            "",
            "This artifact designs historical M4 signal generation only. It does not generate strategy_signal rows, write DB rows, execute backtests, or route to M6.",
        ]
        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Historical signal generation preview dry-run
# ---------------------------------------------------------------------------
# This is intentionally kept in the existing historical_signal_generation_design
# module instead of adding another service file. The goal is to reuse the design
# artifact and keep the M4 historical signal pipeline consolidated while the
# feature is still being validated.

HISTORICAL_PREVIEW_STAGE = "M4_HISTORICAL_SIGNAL_GENERATION_PREVIEW_DRY_RUN"
HISTORICAL_PREVIEW_WRITE_MODE = "HISTORICAL_PREVIEW_ARTIFACT_ONLY"
DEFAULT_HISTORICAL_PREVIEW_OUTPUT_DIR = Path("artifacts") / "m4" / "historical_signal_generation_preview"

HISTORICAL_PREVIEW_SCORING_MODE_BASE = "base"
HISTORICAL_PREVIEW_SCORING_MODE_CLEANED_V1_1 = "cleaned_v1_1"
HISTORICAL_PREVIEW_SCORING_MODES = {
    HISTORICAL_PREVIEW_SCORING_MODE_BASE,
    HISTORICAL_PREVIEW_SCORING_MODE_CLEANED_V1_1,
}

# Stage 6.19B-1D keeps historical cleaned v1.1 generation in the
# existing historical preview path. It is artifact-only and is used only as an
# M5 validation input candidate. It must not write strategy_signal or route to
# production.
CONCEPT_TAG_TYPE = "CONCEPT_EM"
CONCEPT_TAXONOMY_SOURCE = "EASTMONEY"
INDUSTRY_TAXONOMY_SOURCE = "SW_2021"

GENERIC_CONCEPT_TAG_NAMES: frozenset[str] = frozenset(
    {
        "融资融券", "沪股通", "深股通", "富时罗素", "标普道琼斯A股", "MSCI概念",
        "证金持股", "QFII重仓", "机构重仓", "社保重仓", "基金重仓",
        "百元股", "小盘股", "中盘股", "大盘股", "低价股", "高价股", "周期股", "微利股",
        "创业板综", "上证180", "上证380", "深证100R", "深成500", "中证500", "中证1000", "沪深300",
        "标准普尔", "HS300_", "创业成份",
        "昨日涨停", "昨日连板", "昨日触板", "昨日高振幅", "昨日高换手",
        "近期新高", "百日新高", "历史新高", "东方财富热股", "同花顺热股", "热门股",
        "破净股", "破发股", "预盈预增", "股权激励", "送转填权", "转债标的", "注册制次新股", "次新股", "ST股",
        "最近多板", "2025年报扭亏", "2025年报预减", "2025年报预增", "2026—季报预增", "养老金",
    }
)
GENERIC_CONCEPT_KEYWORDS: tuple[str, ...] = (
    "融资融券", "沪股通", "深股通", "QFII", "机构重仓", "基金重仓", "社保重仓",
    "百元股", "小盘股", "中盘股", "大盘股", "创业板综", "标准普尔", "HS300", "创业成份", "昨日", "新高", "热股",
    "高振幅", "高换手", "多板", "破发", "年报", "季报", "扭亏", "预减", "养老金", "次新股", "ST股",
    "周期股", "微利股", "股权激励",
)
CONCEPT_TAG_CLASS_TRUE_THEME = "L7_TRUE_THEME"
CONCEPT_TAG_CLASS_STYLE = "L8_STYLE"
CONCEPT_TAG_CLASS_STATE_EVENT = "L5_STATE_EVENT"
CONCEPT_TAG_CLASS_INDEX_CHANNEL = "INDEX_CHANNEL"
CONCEPT_TAG_CLASS_HOLDING_STRUCTURE = "L9_HOLDING_STRUCTURE"
CONCEPT_TAG_CLASS_POLICY_ATTRIBUTE = "POLICY_ATTRIBUTE"
CONCEPT_TAG_CLASS_GENERIC_OTHER = "GENERIC_OTHER"

INDEX_CHANNEL_TAG_NAMES: frozenset[str] = frozenset(
    {
        "融资融券", "沪股通", "深股通", "富时罗素", "标普道琼斯A股",
        "MSCI概念", "MSCI中国", "标准普尔", "标普道琼斯A股", "上证180", "上证380", "深证100R",
        "深成500", "中证500", "中证1000", "沪深300", "HS300_", "创业板综", "创业成份",
    }
)
INDEX_CHANNEL_KEYWORDS: tuple[str, ...] = ("沪股通", "深股通", "MSCI", "富时罗素", "标准普尔", "标普", "HS300", "创业成份", "中证", "上证", "深成", "沪深")

STYLE_TAG_NAMES: frozenset[str] = frozenset(
    {"小盘股", "中盘股", "大盘股", "低价股", "高价股", "百元股", "小盘成长", "中盘成长", "大盘成长", "周期股", "微利股"}
)
STYLE_TAG_KEYWORDS: tuple[str, ...] = ("小盘", "中盘", "大盘", "低价", "高价", "百元股", "成长", "价值", "红利", "周期股", "微利股")

STATE_EVENT_TAG_NAMES: frozenset[str] = frozenset(
    {
        "昨日涨停", "昨日连板", "昨日触板", "昨日高振幅", "昨日高换手",
        "近期新高", "百日新高", "历史新高", "东方财富热股", "同花顺热股",
        "热门股", "最近多板", "破净股", "破发股", "预盈预增", "股权激励", "2025年报预增",
        "2025年报扭亏", "2025年报预减", "2026—季报预增", "送转填权",
        "注册制次新股", "次新股", "ST股",
    }
)
STATE_EVENT_KEYWORDS: tuple[str, ...] = ("昨日", "新高", "热股", "高振幅", "高换手", "多板", "预增", "预盈", "年报", "季报", "扭亏", "预减", "破净", "破发", "股权激励", "次新", "ST")

HOLDING_STRUCTURE_TAG_NAMES: frozenset[str] = frozenset({"证金持股", "QFII重仓", "机构重仓", "社保重仓", "基金重仓", "养老金"})
HOLDING_STRUCTURE_KEYWORDS: tuple[str, ...] = ("重仓", "持股", "QFII", "基金", "机构", "社保", "证金", "养老金")

POLICY_ATTRIBUTE_TAG_NAMES: frozenset[str] = frozenset(
    {"专精特新", "央企改革", "国企改革", "一带一路", "深圳特区", "雄安新区", "共同富裕示范区", "长江三角", "西部大开发"}
)
POLICY_ATTRIBUTE_KEYWORDS: tuple[str, ...] = ("专精特新", "改革", "一带一路", "特区", "新区", "示范区", "长江三角", "西部大开发")

NON_THEME_CONCEPT_TAG_CLASSES: frozenset[str] = frozenset(
    {
        CONCEPT_TAG_CLASS_STYLE,
        CONCEPT_TAG_CLASS_STATE_EVENT,
        CONCEPT_TAG_CLASS_INDEX_CHANNEL,
        CONCEPT_TAG_CLASS_HOLDING_STRUCTURE,
        CONCEPT_TAG_CLASS_POLICY_ATTRIBUTE,
        CONCEPT_TAG_CLASS_GENERIC_OTHER,
    }
)


HISTORICAL_PREVIEW_SIGNAL_COLUMNS = (
    "preview_signal_id",
    "signal_write_mode",
    "strategy_code",
    "strategy_stage",
    "source_stage",
    "source_design_stage",
    "sequence_no",
    "source_feature_date",
    "feature_date_lag_days",
    "run_id",
    "strategy_version_id",
    "strategy_version_code",
    "as_of_date",
    "effective_date",
    "subject_type",
    "subject_key",
    "instrument_id",
    "signal_role",
    "signal_side",
    "signal_action",
    "raw_score",
    "normalized_score",
    "confidence_score",
    "rank_in_batch",
    "universe_size",
    "reason_code",
    "reason_payload_json",
    "parameter_payload_json",
    "instrument_code",
    "display_name",
    "industry_tag_code",
    "industry_tag_name",
    "market_regime",
    "raw_market_regime",
    "confirmed_market_regime",
    "market_regime_display",
    "route_name",
    "candidate_strategy_code",
    "candidate_strategy_name",
    "candidate_strategy_bucket",
    "candidate_strategy_score",
    "candidate_strategy_rank_in_batch",
    "candidate_strategy_reason",
    "regime_confidence",
    "regime_days_in_state",
    "regime_transition_flag",
    "regime_reason_code",
    "regime_reason_summary",
    "reason_summary",
    "stock_alpha_score",
    "risk_penalty_score",
    "feat_industry_strength_20",
    "feat_mom_20",
    "feat_trend_strength_20",
    "feat_volatility_rank_20",
    "feat_tradability_score",
    "feat_tradable_flag",
    "preview_scoring_mode",
    "base_final_preview_score",
    "base_normalized_score_for_v1_1",
    "selection_score",
    "selection_score_source",
    "pct_change",
    "amount",
    "volume",
    "turnover_rate",
    "amount_pct_rank",
    "volume_pct_rank",
    "turnover_rate_pct_rank",
    "capital_activity_score",
    "capital_activity_status",
    "concept_count",
    "concept_names",
    "concept_score",
    "concept_status",
    "concept_top_drivers_json",
    "cleaned_concept_count",
    "cleaned_concept_names",
    "cleaned_concept_score",
    "cleaned_concept_status",
    "cleaned_concept_top_drivers_json",
    "true_theme_count",
    "true_theme_names",
    "true_theme_score",
    "true_theme_top_drivers_json",
    "style_tag_count",
    "style_tag_names",
    "state_event_tag_count",
    "state_event_tag_names",
    "index_channel_tag_count",
    "index_channel_tag_names",
    "holding_structure_tag_count",
    "holding_structure_tag_names",
    "policy_attribute_tag_count",
    "policy_attribute_tag_names",
    "other_tag_count",
    "other_tag_names",
    "filtered_generic_concept_count",
    "filtered_generic_concept_names",
    "concept_cleaning_status",
    "tag_classification_status",
    "sw_l2_names",
    "sw_l3_names",
    "v1_1_preview_score",
    "v1_1_score_delta",
    "cleaned_v1_1_preview_score",
    "cleaned_v1_1_score_delta",
    "v1_1_scoring_mode",
)

HISTORICAL_PREVIEW_BATCH_COLUMNS = (
    "sequence_no",
    "signal_as_of_date",
    "entry_effective_date",
    "source_feature_date",
    "feature_date_lag_days",
    "market_regime",
    "raw_market_regime",
    "confirmed_market_regime",
    "market_regime_display",
    "route_name",
    "candidate_strategy_code",
    "candidate_strategy_name",
    "candidate_strategy_bucket",
    "regime_confidence",
    "regime_days_in_state",
    "regime_transition_flag",
    "regime_reason_code",
    "score_input_row_count",
    "eligible_candidate_count",
    "preview_signal_row_count",
    "expected_signal_rows",
    "preview_scoring_mode",
    "cleaned_v1_1_score_count",
    "true_theme_score_count",
    "capital_activity_score_count",
    "required_feature_pass_count",
    "required_feature_warn_count",
    "required_feature_fail_count",
    "status",
    "detail",
)

HISTORICAL_PREVIEW_COVERAGE_COLUMNS = (
    "sequence_no",
    "signal_as_of_date",
    "source_feature_date",
    "feature_code",
    "required",
    "row_count",
    "ready_rows",
    "ready_instrument_count",
    "min_value",
    "max_value",
    "avg_value",
    "status",
    "quality_issue",
)

HISTORICAL_PREVIEW_ACTION_COLUMNS = ACTION_COLUMNS

HISTORICAL_REGIME_DAILY_PROFILE_COLUMNS = (
    "sequence_no",
    "trade_date",
    "signal_as_of_date",
    "source_feature_date",
    "raw_market_regime",
    "previous_confirmed_market_regime",
    "confirmed_market_regime",
    "market_regime_display",
    "route_name",
    "regime_confidence",
    "regime_days_in_state",
    "regime_transition_flag",
    "regime_reason_code",
    "regime_reason_summary",
    "benchmark_ret_20",
    "advancer_ratio",
    "benchmark_index_code",
    "lookback_days",
    "profile_status",
)


@dataclass(frozen=True)
class RegimeSectorIndustryHistoricalSignalGenerationPreviewConfig:
    report_date: str
    design_artifact_dir: Path = DEFAULT_OUTPUT_DIR
    output_dir: Path = DEFAULT_HISTORICAL_PREVIEW_OUTPUT_DIR
    strategy_code: str = STRATEGY_CODE
    strategy_version_code: str = DEFAULT_STRATEGY_VERSION_CODE
    research_backtest_request_id: int | None = None
    benchmark_index_code: str = "000300.SH"
    target_top_n: int = 100
    max_signal_batches: int = 120
    min_preview_rows_per_batch: int = 50
    feature_set_code: str = "fs_daily_alpha_v1"
    feature_set_version: str = "v1"
    industry_tag_type: str = "SW_INDUSTRY_L2"
    lookback_days: int = 20
    preview_scoring_mode: str = HISTORICAL_PREVIEW_SCORING_MODE_BASE


@dataclass(frozen=True)
class HistoricalSignalGenerationPreviewArtifacts:
    json_path: str
    markdown_path: str
    signal_preview_rows_csv_path: str
    batch_summary_csv_path: str
    feature_coverage_csv_path: str
    action_items_csv_path: str
    historical_regime_daily_profile_csv_path: str


@dataclass(frozen=True)
class RegimeSectorIndustryHistoricalSignalGenerationPreviewResult:
    status: str
    generated_at: str
    report_date: str
    strategy_code: str
    strategy_version_code: str
    stage: str
    source_stage: str
    research_backtest_request_id: int | None
    benchmark_index_code: str
    summary: dict[str, Any]
    validation_decision: dict[str, Any]
    batch_summary: list[dict[str, Any]]
    feature_coverage: list[dict[str, Any]]
    action_items: list[dict[str, Any]]
    artifacts: HistoricalSignalGenerationPreviewArtifacts | None = None


@dataclass(frozen=True)
class RegimeSectorIndustryHistoricalSignalGenerationPreviewTaskResult:
    result: RegimeSectorIndustryHistoricalSignalGenerationPreviewResult


class RegimeSectorIndustryHistoricalSignalGenerationPreviewService:
    """Generate historical strategy-signal preview artifacts without DB writes.

    This class intentionally lives in the existing historical signal generation
    design module. It reuses the design artifact and the existing M4 S2 scoring
    rules. It does not write strategy_signal and does not create M5 requests or
    results.
    """

    def __init__(self, engine: Engine | None) -> None:
        self.engine = engine

    def preview(
        self,
        config: RegimeSectorIndustryHistoricalSignalGenerationPreviewConfig,
        *,
        progress_callback: Callable[[str], None] | None = None,
    ) -> RegimeSectorIndustryHistoricalSignalGenerationPreviewResult:
        def progress(message: str) -> None:
            if progress_callback:
                progress_callback(message)

        source_dir = Path(config.design_artifact_dir)
        output_dir = Path(config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        design_json_path = find_artifact_file(source_dir, "m4_historical_signal_generation_design", config.report_date, "json")
        design_payload = read_json(design_json_path) if design_json_path.exists() else {}
        progress(f"DESIGN_ARTIFACT_LOADED status={design_payload.get('status')} json={design_json_path}")

        source_decision = dict(design_payload.get("validation_decision") or {})
        source_summary = dict(design_payload.get("summary") or {})
        request_id = config.research_backtest_request_id or safe_int(design_payload.get("research_backtest_request_id")) or safe_int(source_summary.get("research_backtest_request_id"))
        source_batch_plan = list(design_payload.get("signal_batch_plan") or [])
        planned_batches = [row for row in source_batch_plan if str(row.get("status", "")).upper() in {"PLANNED", "PASS", "WARN"}]
        planned_batches = planned_batches[: max(1, config.max_signal_batches)]

        action_items: list[dict[str, Any]] = []
        preview_rows: list[dict[str, Any]] = []
        batch_summary: list[dict[str, Any]] = []
        feature_coverage: list[dict[str, Any]] = []

        if not design_json_path.exists():
            action_items.append(self._action("BLOCKER", "design_artifact_missing", f"No design json found under {source_dir}.", "Rerun M4 historical signal generation design first."))
        if str(design_payload.get("status")) not in {"PASS", "PASS_WITH_WARN"}:
            action_items.append(self._action("BLOCKER", "design_status", f"Design status is {design_payload.get('status')}.", "Resolve design blockers before preview dry-run."))
        if not bool_value(source_decision.get("can_start_m4_historical_signal_generation_preview_dry_run")):
            action_items.append(self._action("BLOCKER", "preview_gate_closed", "Design artifact did not open the historical preview gate.", "Rerun design or resolve source gate issues."))
        if not planned_batches:
            action_items.append(self._action("BLOCKER", "planned_batches_missing", "No planned signal/effective-date pairs were found.", "Rerun historical request/span design."))
        if self.engine is None:
            action_items.append(self._action("BLOCKER", "db_engine_missing", "A DB engine is required to generate historical preview rows.", "Run this task from the project environment with V2_SQLALCHEMY_URL configured."))

        regime_history_rows: list[dict[str, Any]] = []

        if not any(item.get("severity") == "BLOCKER" for item in action_items):
            with self.engine.connect() as conn:  # type: ignore[union-attr]
                resolved_batches: list[dict[str, Any]] = []
                for index, batch in enumerate(planned_batches, start=1):
                    sequence_no = safe_int(batch.get("sequence_no")) or index
                    signal_as_of_date = self._parse_date(batch.get("signal_as_of_date"))
                    entry_effective_date = self._parse_date(batch.get("entry_effective_date"))
                    if signal_as_of_date is None or entry_effective_date is None:
                        batch_summary.append(
                            self._batch_summary_row(
                                sequence_no=sequence_no,
                                signal_as_of_date=batch.get("signal_as_of_date"),
                                entry_effective_date=batch.get("entry_effective_date"),
                                status="FAIL",
                                detail="Missing or invalid signal_as_of_date / entry_effective_date.",
                                expected_signal_rows=safe_int(batch.get("expected_signal_rows")) or config.target_top_n,
                            )
                        )
                        continue
                    resolved_batches.append({"sequence_no": sequence_no, "signal_as_of_date": signal_as_of_date, "entry_effective_date": entry_effective_date})

                regime_state_by_sequence = self._build_confirmed_regime_history(conn, batches=resolved_batches, config=config)
                regime_history_rows = [regime_state_by_sequence[row["sequence_no"]] for row in resolved_batches if row["sequence_no"] in regime_state_by_sequence]

                for batch in resolved_batches:
                    sequence_no = int(batch["sequence_no"])
                    signal_as_of_date = batch["signal_as_of_date"]
                    entry_effective_date = batch["entry_effective_date"]

                    score_result = self._score_one_batch(
                        conn,
                        sequence_no=sequence_no,
                        signal_as_of_date=signal_as_of_date,
                        entry_effective_date=entry_effective_date,
                        config=config,
                        confirmed_regime_state=regime_state_by_sequence.get(sequence_no),
                    )
                    batch_summary.append(score_result["batch_summary"])
                    feature_coverage.extend(score_result["feature_coverage"])
                    preview_rows.extend(score_result["preview_rows"])
                    progress(
                        "BATCH_PREVIEW "
                        f"sequence_no={sequence_no} "
                        f"as_of={signal_as_of_date} "
                        f"effective={entry_effective_date} "
                        f"status={score_result['batch_summary'].get('status')} "
                        f"rows={score_result['batch_summary'].get('preview_signal_row_count')} "
                        f"raw_regime={score_result['batch_summary'].get('raw_market_regime')} "
                        f"confirmed_regime={score_result['batch_summary'].get('confirmed_market_regime')}"
                    )

        fail_batches = count_status(batch_summary, "FAIL")
        warn_batches = count_status(batch_summary, "WARN")
        blocker_count = sum(1 for item in action_items if item.get("severity") == "BLOCKER") + fail_batches
        warn_count = sum(1 for item in action_items if item.get("severity") == "WARN") + warn_batches
        status = "FAIL" if blocker_count > 0 else "PASS_WITH_WARN" if warn_count > 0 else "PASS"

        if not preview_rows and blocker_count == 0:
            status = "FAIL"
            blocker_count += 1
            action_items.append(self._action("BLOCKER", "preview_rows_empty", "No historical preview rows were generated.", "Check M2/M3 feature coverage for the historical window."))

        if blocker_count == 0:
            action_items.extend(
                [
                    self._action("WARN", "artifact_only_boundary", "Historical signal preview was generated as files only; strategy_signal DB write remains disabled.", "Review artifacts before starting historical signal DB write preview."),
                    self._action("WARN", "reuse_existing_pipeline", "This patch reuses the existing historical signal generation module and does not add a new script/service file.", "After validation, fold this preview path into the stable M4 signal generation task."),
                ]
            )
            warn_count += 2
            if status == "PASS":
                status = "PASS_WITH_WARN"

        processed_batches = len(batch_summary)
        expected_signal_rows = sum(safe_int(row.get("expected_signal_rows")) or 0 for row in batch_summary)
        preview_signal_row_count = len(preview_rows)
        distinct_as_of_dates = len({str(row.get("as_of_date")) for row in preview_rows if row.get("as_of_date")})
        zero_row_batches = sum(1 for row in batch_summary if (safe_int(row.get("preview_signal_row_count")) or 0) == 0)
        raw_regime_transitions = self._count_regime_transitions(regime_history_rows, "raw_market_regime")
        confirmed_regime_transitions = self._count_regime_transitions(regime_history_rows, "confirmed_market_regime")
        one_day_confirmed_state_count = self._count_one_day_confirmed_states(regime_history_rows)
        confirmed_regime_counts = self._count_values(regime_history_rows, "confirmed_market_regime")
        raw_regime_counts = self._count_values(regime_history_rows, "raw_market_regime")
        historical_regime_daily_profile_rows = self._build_historical_regime_daily_profile_rows(regime_history_rows, config)

        if blocker_count == 0 and raw_regime_transitions > confirmed_regime_transitions:
            action_items.append(
                self._action(
                    "WARN",
                    "market_regime_state_machine_applied",
                    f"Raw regime transitions={raw_regime_transitions}; confirmed regime transitions={confirmed_regime_transitions} after hysteresis/min-hold smoothing.",
                    "Review raw/confirmed market regime fields and use confirmed_market_regime for route decisions.",
                )
            )
            warn_count += 1
            if status == "PASS":
                status = "PASS_WITH_WARN"

        summary = {
            "research_backtest_request_id": request_id,
            "planned_signal_pair_count": len(planned_batches),
            "processed_signal_pair_count": processed_batches,
            "distinct_as_of_dates": distinct_as_of_dates,
            "target_top_n": config.target_top_n,
            "expected_signal_rows": expected_signal_rows,
            "preview_signal_row_count": preview_signal_row_count,
            "zero_row_batch_count": zero_row_batches,
            "preview_scoring_mode": config.preview_scoring_mode,
            "cleaned_v1_1_score_count": sum(1 for row in preview_rows if self._to_decimal(row.get("cleaned_v1_1_preview_score")) is not None),
            "true_theme_score_count": sum(1 for row in preview_rows if self._to_decimal(row.get("true_theme_score")) is not None),
            "capital_activity_score_count": sum(1 for row in preview_rows if self._to_decimal(row.get("capital_activity_score")) is not None),
            "feature_set_code": config.feature_set_code,
            "feature_set_version": config.feature_set_version,
            "industry_tag_type": config.industry_tag_type,
            "benchmark_index_code": config.benchmark_index_code,
            "market_regime_confirmation_policy": {
                "raw_regime_used_for": "diagnostic_only",
                "confirmed_regime_used_for": "strategy_route_and_score",
                "confirmation_window_days": REGIME_CONFIRMATION_WINDOW_DAYS,
                "confirmation_min_matches": REGIME_CONFIRMATION_MIN_MATCHES,
                "min_days_in_state": REGIME_MIN_DAYS_IN_STATE,
                "fast_risk_off_ret_20_threshold": str(REGIME_FAST_RISK_OFF_RET_20_THRESHOLD),
                "fast_risk_off_breadth_threshold": str(REGIME_FAST_RISK_OFF_BREADTH_THRESHOLD),
            },
            "raw_regime_counts": raw_regime_counts,
            "confirmed_regime_counts": confirmed_regime_counts,
            "historical_regime_daily_profile_row_count": len(historical_regime_daily_profile_rows),
            "historical_regime_daily_profile_ready": bool(historical_regime_daily_profile_rows),
            "raw_regime_transition_count": raw_regime_transitions,
            "confirmed_regime_transition_count": confirmed_regime_transitions,
            "one_day_confirmed_state_count": one_day_confirmed_state_count,
            "write_mode": HISTORICAL_PREVIEW_WRITE_MODE,
            "file_reuse_decision": {
                "new_files_added_by_this_patch": 0,
                "modified_existing_files": [
                    "src/stock_quant_v2/strategy_domain/services/regime_sector_industry_historical_signal_generation_design_service.py",
                    "src/stock_quant_v2/strategy_domain/tasks/build_regime_sector_industry_historical_signal_generation_design.py",
                    "src/stock_quant_v2/scripts/bootstrap_m4_historical_signal_generation_design.py",
                    "tests/strategy/test_regime_sector_industry_historical_signal_generation_design_service.py",
                ],
                "reason": "Preview dry-run is a continuation of historical signal generation design, so it is kept in the existing M4 historical signal module instead of creating another service/script file.",
            },
        }
        decision = {
            "manual_review_required": True,
            "blocker_count": blocker_count,
            "warn_count": warn_count,
            "can_start_m4_historical_signal_db_write_preview": status != "FAIL",
            "can_write_strategy_signal_now": False,
            "can_start_m5_historical_backtest_request_write_preview": False,
            "can_execute_backtest_now": False,
            "can_create_research_backtest_result_now": False,
            "can_start_m5_backtest_result_write_preview": False,
            "can_route_to_paper_trading_now": False,
            "performance_claim_allowed": False,
            "historical_signal_preview_only": True,
            "historical_regime_daily_profile_artifact_only": True,
            "cleaned_v1_1_historical_preview_artifact_only": config.preview_scoring_mode == HISTORICAL_PREVIEW_SCORING_MODE_CLEANED_V1_1,
            "can_use_historical_regime_daily_profile_for_window_search": bool(historical_regime_daily_profile_rows),
            "next_research_step": "Review historical signal preview and historical_regime_daily_profile artifacts, then use the regime profile for artifact-backed follow-up window candidate search before any DB write or backtest.",
        }

        result = RegimeSectorIndustryHistoricalSignalGenerationPreviewResult(
            status=status,
            generated_at=utc_now_iso(),
            report_date=config.report_date,
            strategy_code=config.strategy_code,
            strategy_version_code=config.strategy_version_code,
            stage=HISTORICAL_PREVIEW_STAGE,
            source_stage=STAGE,
            research_backtest_request_id=request_id,
            benchmark_index_code=config.benchmark_index_code,
            summary=summary,
            validation_decision=decision,
            batch_summary=batch_summary,
            feature_coverage=feature_coverage,
            action_items=action_items,
            artifacts=None,
        )
        artifacts = self._write_preview_artifacts(
            output_dir,
            config.report_date,
            result,
            preview_rows,
            historical_regime_daily_profile_rows,
        )
        return RegimeSectorIndustryHistoricalSignalGenerationPreviewResult(**{**asdict(result), "artifacts": artifacts})


    def _build_confirmed_regime_history(
        self,
        conn: Any,
        *,
        batches: Sequence[Mapping[str, Any]],
        config: RegimeSectorIndustryHistoricalSignalGenerationPreviewConfig,
    ) -> dict[int, dict[str, Any]]:
        try:
            from stock_quant_v2.strategy_domain.services.regime_sector_industry_rule_validation_service import (
                classify_market_regime,
                quantize,
                to_decimal,
            )
        except Exception:
            classify_market_regime = None  # type: ignore[assignment]
            quantize = self._quantize  # type: ignore[assignment]
            to_decimal = self._to_decimal  # type: ignore[assignment]

        raw_rows: list[dict[str, Any]] = []
        for batch in batches:
            sequence_no = safe_int(batch.get("sequence_no"))
            signal_as_of_date = self._parse_date(batch.get("signal_as_of_date"))
            if sequence_no is None or signal_as_of_date is None:
                continue
            feature_date = self._resolve_feature_date(
                conn,
                requested_date=signal_as_of_date,
                feature_set_code=config.feature_set_code,
                feature_set_version=config.feature_set_version,
            )
            if feature_date is None:
                market_inputs: dict[str, Any] = {}
                raw_regime = "UNKNOWN"
            else:
                market_inputs = self._load_historical_market_inputs(
                    conn,
                    trade_date=feature_date,
                    benchmark_index_code=config.benchmark_index_code,
                    lookback_days=config.lookback_days,
                )
                raw_regime = "UNKNOWN"
                if classify_market_regime is not None:
                    raw_regime = classify_market_regime(
                        index_ret_20=market_inputs.get("benchmark_ret_20"),
                        advancer_ratio=market_inputs.get("advancer_ratio"),
                    )
            raw_rows.append(
                {
                    "sequence_no": sequence_no,
                    "signal_as_of_date": signal_as_of_date,
                    "source_feature_date": feature_date,
                    "raw_market_regime": raw_regime,
                    "market_inputs": market_inputs,
                }
            )

        raw_rows.sort(key=lambda row: (row.get("signal_as_of_date") or date.min, safe_int(row.get("sequence_no")) or 0))
        result: dict[int, dict[str, Any]] = {}
        history: list[str] = []
        confirmed: str | None = None
        days_in_state = 0

        for row in raw_rows:
            raw_regime = str(row.get("raw_market_regime") or "UNKNOWN")
            previous_confirmed = confirmed
            history.append(raw_regime)
            window = history[-REGIME_CONFIRMATION_WINDOW_DAYS:]
            raw_count = window.count(raw_regime)
            market_inputs = dict(row.get("market_inputs") or {})
            ret_20 = to_decimal(market_inputs.get("benchmark_ret_20"))
            breadth = to_decimal(market_inputs.get("advancer_ratio"))
            fast_risk_off = raw_regime == "RISK_OFF" and (
                (ret_20 is not None and ret_20 <= REGIME_FAST_RISK_OFF_RET_20_THRESHOLD)
                or (breadth is not None and breadth <= REGIME_FAST_RISK_OFF_BREADTH_THRESHOLD)
            )

            reason_code = "REGIME_STABLE"
            if confirmed is None:
                confirmed = raw_regime
                days_in_state = 1
                reason_code = "INITIAL_STATE"
            elif fast_risk_off and confirmed != "RISK_OFF":
                confirmed = "RISK_OFF"
                days_in_state = 1
                reason_code = "FAST_RISK_OFF_TRIGGER"
            elif raw_regime == confirmed:
                days_in_state += 1
                reason_code = "REGIME_STABLE"
            elif days_in_state < REGIME_MIN_DAYS_IN_STATE:
                days_in_state += 1
                reason_code = "MIN_DAYS_IN_STATE_HOLD"
            elif raw_count >= REGIME_CONFIRMATION_MIN_MATCHES:
                confirmed = raw_regime
                days_in_state = 1
                reason_code = "CONFIRMED_BY_3_OF_5"
            else:
                days_in_state += 1
                reason_code = "RAW_DIVERGENCE_WAITING_CONFIRMATION"

            confirmed_count = window.count(confirmed) if confirmed else 0
            confidence = quantize(Decimal(confirmed_count) / Decimal(max(1, len(window))))
            transition_flag = regime_transition_flag(confirmed, previous_confirmed, raw_regime)
            reason_summary = self._regime_reason_summary(
                raw_market_regime=raw_regime,
                confirmed_market_regime=confirmed,
                previous_confirmed_market_regime=previous_confirmed,
                reason_code=reason_code,
                confidence=confidence,
                days_in_state=days_in_state,
                window=window,
                fast_risk_off=fast_risk_off,
                market_inputs=market_inputs,
            )
            state = {
                **row,
                "previous_confirmed_market_regime": previous_confirmed,
                "confirmed_market_regime": confirmed,
                "market_regime_display": market_regime_display_label_local(confirmed),
                "route_name": route_name_for_regime_local(confirmed),
                "regime_confidence": confidence,
                "regime_days_in_state": days_in_state,
                "regime_transition_flag": transition_flag,
                "regime_reason_code": reason_code,
                "regime_reason_summary": reason_summary,
            }
            result[int(row["sequence_no"])] = state
        return result

    def _single_regime_state(
        self,
        *,
        sequence_no: int,
        signal_as_of_date: date,
        source_feature_date: date | None,
        raw_market_regime: str,
        market_inputs: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "sequence_no": sequence_no,
            "signal_as_of_date": signal_as_of_date,
            "source_feature_date": source_feature_date,
            "raw_market_regime": raw_market_regime,
            "previous_confirmed_market_regime": None,
            "confirmed_market_regime": raw_market_regime,
            "market_regime_display": market_regime_display_label_local(raw_market_regime),
            "route_name": route_name_for_regime_local(raw_market_regime),
            "regime_confidence": Decimal("1.0000000000"),
            "regime_days_in_state": 1,
            "regime_transition_flag": "SINGLE_DAY_PREVIEW",
            "regime_reason_code": "SINGLE_DAY_NO_HISTORY",
            "regime_reason_summary": "单日预览没有完整历史状态机上下文；仅用于S2/S3即时诊断，历史/生产路由必须使用confirmed_market_regime。",
            "market_inputs": dict(market_inputs),
        }

    def _regime_reason_summary(
        self,
        *,
        raw_market_regime: str,
        confirmed_market_regime: str,
        previous_confirmed_market_regime: str | None,
        reason_code: str,
        confidence: Any,
        days_in_state: int,
        window: Sequence[str],
        fast_risk_off: bool,
        market_inputs: Mapping[str, Any],
    ) -> str:
        display = market_regime_display_label_local(confirmed_market_regime)
        raw_display = market_regime_display_label_local(raw_market_regime)
        ret_20 = market_inputs.get("benchmark_ret_20")
        breadth = market_inputs.get("advancer_ratio")
        window_text = "/".join(window)
        if fast_risk_off:
            trigger = "触发快速RISK_OFF防守条件"
        elif reason_code == "CONFIRMED_BY_3_OF_5":
            trigger = "最近窗口满足3/5确认条件"
        elif reason_code == "MIN_DAYS_IN_STATE_HOLD":
            trigger = f"仍处于最短{REGIME_MIN_DAYS_IN_STATE}个交易日驻留期"
        elif reason_code == "RAW_DIVERGENCE_WAITING_CONFIRMATION":
            trigger = "raw状态出现分歧但尚未满足切换确认"
        elif reason_code == "INITIAL_STATE":
            trigger = "历史窗口首日初始化"
        else:
            trigger = "confirmed状态保持稳定"
        return (
            f"raw_market_regime={raw_display}（内部码={raw_market_regime}），"
            f"confirmed_market_regime={display}（内部码={confirmed_market_regime}），"
            f"上一确认状态={previous_confirmed_market_regime or 'NONE'}，"
            f"状态原因={reason_code}：{trigger}；"
            f"确认状态已持续{days_in_state}个信号日，confidence={confidence}，"
            f"最近窗口raw序列={window_text}；"
            f"benchmark_ret_20={ret_20}，advancer_ratio={breadth}。"
        )

    def _count_regime_transitions(self, rows: Sequence[Mapping[str, Any]], key: str) -> int:
        previous: str | None = None
        count = 0
        for row in rows:
            current = str(row.get(key) or "")
            if previous is not None and current != previous:
                count += 1
            previous = current
        return count

    def _count_one_day_confirmed_states(self, rows: Sequence[Mapping[str, Any]]) -> int:
        if not rows:
            return 0
        segments: list[int] = []
        previous: str | None = None
        current_len = 0
        for row in rows:
            current = str(row.get("confirmed_market_regime") or "")
            if previous is None or current == previous:
                current_len += 1
            else:
                segments.append(current_len)
                current_len = 1
            previous = current
        segments.append(current_len)
        return sum(1 for value in segments if value == 1)

    def _count_values(self, rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in rows:
            value = str(row.get(key) or "UNKNOWN")
            counts[value] = counts.get(value, 0) + 1
        return counts


    def _build_historical_regime_daily_profile_rows(
        self,
        regime_history_rows: Sequence[Mapping[str, Any]],
        config: RegimeSectorIndustryHistoricalSignalGenerationPreviewConfig,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for row in sorted(
            regime_history_rows,
            key=lambda item: (item.get("signal_as_of_date") or item.get("source_feature_date") or date.min, safe_int(item.get("sequence_no")) or 0),
        ):
            market_inputs = dict(row.get("market_inputs") or {})
            source_feature_date = row.get("source_feature_date")
            signal_as_of_date = row.get("signal_as_of_date")
            # The profile is a daily regime series for window search, so trade_date
            # must represent the signal/as-of trading day. source_feature_date is
            # kept separately to audit feature lag and avoid accidental future data use.
            trade_date = signal_as_of_date or source_feature_date
            rows.append(
                {
                    "sequence_no": row.get("sequence_no"),
                    "trade_date": trade_date,
                    "signal_as_of_date": signal_as_of_date,
                    "source_feature_date": source_feature_date,
                    "raw_market_regime": row.get("raw_market_regime"),
                    "previous_confirmed_market_regime": row.get("previous_confirmed_market_regime"),
                    "confirmed_market_regime": row.get("confirmed_market_regime"),
                    "market_regime_display": row.get("market_regime_display"),
                    "route_name": row.get("route_name"),
                    "regime_confidence": row.get("regime_confidence"),
                    "regime_days_in_state": row.get("regime_days_in_state"),
                    "regime_transition_flag": row.get("regime_transition_flag"),
                    "regime_reason_code": row.get("regime_reason_code"),
                    "regime_reason_summary": row.get("regime_reason_summary"),
                    "benchmark_ret_20": market_inputs.get("benchmark_ret_20"),
                    "advancer_ratio": market_inputs.get("advancer_ratio"),
                    "benchmark_index_code": config.benchmark_index_code,
                    "lookback_days": config.lookback_days,
                    "profile_status": "READY_FOR_WINDOW_SEARCH",
                }
            )
        return rows


    def _score_one_batch(
        self,
        conn: Any,
        *,
        sequence_no: int,
        signal_as_of_date: date,
        entry_effective_date: date,
        config: RegimeSectorIndustryHistoricalSignalGenerationPreviewConfig,
        confirmed_regime_state: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            from stock_quant_v2.strategy_domain.services.regime_sector_industry_rule_validation_service import (
                ALL_VALIDATION_FEATURE_CODES,
                REQUIRED_FEATURE_CODES,
                classify_market_regime,
                feature_quality_status,
                final_preview_score,
                quantize,
                market_regime_display_label,
                reason_code_for_row,
                reason_summary_for_row,
                risk_penalty_score,
                route_name_for_regime,
                stock_alpha_score,
                to_decimal,
            )
        except Exception as exc:
            return {
                "batch_summary": self._batch_summary_row(
                    sequence_no=sequence_no,
                    signal_as_of_date=signal_as_of_date,
                    entry_effective_date=entry_effective_date,
                    status="FAIL",
                    detail=f"Unable to import existing S2 scoring helpers: {str(exc)[:300]}",
                    expected_signal_rows=config.target_top_n,
                ),
                "feature_coverage": [],
                "preview_rows": [],
            }

        try:
            feature_date = self._resolve_feature_date(
                conn,
                requested_date=signal_as_of_date,
                feature_set_code=config.feature_set_code,
                feature_set_version=config.feature_set_version,
            )
            if feature_date is None:
                return {
                    "batch_summary": self._batch_summary_row(
                        sequence_no=sequence_no,
                        signal_as_of_date=signal_as_of_date,
                        entry_effective_date=entry_effective_date,
                        status="FAIL",
                        detail="No analytics_feature_snapshot ready date found on or before signal_as_of_date.",
                        expected_signal_rows=config.target_top_n,
                    ),
                    "feature_coverage": [],
                    "preview_rows": [],
                }

            if confirmed_regime_state is not None:
                market_inputs = dict(confirmed_regime_state.get("market_inputs") or {})
                raw_market_regime = str(confirmed_regime_state.get("raw_market_regime") or "UNKNOWN")
                market_regime = str(confirmed_regime_state.get("confirmed_market_regime") or raw_market_regime)
            else:
                market_inputs = self._load_historical_market_inputs(
                    conn,
                    trade_date=feature_date,
                    benchmark_index_code=config.benchmark_index_code,
                    lookback_days=config.lookback_days,
                )
                raw_market_regime = classify_market_regime(
                    index_ret_20=market_inputs.get("benchmark_ret_20"),
                    advancer_ratio=market_inputs.get("advancer_ratio"),
                )
                confirmed_regime_state = self._single_regime_state(
                    sequence_no=sequence_no,
                    signal_as_of_date=signal_as_of_date,
                    source_feature_date=feature_date,
                    raw_market_regime=raw_market_regime,
                    market_inputs=market_inputs,
                )
                market_regime = str(confirmed_regime_state.get("confirmed_market_regime") or raw_market_regime)

            coverage_rows = self._load_historical_feature_coverage(
                conn,
                sequence_no=sequence_no,
                signal_as_of_date=signal_as_of_date,
                feature_date=feature_date,
                feature_set_code=config.feature_set_code,
                feature_set_version=config.feature_set_version,
                industry_tag_type=config.industry_tag_type,
                all_feature_codes=list(ALL_VALIDATION_FEATURE_CODES),
                required_feature_codes=set(REQUIRED_FEATURE_CODES),
                feature_quality_status=feature_quality_status,
            )
            required_fail_count = sum(
                1 for row in coverage_rows if bool_value(row.get("required")) and str(row.get("status", "")).upper() == "FAIL"
            )
            required_warn_count = sum(
                1 for row in coverage_rows if bool_value(row.get("required")) and str(row.get("status", "")).upper() == "WARN"
            )
            required_pass_count = sum(
                1 for row in coverage_rows if bool_value(row.get("required")) and str(row.get("status", "")).upper() == "PASS"
            )

            score_input_rows = self._load_historical_score_input_rows(
                conn,
                trade_date=feature_date,
                feature_set_code=config.feature_set_code,
                feature_set_version=config.feature_set_version,
                industry_tag_type=config.industry_tag_type,
                all_feature_codes=list(ALL_VALIDATION_FEATURE_CODES),
            )

            tag_by_instrument: dict[int, dict[str, Any]] = {}
            if str(config.preview_scoring_mode) == HISTORICAL_PREVIEW_SCORING_MODE_CLEANED_V1_1:
                instrument_ids = sorted(
                    {
                        int(value)
                        for value in (safe_int(row.get("instrument_id")) for row in score_input_rows)
                        if value is not None
                    }
                )
                tag_by_instrument = self._aggregate_historical_tag_enrichment(
                    self._load_historical_tag_enrichment(conn, as_of_date=feature_date, instrument_ids=instrument_ids)
                )

            scored_rows: list[dict[str, Any]] = []
            for raw_row in score_input_rows:
                row = dict(raw_row)
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
                base_score = final_preview_score(
                    market_regime=market_regime,
                    industry_strength_20=row.get("feat_industry_strength_20"),
                    alpha_score=alpha,
                    risk_penalty=risk,
                )
                candidate_strategy = self._candidate_strategy_context(
                    row,
                    market_regime=market_regime,
                    alpha_score=alpha,
                    risk_penalty_score_value=risk,
                    base_score=base_score,
                )
                final_score = candidate_strategy.get("candidate_strategy_score") or base_score
                row["stock_alpha_score"] = alpha
                row["risk_penalty_score"] = risk
                row["base_preview_score"] = base_score
                row["final_preview_score"] = final_score
                row.update(candidate_strategy)
                row["market_regime"] = market_regime
                row["raw_market_regime"] = raw_market_regime
                row["confirmed_market_regime"] = market_regime
                row["market_regime_display"] = market_regime_display_label(market_regime)
                row["route_name"] = route_name_for_regime(market_regime)
                row["regime_confidence"] = confirmed_regime_state.get("regime_confidence")
                row["regime_days_in_state"] = confirmed_regime_state.get("regime_days_in_state")
                row["regime_transition_flag"] = confirmed_regime_state.get("regime_transition_flag")
                row["regime_reason_code"] = confirmed_regime_state.get("regime_reason_code")
                row["regime_reason_summary"] = confirmed_regime_state.get("regime_reason_summary")
                row["reason_code"] = reason_code_for_row(row, market_regime=market_regime)
                row["reason_summary"] = reason_summary_for_row(row, market_regime=market_regime)
                row["is_candidate"] = row["reason_code"] not in {"FILTER_NOT_TRADABLE", "FILTER_MISSING_SCORE_INPUT"}
                if str(config.preview_scoring_mode) == HISTORICAL_PREVIEW_SCORING_MODE_CLEANED_V1_1:
                    tags = tag_by_instrument.get(safe_int(row.get("instrument_id")) or -1, {})
                    self._apply_historical_tag_enrichment(row, tags)
                else:
                    self._apply_empty_historical_v1_1_fields(row)
                scored_rows.append(row)

            eligible_rows = [row for row in scored_rows if row.get("is_candidate")]
            self._apply_historical_selection_scores(eligible_rows, preview_scoring_mode=str(config.preview_scoring_mode))
            eligible_rows.sort(
                key=lambda row: (self._to_decimal(row.get("selection_score")) or Decimal("-999"), str(row.get("instrument_code") or "")),
                reverse=True,
            )
            preview_source_rows = eligible_rows[: max(0, config.target_top_n)]
            for candidate_strategy_rank, row in enumerate(preview_source_rows, start=1):
                row["candidate_strategy_rank_in_batch"] = candidate_strategy_rank
            numeric_scores = [to_decimal(row.get("selection_score")) for row in preview_source_rows]
            numeric_scores = [value for value in numeric_scores if value is not None]
            min_score = min(numeric_scores) if numeric_scores else Decimal("0")
            max_score = max(numeric_scores) if numeric_scores else Decimal("0")
            feature_lag_days = (signal_as_of_date - feature_date).days
            preview_rows: list[dict[str, Any]] = []
            universe_size = len(eligible_rows)
            for rank, row in enumerate(preview_source_rows, start=1):
                raw_score = row.get("final_preview_score")
                normalized_score = self._min_max_normalize(raw_score, min_value=min_score, max_value=max_score)
                confidence = self._historical_confidence_score(
                    normalized_score=normalized_score,
                    risk_penalty_score_value=row.get("risk_penalty_score"),
                    tradability_score=row.get("feat_tradability_score"),
                )
                reason_payload = self._build_historical_reason_payload(
                    row,
                    sequence_no=sequence_no,
                    signal_as_of_date=signal_as_of_date,
                    entry_effective_date=entry_effective_date,
                    source_feature_date=feature_date,
                    market_inputs=market_inputs,
                )
                parameter_payload = self._build_historical_parameter_payload(
                    config=config,
                    market_regime=market_regime,
                    source_feature_date=feature_date,
                )
                preview_rows.append(
                    {
                        "preview_signal_id": f"{config.strategy_code}:{signal_as_of_date}:{sequence_no:04d}:{rank:05d}:{row.get('instrument_code') or row.get('instrument_id')}",
                        "signal_write_mode": HISTORICAL_PREVIEW_WRITE_MODE,
                        "strategy_code": config.strategy_code,
                        "strategy_stage": HISTORICAL_PREVIEW_STAGE,
                        "source_stage": "M4_S2_RULE_VALIDATION_SCORING_RULES_REUSED",
                        "source_design_stage": STAGE,
                        "sequence_no": sequence_no,
                        "source_feature_date": feature_date,
                        "feature_date_lag_days": feature_lag_days,
                        "run_id": "",
                        "strategy_version_id": "",
                        "strategy_version_code": config.strategy_version_code,
                        "as_of_date": signal_as_of_date,
                        "effective_date": entry_effective_date,
                        "subject_type": DEFAULT_SUBJECT_TYPE,
                        "subject_key": row.get("instrument_code") or row.get("instrument_id"),
                        "instrument_id": row.get("instrument_id"),
                        "signal_role": DEFAULT_SIGNAL_ROLE,
                        "signal_side": DEFAULT_SIGNAL_SIDE,
                        "signal_action": DEFAULT_SIGNAL_ACTION,
                        "raw_score": row.get("selection_score") or raw_score,
                        "normalized_score": normalized_score,
                        "confidence_score": confidence,
                        "rank_in_batch": rank,
                        "universe_size": universe_size,
                        "reason_code": row.get("reason_code"),
                        "reason_payload_json": json.dumps(reason_payload, ensure_ascii=False, default=json_default, sort_keys=True),
                        "parameter_payload_json": json.dumps(parameter_payload, ensure_ascii=False, default=json_default, sort_keys=True),
                        "instrument_code": row.get("instrument_code"),
                        "display_name": row.get("display_name"),
                        "industry_tag_code": row.get("industry_tag_code"),
                        "industry_tag_name": row.get("industry_tag_name"),
                        "market_regime": market_regime,
                        "raw_market_regime": row.get("raw_market_regime"),
                        "confirmed_market_regime": row.get("confirmed_market_regime"),
                        "market_regime_display": row.get("market_regime_display"),
                        "route_name": row.get("route_name"),
                        "candidate_strategy_code": row.get("candidate_strategy_code"),
                        "candidate_strategy_name": row.get("candidate_strategy_name"),
                        "candidate_strategy_bucket": row.get("candidate_strategy_bucket"),
                        "candidate_strategy_score": row.get("candidate_strategy_score"),
                        "candidate_strategy_rank_in_batch": row.get("candidate_strategy_rank_in_batch"),
                        "candidate_strategy_reason": row.get("candidate_strategy_reason"),
                        "regime_confidence": row.get("regime_confidence"),
                        "regime_days_in_state": row.get("regime_days_in_state"),
                        "regime_transition_flag": row.get("regime_transition_flag"),
                        "regime_reason_code": row.get("regime_reason_code"),
                        "regime_reason_summary": row.get("regime_reason_summary"),
                        "reason_summary": row.get("reason_summary"),
                        "stock_alpha_score": row.get("stock_alpha_score"),
                        "risk_penalty_score": row.get("risk_penalty_score"),
                        "feat_industry_strength_20": row.get("feat_industry_strength_20"),
                        "feat_mom_20": row.get("feat_mom_20"),
                        "feat_trend_strength_20": row.get("feat_trend_strength_20"),
                        "feat_volatility_rank_20": row.get("feat_volatility_rank_20"),
                        "feat_tradability_score": row.get("feat_tradability_score"),
                        "feat_tradable_flag": row.get("feat_tradable_flag"),
                        "preview_scoring_mode": config.preview_scoring_mode,
                        "base_final_preview_score": row.get("final_preview_score"),
                        "base_normalized_score_for_v1_1": row.get("base_normalized_score_for_v1_1"),
                        "selection_score": row.get("selection_score"),
                        "selection_score_source": row.get("selection_score_source"),
                        "pct_change": row.get("pct_change"),
                        "amount": row.get("amount"),
                        "volume": row.get("volume"),
                        "turnover_rate": row.get("turnover_rate"),
                        "amount_pct_rank": row.get("amount_pct_rank"),
                        "volume_pct_rank": row.get("volume_pct_rank"),
                        "turnover_rate_pct_rank": row.get("turnover_rate_pct_rank"),
                        "capital_activity_score": row.get("capital_activity_score"),
                        "capital_activity_status": row.get("capital_activity_status"),
                        "concept_count": row.get("concept_count"),
                        "concept_names": row.get("concept_names"),
                        "concept_score": row.get("concept_score"),
                        "concept_status": row.get("concept_status"),
                        "concept_top_drivers_json": row.get("concept_top_drivers_json"),
                        "cleaned_concept_count": row.get("cleaned_concept_count"),
                        "cleaned_concept_names": row.get("cleaned_concept_names"),
                        "cleaned_concept_score": row.get("cleaned_concept_score"),
                        "cleaned_concept_status": row.get("cleaned_concept_status"),
                        "cleaned_concept_top_drivers_json": row.get("cleaned_concept_top_drivers_json"),
                        "true_theme_count": row.get("true_theme_count"),
                        "true_theme_names": row.get("true_theme_names"),
                        "true_theme_score": row.get("true_theme_score"),
                        "true_theme_top_drivers_json": row.get("true_theme_top_drivers_json"),
                        "style_tag_count": row.get("style_tag_count"),
                        "style_tag_names": row.get("style_tag_names"),
                        "state_event_tag_count": row.get("state_event_tag_count"),
                        "state_event_tag_names": row.get("state_event_tag_names"),
                        "index_channel_tag_count": row.get("index_channel_tag_count"),
                        "index_channel_tag_names": row.get("index_channel_tag_names"),
                        "holding_structure_tag_count": row.get("holding_structure_tag_count"),
                        "holding_structure_tag_names": row.get("holding_structure_tag_names"),
                        "policy_attribute_tag_count": row.get("policy_attribute_tag_count"),
                        "policy_attribute_tag_names": row.get("policy_attribute_tag_names"),
                        "other_tag_count": row.get("other_tag_count"),
                        "other_tag_names": row.get("other_tag_names"),
                        "filtered_generic_concept_count": row.get("filtered_generic_concept_count"),
                        "filtered_generic_concept_names": row.get("filtered_generic_concept_names"),
                        "concept_cleaning_status": row.get("concept_cleaning_status"),
                        "tag_classification_status": row.get("tag_classification_status"),
                        "sw_l2_names": row.get("sw_l2_names"),
                        "sw_l3_names": row.get("sw_l3_names"),
                        "v1_1_preview_score": row.get("v1_1_preview_score"),
                        "v1_1_score_delta": row.get("v1_1_score_delta"),
                        "cleaned_v1_1_preview_score": row.get("cleaned_v1_1_preview_score"),
                        "cleaned_v1_1_score_delta": row.get("cleaned_v1_1_score_delta"),
                        "v1_1_scoring_mode": row.get("v1_1_scoring_mode"),
                    }
                )

            batch_status = "PASS"
            details = [
                f"feature_date={feature_date}",
                f"raw_market_regime={raw_market_regime}",
                f"confirmed_market_regime={market_regime}",
                f"preview_scoring_mode={config.preview_scoring_mode}",
                f"transition={confirmed_regime_state.get('regime_transition_flag')}",
                f"days_in_state={confirmed_regime_state.get('regime_days_in_state')}",
            ]
            if feature_lag_days != 0:
                batch_status = "WARN"
                details.append(f"feature_date_lag_days={feature_lag_days}; using latest ready feature date <= signal_as_of_date")
            if market_regime == "UNKNOWN":
                batch_status = "WARN"
                details.append("market_regime=UNKNOWN")
            if required_fail_count > 0:
                batch_status = "FAIL"
                details.append(f"required_feature_fail_count={required_fail_count}")
            if len(preview_rows) < config.min_preview_rows_per_batch:
                batch_status = "FAIL"
                details.append(f"preview rows {len(preview_rows)} below min_preview_rows_per_batch={config.min_preview_rows_per_batch}")

            return {
                "batch_summary": self._batch_summary_row(
                    sequence_no=sequence_no,
                    signal_as_of_date=signal_as_of_date,
                    entry_effective_date=entry_effective_date,
                    source_feature_date=feature_date,
                    feature_date_lag_days=feature_lag_days,
                    market_regime=market_regime,
                    raw_market_regime=raw_market_regime,
                    confirmed_market_regime=market_regime,
                    market_regime_display=market_regime_display_label(market_regime),
                    route_name=route_name_for_regime(market_regime),
                    candidate_strategy_code=candidate_strategy_config_for_regime_local(market_regime).get("candidate_strategy_code"),
                    candidate_strategy_name=candidate_strategy_config_for_regime_local(market_regime).get("candidate_strategy_name"),
                    candidate_strategy_bucket=candidate_strategy_config_for_regime_local(market_regime).get("candidate_strategy_bucket"),
                    regime_confidence=confirmed_regime_state.get("regime_confidence"),
                    regime_days_in_state=confirmed_regime_state.get("regime_days_in_state"),
                    regime_transition_flag=confirmed_regime_state.get("regime_transition_flag"),
                    regime_reason_code=confirmed_regime_state.get("regime_reason_code"),
                    score_input_row_count=len(score_input_rows),
                    eligible_candidate_count=len(eligible_rows),
                    preview_signal_row_count=len(preview_rows),
                    expected_signal_rows=config.target_top_n,
                    preview_scoring_mode=config.preview_scoring_mode,
                    cleaned_v1_1_score_count=sum(1 for row in preview_rows if self._to_decimal(row.get("cleaned_v1_1_preview_score")) is not None),
                    true_theme_score_count=sum(1 for row in preview_rows if self._to_decimal(row.get("true_theme_score")) is not None),
                    capital_activity_score_count=sum(1 for row in preview_rows if self._to_decimal(row.get("capital_activity_score")) is not None),
                    required_feature_pass_count=required_pass_count,
                    required_feature_warn_count=required_warn_count,
                    required_feature_fail_count=required_fail_count,
                    status=batch_status,
                    detail="; ".join(details),
                ),
                "feature_coverage": coverage_rows,
                "preview_rows": preview_rows,
            }
        except Exception as exc:
            return {
                "batch_summary": self._batch_summary_row(
                    sequence_no=sequence_no,
                    signal_as_of_date=signal_as_of_date,
                    entry_effective_date=entry_effective_date,
                    status="FAIL",
                    detail=f"Batch scoring failed: {str(exc)[:500]}",
                    expected_signal_rows=config.target_top_n,
                ),
                "feature_coverage": [],
                "preview_rows": [],
            }

    def _resolve_feature_date(self, conn: Any, *, requested_date: date, feature_set_code: str, feature_set_version: str) -> date | None:
        row = conn.execute(
            text(
                """
                select max(trade_date) as trade_date
                from analytics_feature_snapshot
                where trade_date <= :requested_date
                  and feature_set_code = :feature_set_code
                  and feature_set_version = :feature_set_version
                  and sample_status = 'ready'
                """
            ),
            {"requested_date": requested_date, "feature_set_code": feature_set_code, "feature_set_version": feature_set_version},
        ).mappings().first()
        return row["trade_date"] if row and row.get("trade_date") else None

    def _load_historical_market_inputs(self, conn: Any, *, trade_date: date, benchmark_index_code: str, lookback_days: int) -> dict[str, Any]:
        from stock_quant_v2.strategy_domain.services.regime_sector_industry_rule_validation_service import quantize, safe_ratio, to_decimal

        breadth = conn.execute(
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

        index_rows = conn.execute(
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

    def _load_historical_feature_coverage(
        self,
        conn: Any,
        *,
        sequence_no: int,
        signal_as_of_date: date,
        feature_date: date,
        feature_set_code: str,
        feature_set_version: str,
        industry_tag_type: str,
        all_feature_codes: Sequence[str],
        required_feature_codes: set[str],
        feature_quality_status: Callable[..., tuple[str, str | None]],
    ) -> list[dict[str, Any]]:
        feature_rows = conn.execute(
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
                where trade_date = :feature_date
                  and feature_set_code = :feature_set_code
                  and feature_set_version = :feature_set_version
                  and feature_code = any(:feature_codes)
                group by feature_code
                """
            ),
            {
                "feature_date": feature_date,
                "feature_set_code": feature_set_code,
                "feature_set_version": feature_set_version,
                "feature_codes": list(all_feature_codes),
            },
        ).mappings().all()
        rows_by_code = {row["feature_code"]: dict(row) for row in feature_rows}

        coverage: list[dict[str, Any]] = []
        for code in all_feature_codes:
            row = rows_by_code.get(code, {})
            ready_rows = int(row.get("ready_rows") or 0)
            required = code in required_feature_codes
            status, quality_issue = feature_quality_status(
                feature_code=code,
                required=required,
                ready_rows=ready_rows,
                min_value=row.get("min_value"),
                max_value=row.get("max_value"),
            )
            coverage.append(
                {
                    "sequence_no": sequence_no,
                    "signal_as_of_date": signal_as_of_date,
                    "source_feature_date": feature_date,
                    "feature_code": code,
                    "required": required,
                    "row_count": int(row.get("row_count") or 0),
                    "ready_rows": ready_rows,
                    "ready_instrument_count": int(row.get("ready_instrument_count") or 0),
                    "min_value": row.get("min_value"),
                    "max_value": row.get("max_value"),
                    "avg_value": row.get("avg_value"),
                    "status": status,
                    "quality_issue": quality_issue,
                }
            )
        industry_row = conn.execute(
            text(
                """
                select count(distinct t.id) as industry_count,
                       count(distinct it.instrument_id) as instrument_count
                from instrument_tag it
                join tag t on t.id = it.tag_id
                where t.tag_type = :industry_tag_type
                  and it.effective_from <= :feature_date
                  and (it.effective_to is null or it.effective_to >= :feature_date)
                """
            ),
            {"industry_tag_type": industry_tag_type, "feature_date": feature_date},
        ).mappings().first()
        industry_count = int(industry_row.get("industry_count") or 0) if industry_row else 0
        coverage.append(
            {
                "sequence_no": sequence_no,
                "signal_as_of_date": signal_as_of_date,
                "source_feature_date": feature_date,
                "feature_code": f"industry_mapping:{industry_tag_type}",
                "required": True,
                "row_count": int(industry_row.get("instrument_count") or 0) if industry_row else 0,
                "ready_rows": int(industry_row.get("instrument_count") or 0) if industry_row else 0,
                "ready_instrument_count": int(industry_row.get("instrument_count") or 0) if industry_row else 0,
                "min_value": None,
                "max_value": None,
                "avg_value": None,
                "status": "PASS" if industry_count >= 5 else "FAIL",
                "quality_issue": None if industry_count >= 5 else "too_few_industries",
            }
        )
        return coverage

    def _load_historical_score_input_rows(
        self,
        conn: Any,
        *,
        trade_date: date,
        feature_set_code: str,
        feature_set_version: str,
        industry_tag_type: str,
        all_feature_codes: Sequence[str],
    ) -> list[dict[str, Any]]:
        rows = conn.execute(
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
                "feature_codes": list(all_feature_codes),
                "industry_tag_type": industry_tag_type,
            },
        ).mappings().all()
        return [dict(row) for row in rows]

    def _load_historical_tag_enrichment(self, conn: Any, *, as_of_date: date, instrument_ids: Sequence[int]) -> list[dict[str, Any]]:
        """Load concept/industry enrichment for one historical batch.

        Stage 6.19B-1D-fix1 keeps this research-only and artifact-only, but
        avoids the earlier heavy whole-market concept scan.  We still compute
        capital percent-ranks from the daily universe for the date, while
        concept strength is estimated only from tags attached to the current
        score input instruments.  This is sufficient for cleaned v1.1 M5 input
        validation and prevents one historical batch from blocking on a large
        CONCEPT_EM full-universe aggregation.
        """
        ids = sorted({int(value) for value in instrument_ids if value is not None})
        if not ids:
            return []

        sql = """
with universe as (
  select
    b.instrument_id,
    b.pct_change,
    b.amount,
    b.volume,
    b.turnover_rate
  from public.core_daily_bar b
  where b.price_adjust_type = 'RAW'
    and b.trade_date = :as_of_date
),
amount_rank as (
  select instrument_id, percent_rank() over (order by amount) as amount_pct_rank
  from universe
  where amount is not null
),
volume_rank as (
  select instrument_id, percent_rank() over (order by volume) as volume_pct_rank
  from universe
  where volume is not null
),
turnover_rank as (
  select instrument_id, percent_rank() over (order by turnover_rate) as turnover_rate_pct_rank
  from universe
  where turnover_rate is not null
),
capital as (
  select
    u.instrument_id,
    u.pct_change,
    u.amount,
    u.volume,
    u.turnover_rate,
    ar.amount_pct_rank,
    vr.volume_pct_rank,
    tr.turnover_rate_pct_rank,
    case
      when ar.amount_pct_rank is null or vr.volume_pct_rank is null or tr.turnover_rate_pct_rank is null then null
      else ((ar.amount_pct_rank + vr.volume_pct_rank + tr.turnover_rate_pct_rank) / 3.0)
    end as capital_activity_score
  from universe u
  left join amount_rank ar on ar.instrument_id = u.instrument_id
  left join volume_rank vr on vr.instrument_id = u.instrument_id
  left join turnover_rank tr on tr.instrument_id = u.instrument_id
),
target_edges as (
  select
    it.instrument_id,
    t.id as tag_id,
    t.tag_type,
    t.taxonomy_source,
    t.tag_name
  from public.instrument_tag it
  join public.tag t on t.id = it.tag_id
  where it.instrument_id in :instrument_ids
    and it.effective_from <= :as_of_date
    and (it.effective_to is null or it.effective_to >= :as_of_date)
    and (
      (t.tag_type = :concept_tag_type and t.taxonomy_source = :concept_taxonomy_source)
      or (t.tag_type in ('SW_INDUSTRY_L2', 'SW_INDUSTRY_L3') and t.taxonomy_source = :industry_taxonomy_source)
    )
),
concept_edges as (
  select *
  from target_edges
  where tag_type = :concept_tag_type
    and taxonomy_source = :concept_taxonomy_source
),
concept_stats_raw as (
  select
    ce.tag_id,
    ce.tag_name,
    count(distinct ce.instrument_id) as concept_stock_count,
    avg(c.capital_activity_score) as concept_avg_capital_activity_score,
    avg(c.pct_change) as concept_avg_pct_change,
    avg(case when c.pct_change > 0 then 1.0 when c.pct_change is not null then 0.0 else null end) as concept_positive_ratio
  from concept_edges ce
  left join capital c on c.instrument_id = ce.instrument_id
  group by ce.tag_id, ce.tag_name
),
concept_stats_ranked as (
  select
    csr.*,
    percent_rank() over (order by csr.concept_avg_pct_change) as concept_pct_change_rank,
    percent_rank() over (order by csr.concept_stock_count) as concept_coverage_rank
  from concept_stats_raw csr
),
concept_stats as (
  select
    csr.*,
    case
      when csr.concept_avg_capital_activity_score is null
        or csr.concept_positive_ratio is null
        or csr.concept_avg_pct_change is null
      then null
      else (
        0.40 * coalesce(csr.concept_avg_capital_activity_score, 0)
        + 0.30 * coalesce(csr.concept_positive_ratio, 0)
        + 0.20 * coalesce(csr.concept_pct_change_rank, 0)
        + 0.10 * coalesce(csr.concept_coverage_rank, 0)
      )
    end as concept_hot_score
  from concept_stats_ranked csr
),
target_tags as (
  select
    te.instrument_id,
    te.tag_type,
    te.taxonomy_source,
    te.tag_name,
    c.pct_change,
    c.amount,
    c.volume,
    c.turnover_rate,
    c.amount_pct_rank,
    c.volume_pct_rank,
    c.turnover_rate_pct_rank,
    c.capital_activity_score,
    cs.concept_stock_count,
    cs.concept_avg_capital_activity_score,
    cs.concept_avg_pct_change,
    cs.concept_positive_ratio,
    cs.concept_hot_score
  from target_edges te
  left join capital c on c.instrument_id = te.instrument_id
  left join concept_stats cs on cs.tag_id = te.tag_id
)
select *
from target_tags
order by instrument_id, tag_type, concept_hot_score desc nulls last, tag_name
"""
        statement = text(sql).bindparams(bindparam("instrument_ids", expanding=True))
        result = conn.execute(
            statement,
            {
                "as_of_date": as_of_date,
                "instrument_ids": ids,
                "concept_tag_type": CONCEPT_TAG_TYPE,
                "concept_taxonomy_source": CONCEPT_TAXONOMY_SOURCE,
                "industry_taxonomy_source": INDUSTRY_TAXONOMY_SOURCE,
            },
        )
        return [dict(row._mapping) for row in result]

    def _aggregate_historical_tag_enrichment(self, rows: Sequence[Mapping[str, Any]]) -> dict[int, dict[str, Any]]:
        grouped: dict[int, dict[str, Any]] = {}
        for row in rows:
            instrument_id = safe_int(row.get("instrument_id"))
            if instrument_id is None:
                continue
            item = grouped.setdefault(instrument_id, {"concepts": [], "sw_l2": [], "sw_l3": [], "market": {}})
            item["market"] = {
                "pct_change": row.get("pct_change"),
                "amount": row.get("amount"),
                "volume": row.get("volume"),
                "turnover_rate": row.get("turnover_rate"),
                "amount_pct_rank": row.get("amount_pct_rank"),
                "volume_pct_rank": row.get("volume_pct_rank"),
                "turnover_rate_pct_rank": row.get("turnover_rate_pct_rank"),
                "capital_activity_score": row.get("capital_activity_score"),
            }
            tag_type = str(row.get("tag_type") or "")
            tag_name = str(row.get("tag_name") or "").strip()
            if not tag_name:
                continue
            if tag_type == CONCEPT_TAG_TYPE:
                item["concepts"].append(
                    {
                        "concept_name": tag_name,
                        "concept_hot_score": safe_float(row.get("concept_hot_score")),
                        "stock_count": safe_int(row.get("concept_stock_count")),
                        "avg_capital_activity_score": safe_float(row.get("concept_avg_capital_activity_score")),
                        "avg_pct_change": safe_float(row.get("concept_avg_pct_change")),
                        "positive_ratio": safe_float(row.get("concept_positive_ratio")),
                    }
                )
            elif tag_type == "SW_INDUSTRY_L2" and tag_name not in item["sw_l2"]:
                item["sw_l2"].append(tag_name)
            elif tag_type == "SW_INDUSTRY_L3" and tag_name not in item["sw_l3"]:
                item["sw_l3"].append(tag_name)
        return grouped

    def _apply_empty_historical_v1_1_fields(self, row: dict[str, Any]) -> None:
        for key in (
            "pct_change", "amount", "volume", "turnover_rate",
            "amount_pct_rank", "volume_pct_rank", "turnover_rate_pct_rank",
            "capital_activity_score", "capital_activity_status",
            "concept_count", "concept_names", "concept_score", "concept_status", "concept_top_drivers_json",
            "cleaned_concept_count", "cleaned_concept_names", "cleaned_concept_score", "cleaned_concept_status", "cleaned_concept_top_drivers_json",
            "true_theme_count", "true_theme_names", "true_theme_score", "true_theme_top_drivers_json",
            "style_tag_count", "style_tag_names", "state_event_tag_count", "state_event_tag_names",
            "index_channel_tag_count", "index_channel_tag_names", "holding_structure_tag_count", "holding_structure_tag_names",
            "policy_attribute_tag_count", "policy_attribute_tag_names", "other_tag_count", "other_tag_names",
            "filtered_generic_concept_count", "filtered_generic_concept_names",
            "concept_cleaning_status", "tag_classification_status",
            "sw_l2_names", "sw_l3_names",
            "v1_1_preview_score", "v1_1_score_delta", "cleaned_v1_1_preview_score", "cleaned_v1_1_score_delta",
            "base_normalized_score_for_v1_1",
        ):
            row.setdefault(key, None)
        row["v1_1_scoring_mode"] = HISTORICAL_PREVIEW_SCORING_MODE_BASE

    def _apply_historical_tag_enrichment(self, row: dict[str, Any], tags: Mapping[str, Any]) -> None:
        market = dict(tags.get("market") or {})
        for key in (
            "pct_change",
            "amount",
            "volume",
            "turnover_rate",
            "amount_pct_rank",
            "volume_pct_rank",
            "turnover_rate_pct_rank",
            "capital_activity_score",
        ):
            value = market.get(key)
            row[key] = self._quantize(self._to_decimal(value)) if self._to_decimal(value) is not None else value
        row["capital_activity_status"] = "READY_FOR_M4_SCORING_PREVIEW" if row.get("capital_activity_score") is not None else "MISSING_OR_NOT_TRADABLE"

        concepts = list(tags.get("concepts") or [])
        concepts.sort(key=lambda item: (item.get("concept_hot_score") is None, -(item.get("concept_hot_score") or 0), item.get("concept_name") or ""))

        concept_groups: dict[str, list[dict[str, Any]]] = {
            CONCEPT_TAG_CLASS_TRUE_THEME: [],
            CONCEPT_TAG_CLASS_STYLE: [],
            CONCEPT_TAG_CLASS_STATE_EVENT: [],
            CONCEPT_TAG_CLASS_INDEX_CHANNEL: [],
            CONCEPT_TAG_CLASS_HOLDING_STRUCTURE: [],
            CONCEPT_TAG_CLASS_POLICY_ATTRIBUTE: [],
            CONCEPT_TAG_CLASS_GENERIC_OTHER: [],
        }
        for concept in concepts:
            concept_name = str(concept.get("concept_name") or "").strip()
            concept_class = self._classify_historical_concept_tag(concept_name)
            enriched_concept = dict(concept)
            enriched_concept["tag_class"] = concept_class
            concept_groups.setdefault(concept_class, []).append(enriched_concept)

        true_theme_concepts = concept_groups.get(CONCEPT_TAG_CLASS_TRUE_THEME, [])
        filtered_generic_concepts = [
            item
            for class_name in NON_THEME_CONCEPT_TAG_CLASSES
            for item in concept_groups.get(class_name, [])
        ]

        top_concepts = concepts[:5]
        true_theme_top_concepts = true_theme_concepts[:5]
        scores = [self._to_decimal(item.get("concept_hot_score")) for item in top_concepts]
        scores = [score for score in scores if score is not None]
        true_theme_scores = [self._to_decimal(item.get("concept_hot_score")) for item in true_theme_top_concepts]
        true_theme_scores = [score for score in true_theme_scores if score is not None]

        row["concept_count"] = len(concepts)
        row["concept_names"] = ",".join(item.get("concept_name") or "" for item in concepts[:20])
        row["concept_top_drivers_json"] = json.dumps(top_concepts, ensure_ascii=False, default=json_default)
        row["concept_score"] = self._quantize(sum(scores) / Decimal(len(scores))) if scores else None
        row["concept_status"] = "READY_FOR_M4_SCORING_PREVIEW" if scores else "NO_CONCEPT_SCORE"

        true_theme_score = self._quantize(sum(true_theme_scores) / Decimal(len(true_theme_scores))) if true_theme_scores else None
        row["true_theme_count"] = len(true_theme_concepts)
        row["true_theme_names"] = ",".join(item.get("concept_name") or "" for item in true_theme_concepts[:20])
        row["true_theme_top_drivers_json"] = json.dumps(true_theme_top_concepts, ensure_ascii=False, default=json_default)
        if true_theme_score is not None:
            row["true_theme_score"] = true_theme_score
            row["cleaned_concept_score"] = true_theme_score
            row["true_theme_status"] = "READY_FOR_M4_TRUE_THEME_SCORING_PREVIEW"
            row["cleaned_concept_status"] = "READY_FOR_M4_CLEANED_SCORING_PREVIEW"
        elif concepts:
            row["true_theme_score"] = Decimal("0")
            row["cleaned_concept_score"] = Decimal("0")
            row["true_theme_status"] = "NON_THEME_ONLY_ZERO_THEME_SCORE"
            row["cleaned_concept_status"] = "GENERIC_ONLY_ZERO_THEME_SCORE"
        else:
            row["true_theme_score"] = Decimal("0")
            row["cleaned_concept_score"] = Decimal("0")
            row["true_theme_status"] = "NO_CONCEPT_TAGS_ZERO_THEME_SCORE"
            row["cleaned_concept_status"] = "NO_CONCEPT_TAGS_ZERO_THEME_SCORE"

        row["cleaned_concept_count"] = len(true_theme_concepts)
        row["cleaned_concept_names"] = row["true_theme_names"]
        row["cleaned_concept_top_drivers_json"] = row["true_theme_top_drivers_json"]

        def names(class_name: str, limit: int = 20) -> str:
            return ",".join(item.get("concept_name") or "" for item in concept_groups.get(class_name, [])[:limit])

        row["style_tag_count"] = len(concept_groups.get(CONCEPT_TAG_CLASS_STYLE, []))
        row["style_tag_names"] = names(CONCEPT_TAG_CLASS_STYLE)
        row["state_event_tag_count"] = len(concept_groups.get(CONCEPT_TAG_CLASS_STATE_EVENT, []))
        row["state_event_tag_names"] = names(CONCEPT_TAG_CLASS_STATE_EVENT)
        row["index_channel_tag_count"] = len(concept_groups.get(CONCEPT_TAG_CLASS_INDEX_CHANNEL, []))
        row["index_channel_tag_names"] = names(CONCEPT_TAG_CLASS_INDEX_CHANNEL)
        row["holding_structure_tag_count"] = len(concept_groups.get(CONCEPT_TAG_CLASS_HOLDING_STRUCTURE, []))
        row["holding_structure_tag_names"] = names(CONCEPT_TAG_CLASS_HOLDING_STRUCTURE)
        row["policy_attribute_tag_count"] = len(concept_groups.get(CONCEPT_TAG_CLASS_POLICY_ATTRIBUTE, []))
        row["policy_attribute_tag_names"] = names(CONCEPT_TAG_CLASS_POLICY_ATTRIBUTE)
        row["other_tag_count"] = len(concept_groups.get(CONCEPT_TAG_CLASS_GENERIC_OTHER, []))
        row["other_tag_names"] = names(CONCEPT_TAG_CLASS_GENERIC_OTHER)
        row["filtered_generic_concept_count"] = len(filtered_generic_concepts)
        row["filtered_generic_concept_names"] = ",".join(item.get("concept_name") or "" for item in filtered_generic_concepts[:20])
        row["concept_cleaning_status"] = (
            "FILTERED_GENERIC_TAGS"
            if filtered_generic_concepts
            else "NO_GENERIC_TAGS_FILTERED"
            if concepts
            else "NO_CONCEPT_TAGS"
        )
        row["tag_classification_status"] = "L0_L9_CLASSIFIED" if concepts else "NO_CONCEPT_TAGS"
        row["sw_l2_names"] = ",".join(tags.get("sw_l2") or [])
        row["sw_l3_names"] = ",".join(tags.get("sw_l3") or [])

    def _apply_historical_selection_scores(self, rows: list[dict[str, Any]], *, preview_scoring_mode: str) -> None:
        base_scores = [self._to_decimal(row.get("final_preview_score")) for row in rows]
        base_scores = [score for score in base_scores if score is not None]
        min_base = min(base_scores) if base_scores else Decimal("0")
        max_base = max(base_scores) if base_scores else Decimal("0")

        for row in rows:
            base_raw = self._to_decimal(row.get("final_preview_score"))
            base_normalized = self._min_max_normalize(base_raw, min_value=min_base, max_value=max_base) if base_raw is not None else None
            row["base_normalized_score_for_v1_1"] = base_normalized

            concept_score = self._to_decimal(row.get("concept_score"))
            cleaned_concept_score = self._to_decimal(row.get("cleaned_concept_score"))
            capital_score = self._to_decimal(row.get("capital_activity_score"))
            if capital_score is None:
                capital_score = Decimal("0")
                row["capital_activity_score"] = Decimal("0")
                row["capital_activity_status"] = "NO_CAPITAL_ACTIVITY_ZERO_SCORE"
            observation_penalty = self._historical_observation_penalty(row)

            if base_normalized is not None and concept_score is not None and capital_score is not None:
                v1_1_score = self._clamp_score(
                    Decimal("0.70") * base_normalized
                    + Decimal("0.15") * concept_score
                    + Decimal("0.15") * capital_score
                    - observation_penalty
                )
                row["v1_1_preview_score"] = v1_1_score
                row["v1_1_score_delta"] = self._quantize(v1_1_score - base_normalized) if v1_1_score is not None else None
            if base_normalized is not None and cleaned_concept_score is not None and capital_score is not None:
                cleaned_score = self._clamp_score(
                    Decimal("0.70") * base_normalized
                    + Decimal("0.15") * cleaned_concept_score
                    + Decimal("0.15") * capital_score
                    - observation_penalty
                )
                row["cleaned_v1_1_preview_score"] = cleaned_score
                row["cleaned_v1_1_score_delta"] = self._quantize(cleaned_score - base_normalized) if cleaned_score is not None else None

            row["v1_1_scoring_mode"] = preview_scoring_mode
            if preview_scoring_mode == HISTORICAL_PREVIEW_SCORING_MODE_CLEANED_V1_1:
                row["selection_score"] = row.get("cleaned_v1_1_preview_score") if row.get("cleaned_v1_1_preview_score") is not None else row.get("final_preview_score")
                row["selection_score_source"] = "cleaned_v1_1_preview_score" if row.get("cleaned_v1_1_preview_score") is not None else "final_preview_score_fallback"
            else:
                row["selection_score"] = row.get("final_preview_score")
                row["selection_score_source"] = "final_preview_score"

    def _historical_observation_penalty(self, row: Mapping[str, Any]) -> Decimal:
        penalty = Decimal("0")
        display_name = str(row.get("display_name") or "")
        concept_names = str(row.get("concept_names") or "")
        if "ST" in display_name.upper() or "ST股" in concept_names:
            penalty += Decimal("0.35")
        if row.get("capital_activity_score") is None:
            penalty += Decimal("0.10")
        pct_change = self._to_decimal(row.get("pct_change"))
        if pct_change is not None and (pct_change >= Decimal("20") or pct_change <= Decimal("-20")):
            penalty += Decimal("0.05")
        return penalty

    def _classify_historical_concept_tag(self, tag_name: str) -> str:
        name = str(tag_name or "").strip()
        if not name:
            return CONCEPT_TAG_CLASS_GENERIC_OTHER
        if name in INDEX_CHANNEL_TAG_NAMES or any(keyword in name for keyword in INDEX_CHANNEL_KEYWORDS):
            return CONCEPT_TAG_CLASS_INDEX_CHANNEL
        if name in STYLE_TAG_NAMES or any(keyword in name for keyword in STYLE_TAG_KEYWORDS):
            return CONCEPT_TAG_CLASS_STYLE
        if name in STATE_EVENT_TAG_NAMES or any(keyword in name for keyword in STATE_EVENT_KEYWORDS):
            return CONCEPT_TAG_CLASS_STATE_EVENT
        if name in HOLDING_STRUCTURE_TAG_NAMES or any(keyword in name for keyword in HOLDING_STRUCTURE_KEYWORDS):
            return CONCEPT_TAG_CLASS_HOLDING_STRUCTURE
        if name in POLICY_ATTRIBUTE_TAG_NAMES or any(keyword in name for keyword in POLICY_ATTRIBUTE_KEYWORDS):
            return CONCEPT_TAG_CLASS_POLICY_ATTRIBUTE
        if name in GENERIC_CONCEPT_TAG_NAMES or any(keyword in name for keyword in GENERIC_CONCEPT_KEYWORDS):
            return CONCEPT_TAG_CLASS_GENERIC_OTHER
        return CONCEPT_TAG_CLASS_TRUE_THEME

    def _clamp_score(self, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        if value < Decimal("0"):
            return Decimal("0")
        if value > Decimal("1"):
            return Decimal("1")
        return self._quantize(value)

    def _historical_confidence_score(self, *, normalized_score: Any, risk_penalty_score_value: Any, tradability_score: Any) -> Decimal | None:
        normalized = self._clamp_0_1(normalized_score)
        risk = self._clamp_0_1(risk_penalty_score_value, default=Decimal("0.5"))
        tradability = self._clamp_0_1(tradability_score, default=Decimal("0.5"))
        if normalized is None:
            return None
        return self._quantize(Decimal("0.50") * normalized + Decimal("0.30") * tradability + Decimal("0.20") * (Decimal("1") - risk))

    def _min_max_normalize(self, value: Any, *, min_value: Decimal, max_value: Decimal) -> Decimal | None:
        decimal_value = self._to_decimal(value)
        if decimal_value is None:
            return None
        if max_value == min_value:
            return Decimal("1")
        return self._quantize((decimal_value - min_value) / (max_value - min_value))

    def _candidate_strategy_context(
        self,
        row: Mapping[str, Any],
        *,
        market_regime: str,
        alpha_score: Any,
        risk_penalty_score_value: Any,
        base_score: Any,
    ) -> dict[str, Any]:
        config = dict(candidate_strategy_config_for_regime_local(market_regime))
        score = self._candidate_strategy_score(
            row,
            market_regime=market_regime,
            alpha_score=alpha_score,
            risk_penalty_score_value=risk_penalty_score_value,
            base_score=base_score,
        )
        formula_ref = self._candidate_strategy_score_formula_ref(market_regime)
        return {
            **config,
            "candidate_strategy_score": score,
            "candidate_strategy_score_formula_ref": formula_ref,
        }

    def _candidate_strategy_score(
        self,
        row: Mapping[str, Any],
        *,
        market_regime: str,
        alpha_score: Any,
        risk_penalty_score_value: Any,
        base_score: Any,
    ) -> Decimal | None:
        industry = self._clamp_0_1(row.get("feat_industry_strength_20"))
        momentum = self._clamp_0_1(row.get("feat_mom_20"))
        trend = self._clamp_0_1(row.get("feat_trend_strength_20"))
        volatility = self._clamp_0_1(row.get("feat_volatility_rank_20"))
        tradability = self._clamp_0_1(row.get("feat_tradability_score"))
        alpha = self._to_decimal(alpha_score)
        risk = self._to_decimal(risk_penalty_score_value)
        fallback = self._to_decimal(base_score)

        if any(value is None for value in (industry, momentum, trend, volatility, tradability, alpha, risk)):
            return self._quantize(fallback)

        low_volatility = Decimal("1") - volatility
        regime = str(market_regime or "UNKNOWN")

        if regime == "RISK_ON":
            return self._quantize(
                Decimal("0.30") * momentum
                + Decimal("0.30") * trend
                + Decimal("0.20") * industry
                + Decimal("0.15") * tradability
                - Decimal("0.05") * risk
            )

        if regime == "RISK_OFF":
            return self._quantize(
                Decimal("0.30") * low_volatility
                + Decimal("0.25") * tradability
                + Decimal("0.25") * industry
                + Decimal("0.10") * trend
                + Decimal("0.10") * momentum
                - Decimal("0.10") * risk
            )

        return self._quantize(
            Decimal("0.25") * industry
            + Decimal("0.25") * low_volatility
            + Decimal("0.20") * tradability
            + Decimal("0.15") * trend
            + Decimal("0.15") * momentum
            - Decimal("0.10") * risk
        )

    def _candidate_strategy_score_formula_ref(self, market_regime: str) -> str:
        regime = str(market_regime or "UNKNOWN")
        if regime == "RISK_ON":
            return "0.30*mom_20 + 0.30*trend_strength_20 + 0.20*industry_strength_20 + 0.15*tradability_score - 0.05*risk_penalty_score"
        if regime == "RISK_OFF":
            return "0.30*(1-volatility_rank_20) + 0.25*tradability_score + 0.25*industry_strength_20 + 0.10*trend_strength_20 + 0.10*mom_20 - 0.10*risk_penalty_score"
        return "0.25*industry_strength_20 + 0.25*(1-volatility_rank_20) + 0.20*tradability_score + 0.15*trend_strength_20 + 0.15*mom_20 - 0.10*risk_penalty_score"

    def _clamp_0_1(self, value: Any, *, default: Decimal | None = None) -> Decimal | None:
        decimal_value = self._to_decimal(value)
        if decimal_value is None:
            return default
        if decimal_value < Decimal("0"):
            return Decimal("0")
        if decimal_value > Decimal("1"):
            return Decimal("1")
        return decimal_value

    def _to_decimal(self, value: Any) -> Decimal | None:
        if value is None:
            return None
        text_value = str(value).strip()
        if not text_value:
            return None
        try:
            return Decimal(text_value)
        except Exception:
            return None

    def _quantize(self, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        return value.quantize(Decimal("0.0000000001"))

    def _build_historical_reason_payload(
        self,
        row: Mapping[str, Any],
        *,
        sequence_no: int,
        signal_as_of_date: date,
        entry_effective_date: date,
        source_feature_date: date,
        market_inputs: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "sequence_no": sequence_no,
            "signal_as_of_date": signal_as_of_date,
            "entry_effective_date": entry_effective_date,
            "source_feature_date": source_feature_date,
            "market_regime": row.get("market_regime"),
            "raw_market_regime": row.get("raw_market_regime"),
            "confirmed_market_regime": row.get("confirmed_market_regime"),
            "market_regime_display": row.get("market_regime_display"),
            "route_name": row.get("route_name"),
            "candidate_strategy_code": row.get("candidate_strategy_code"),
            "candidate_strategy_name": row.get("candidate_strategy_name"),
            "candidate_strategy_bucket": row.get("candidate_strategy_bucket"),
            "candidate_strategy_score": row.get("candidate_strategy_score"),
            "candidate_strategy_rank_in_batch": row.get("candidate_strategy_rank_in_batch"),
            "candidate_strategy_reason": row.get("candidate_strategy_reason"),
            "regime_confidence": row.get("regime_confidence"),
            "regime_days_in_state": row.get("regime_days_in_state"),
            "regime_transition_flag": row.get("regime_transition_flag"),
            "regime_reason_code": row.get("regime_reason_code"),
            "regime_reason_summary": row.get("regime_reason_summary"),
            "reason_code": row.get("reason_code"),
            "reason_summary": row.get("reason_summary"),
            "instrument_code": row.get("instrument_code"),
            "display_name": row.get("display_name"),
            "industry_tag_code": row.get("industry_tag_code"),
            "industry_tag_name": row.get("industry_tag_name"),
            "score_components": {
                "feat_industry_strength_20": row.get("feat_industry_strength_20"),
                "feat_industry_ret_20": row.get("feat_industry_ret_20"),
                "feat_industry_breadth_20": row.get("feat_industry_breadth_20"),
                "feat_mom_20": row.get("feat_mom_20"),
                "feat_trend_strength_20": row.get("feat_trend_strength_20"),
                "feat_volatility_rank_20": row.get("feat_volatility_rank_20"),
                "feat_tradability_score": row.get("feat_tradability_score"),
                "stock_alpha_score": row.get("stock_alpha_score"),
                "risk_penalty_score": row.get("risk_penalty_score"),
                "base_preview_score": row.get("base_preview_score"),
                "candidate_strategy_score": row.get("candidate_strategy_score"),
                "final_preview_score": row.get("final_preview_score"),
                "base_normalized_score_for_v1_1": row.get("base_normalized_score_for_v1_1"),
                "true_theme_score": row.get("true_theme_score"),
                "cleaned_concept_score": row.get("cleaned_concept_score"),
                "capital_activity_score": row.get("capital_activity_score"),
                "cleaned_v1_1_preview_score": row.get("cleaned_v1_1_preview_score"),
                "cleaned_v1_1_score_delta": row.get("cleaned_v1_1_score_delta"),
                "selection_score": row.get("selection_score"),
                "selection_score_source": row.get("selection_score_source"),
            },
            "concept_domain": {
                "enabled": row.get("preview_scoring_mode") == HISTORICAL_PREVIEW_SCORING_MODE_CLEANED_V1_1,
                "stage": "M4_HISTORICAL_CLEANED_V1_1_PREVIEW_ONLY",
                "scope": "artifact-only historical candidate scoring preview; no strategy_signal write, no M5 result write, no production route",
                "true_theme_names": row.get("true_theme_names"),
                "true_theme_score": row.get("true_theme_score"),
                "cleaned_concept_names": row.get("cleaned_concept_names"),
                "cleaned_concept_score": row.get("cleaned_concept_score"),
                "filtered_generic_concept_names": row.get("filtered_generic_concept_names"),
                "style_tag_names": row.get("style_tag_names"),
                "state_event_tag_names": row.get("state_event_tag_names"),
                "index_channel_tag_names": row.get("index_channel_tag_names"),
                "holding_structure_tag_names": row.get("holding_structure_tag_names"),
                "policy_attribute_tag_names": row.get("policy_attribute_tag_names"),
                "capital_activity_score": row.get("capital_activity_score"),
                "cleaned_v1_1_preview_score": row.get("cleaned_v1_1_preview_score"),
                "selection_score_source": row.get("selection_score_source"),
            },
            "market_inputs": dict(market_inputs),
            "guardrails": [
                "no_lookahead_feature_date_lte_signal_as_of_date",
                "concept_strength_enabled_false" if row.get("preview_scoring_mode") != HISTORICAL_PREVIEW_SCORING_MODE_CLEANED_V1_1 else "cleaned_v1_1_preview_artifact_only",
                "artifact_only_no_strategy_signal_write",
            ],
        }

    def _build_historical_parameter_payload(
        self,
        *,
        config: RegimeSectorIndustryHistoricalSignalGenerationPreviewConfig,
        market_regime: str,
        source_feature_date: date,
    ) -> dict[str, Any]:
        return {
            "strategy_code": config.strategy_code,
            "strategy_version_code": config.strategy_version_code,
            "feature_set_code": config.feature_set_code,
            "feature_set_version": config.feature_set_version,
            "industry_tag_type": config.industry_tag_type,
            "benchmark_index_code": config.benchmark_index_code,
            "target_top_n": config.target_top_n,
            "market_regime": market_regime,
            "confirmed_market_regime": market_regime,
            "source_feature_date": source_feature_date,
            "formula_refs": {
                "stock_alpha_score": "0.40*feat_mom_20 + 0.30*feat_trend_strength_20 + 0.20*feat_tradability_score + 0.10*(1-feat_volatility_rank_20)",
                "risk_penalty_score": "0.70*feat_volatility_rank_20 + 0.30*(1-feat_tradability_score)",
                "base_preview_score": "route.industry_strength_weight*feat_industry_strength_20 + route.stock_alpha_weight*stock_alpha_score - route.risk_penalty_weight*risk_penalty_score",
                "candidate_strategy_score": "regime-specific candidate strategy score using only existing M3 features; see candidate_strategy.score_formula_ref",
                "final_preview_score": "candidate_strategy_score when available, otherwise base_preview_score",
            },
            "route_name": route_name_for_regime_local(market_regime),
            "candidate_strategy": {
                **candidate_strategy_config_for_regime_local(market_regime),
                "score_formula_ref": self._candidate_strategy_score_formula_ref(market_regime),
            },
            "market_regime_display": market_regime_display_label_local(market_regime),
            "market_regime_confirmation_policy": {
                "raw_regime_used_for": "diagnostic_only",
                "confirmed_regime_used_for": "strategy_route_and_score",
                "confirmation_window_days": REGIME_CONFIRMATION_WINDOW_DAYS,
                "confirmation_min_matches": REGIME_CONFIRMATION_MIN_MATCHES,
                "min_days_in_state": REGIME_MIN_DAYS_IN_STATE,
            },
            "concept_strength_enabled": config.preview_scoring_mode == HISTORICAL_PREVIEW_SCORING_MODE_CLEANED_V1_1,
            "preview_scoring_mode": config.preview_scoring_mode,
            "cleaned_v1_1_formula": "clamp(0.70*base_normalized_score_for_v1_1 + 0.15*true_theme_score + 0.15*capital_activity_score - observation_penalty, 0, 1)",
            "write_mode": HISTORICAL_PREVIEW_WRITE_MODE,
        }

    def _batch_summary_row(self, **kwargs: Any) -> dict[str, Any]:
        row = {key: None for key in HISTORICAL_PREVIEW_BATCH_COLUMNS}
        row.update(kwargs)
        row.setdefault("score_input_row_count", 0)
        row.setdefault("eligible_candidate_count", 0)
        row.setdefault("preview_signal_row_count", 0)
        row.setdefault("required_feature_pass_count", 0)
        row.setdefault("required_feature_warn_count", 0)
        row.setdefault("required_feature_fail_count", 0)
        return row

    def _action(self, severity: str, item: str, reason: str, next_step: str) -> dict[str, Any]:
        return {"severity": severity, "item": item, "reason": reason, "next_step": next_step}

    def _parse_date(self, value: Any) -> date | None:
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

    def _write_preview_artifacts(
        self,
        output_dir: Path,
        report_date: str,
        result: RegimeSectorIndustryHistoricalSignalGenerationPreviewResult,
        preview_rows: Sequence[Mapping[str, Any]],
        historical_regime_daily_profile_rows: Sequence[Mapping[str, Any]],
    ) -> HistoricalSignalGenerationPreviewArtifacts:
        json_path = output_dir / f"m4_historical_signal_generation_preview_{report_date}.json"
        markdown_path = output_dir / f"m4_historical_signal_generation_preview_{report_date}.md"
        signal_preview_rows_path = output_dir / f"m4_historical_signal_preview_rows_{report_date}.csv"
        batch_summary_path = output_dir / f"m4_historical_signal_preview_batch_summary_{report_date}.csv"
        feature_coverage_path = output_dir / f"m4_historical_signal_preview_feature_coverage_{report_date}.csv"
        action_items_path = output_dir / f"m4_historical_signal_preview_action_items_{report_date}.csv"
        historical_regime_daily_profile_path = output_dir / f"m4_historical_regime_daily_profile_{report_date}.csv"

        artifact_payload = asdict(result)
        artifact_payload["artifacts"] = None
        json_path.write_text(json.dumps(artifact_payload, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
        markdown_path.write_text(self._build_preview_markdown(result), encoding="utf-8")
        write_csv(signal_preview_rows_path, preview_rows, HISTORICAL_PREVIEW_SIGNAL_COLUMNS)
        write_csv(batch_summary_path, result.batch_summary, HISTORICAL_PREVIEW_BATCH_COLUMNS)
        write_csv(feature_coverage_path, result.feature_coverage, HISTORICAL_PREVIEW_COVERAGE_COLUMNS)
        write_csv(action_items_path, result.action_items, HISTORICAL_PREVIEW_ACTION_COLUMNS)
        write_csv(
            historical_regime_daily_profile_path,
            historical_regime_daily_profile_rows,
            HISTORICAL_REGIME_DAILY_PROFILE_COLUMNS,
        )
        return HistoricalSignalGenerationPreviewArtifacts(
            json_path=str(json_path),
            markdown_path=str(markdown_path),
            signal_preview_rows_csv_path=str(signal_preview_rows_path),
            batch_summary_csv_path=str(batch_summary_path),
            feature_coverage_csv_path=str(feature_coverage_path),
            action_items_csv_path=str(action_items_path),
            historical_regime_daily_profile_csv_path=str(historical_regime_daily_profile_path),
        )

    def _build_preview_markdown(self, result: RegimeSectorIndustryHistoricalSignalGenerationPreviewResult) -> str:
        summary = result.summary
        decision = result.validation_decision
        lines = [
            f"# M4 Historical Signal Generation Preview Dry-Run - {result.report_date}",
            "",
            f"- status: `{result.status}`",
            f"- request_id: `{result.research_backtest_request_id}`",
            f"- planned_signal_pair_count: `{summary.get('planned_signal_pair_count')}`",
            f"- processed_signal_pair_count: `{summary.get('processed_signal_pair_count')}`",
            f"- preview_signal_row_count: `{summary.get('preview_signal_row_count')}`",
            f"- zero_row_batch_count: `{summary.get('zero_row_batch_count')}`",
            f"- raw_regime_transition_count: `{summary.get('raw_regime_transition_count')}`",
            f"- confirmed_regime_transition_count: `{summary.get('confirmed_regime_transition_count')}`",
            f"- one_day_confirmed_state_count: `{summary.get('one_day_confirmed_state_count')}`",
            f"- historical_regime_daily_profile_row_count: `{summary.get('historical_regime_daily_profile_row_count')}`",
            f"- can_start_m4_historical_signal_db_write_preview: `{decision.get('can_start_m4_historical_signal_db_write_preview')}`",
            f"- can_write_strategy_signal_now: `{decision.get('can_write_strategy_signal_now')}`",
            f"- can_execute_backtest_now: `{decision.get('can_execute_backtest_now')}`",
            f"- can_route_to_paper_trading_now: `{decision.get('can_route_to_paper_trading_now')}`",
            "",
            "## Boundary",
            "",
            "This artifact generates historical strategy-signal preview rows and a historical regime daily profile only. It does not write strategy_signal, create M5 requests/results, execute backtests, or route to paper trading.",
            "",
            "## File reuse decision",
            "",
            f"- new_files_added_by_this_patch: `{(summary.get('file_reuse_decision') or {}).get('new_files_added_by_this_patch')}`",
            f"- reason: {(summary.get('file_reuse_decision') or {}).get('reason')}",
        ]
        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Historical signal DB write preview
# ---------------------------------------------------------------------------
# This continues to reuse the existing M4 historical signal generation module.
# It transforms validated historical preview rows into DB-write candidate rows
# and checks DB contracts, but it does not insert strategy_signal rows.

HISTORICAL_DB_WRITE_PREVIEW_STAGE = "M4_HISTORICAL_SIGNAL_DB_WRITE_PREVIEW"
HISTORICAL_DB_WRITE_PREVIEW_SOURCE_STAGE = HISTORICAL_PREVIEW_STAGE
HISTORICAL_DB_WRITE_PREVIEW_WRITE_MODE = "HISTORICAL_DB_WRITE_PREVIEW_ARTIFACT_ONLY"
HISTORICAL_DB_WRITE_CANDIDATE_MODE = "HISTORICAL_PREVIEW_SCOPE_DB_WRITE_CANDIDATE"
DEFAULT_HISTORICAL_DB_WRITE_PREVIEW_OUTPUT_DIR = Path("artifacts") / "m4" / "historical_signal_db_write_preview"

HISTORICAL_DB_WRITE_CANDIDATE_COLUMNS = (
    "db_write_candidate_id",
    "source_preview_signal_id",
    "planned_write_mode",
    "strategy_code",
    "strategy_version_code",
    "strategy_version_id",
    "source_preview_stage",
    "as_of_date",
    "effective_date",
    "subject_type",
    "subject_key",
    "instrument_id",
    "signal_role",
    "signal_side",
    "signal_action",
    "raw_score",
    "normalized_score",
    "confidence_score",
    "rank_in_batch",
    "universe_size",
    "reason_code",
    "reason_payload_json",
    "parameter_payload_json",
    "instrument_code",
    "display_name",
    "sequence_no",
    "source_feature_date",
    "market_regime",
    "existing_same_version_date_rows",
    "candidate_status",
    "candidate_detail",
)

HISTORICAL_DB_WRITE_DATE_SUMMARY_COLUMNS = (
    "as_of_date",
    "effective_date",
    "source_preview_row_count",
    "candidate_row_count",
    "existing_same_version_date_rows",
    "status",
    "detail",
)

HISTORICAL_DB_WRITE_CONTRACT_CHECK_COLUMNS = (
    "check_name",
    "status",
    "row_count",
    "detail",
)

HISTORICAL_DB_WRITE_ACTION_COLUMNS = ACTION_COLUMNS


@dataclass(frozen=True)
class RegimeSectorIndustryHistoricalSignalDbWritePreviewConfig:
    report_date: str
    preview_artifact_dir: Path = DEFAULT_HISTORICAL_PREVIEW_OUTPUT_DIR
    output_dir: Path = DEFAULT_HISTORICAL_DB_WRITE_PREVIEW_OUTPUT_DIR
    strategy_code: str = STRATEGY_CODE
    strategy_version_code: str = DEFAULT_STRATEGY_VERSION_CODE
    research_backtest_request_id: int | None = None
    benchmark_index_code: str = "000300.SH"
    min_candidate_rows: int = 1000
    max_rows: int | None = None
    allow_existing_same_version_date: bool = False


@dataclass(frozen=True)
class HistoricalSignalDbWritePreviewArtifacts:
    json_path: str
    markdown_path: str
    candidate_rows_csv_path: str
    date_summary_csv_path: str
    contract_check_csv_path: str
    action_items_csv_path: str


@dataclass(frozen=True)
class RegimeSectorIndustryHistoricalSignalDbWritePreviewResult:
    status: str
    generated_at: str
    report_date: str
    strategy_code: str
    strategy_version_code: str
    stage: str
    source_stage: str
    research_backtest_request_id: int | None
    benchmark_index_code: str
    summary: dict[str, Any]
    validation_decision: dict[str, Any]
    date_summary: list[dict[str, Any]]
    contract_check: list[dict[str, Any]]
    action_items: list[dict[str, Any]]
    artifacts: HistoricalSignalDbWritePreviewArtifacts | None = None


@dataclass(frozen=True)
class RegimeSectorIndustryHistoricalSignalDbWritePreviewTaskResult:
    result: RegimeSectorIndustryHistoricalSignalDbWritePreviewResult


class RegimeSectorIndustryHistoricalSignalDbWritePreviewService:
    """Build historical strategy_signal DB-write candidate artifacts only.

    This is a DB contract/write preview, not a writer. It deliberately keeps
    can_write_strategy_signal_now=false so a later controlled write patch can
    require explicit confirmation.
    """

    def __init__(self, engine: Engine | None) -> None:
        self.engine = engine

    def preview_write(
        self,
        config: RegimeSectorIndustryHistoricalSignalDbWritePreviewConfig,
        *,
        progress_callback: Callable[[str], None] | None = None,
    ) -> RegimeSectorIndustryHistoricalSignalDbWritePreviewResult:
        def progress(message: str) -> None:
            if progress_callback:
                progress_callback(message)

        source_dir = Path(config.preview_artifact_dir)
        output_dir = Path(config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        preview_json_path = find_artifact_file(source_dir, "m4_historical_signal_generation_preview", config.report_date, "json")
        preview_rows_path = find_artifact_file(source_dir, "m4_historical_signal_preview_rows", config.report_date, "csv")
        preview_payload = read_json(preview_json_path) if preview_json_path.exists() else {}
        preview_rows = self._read_csv(preview_rows_path) if preview_rows_path.exists() else []
        if config.max_rows is not None:
            preview_rows = preview_rows[: max(0, config.max_rows)]
        progress(f"PREVIEW_ARTIFACTS_LOADED status={preview_payload.get('status')} rows={len(preview_rows)} json={preview_json_path} csv={preview_rows_path}")

        source_summary = dict(preview_payload.get("summary") or {})
        source_decision = dict(preview_payload.get("validation_decision") or {})
        request_id = config.research_backtest_request_id or safe_int(preview_payload.get("research_backtest_request_id")) or safe_int(source_summary.get("research_backtest_request_id"))

        action_items: list[dict[str, Any]] = []
        contract_check: list[dict[str, Any]] = []
        date_summary: list[dict[str, Any]] = []
        candidate_rows: list[dict[str, Any]] = []

        if not preview_json_path.exists():
            action_items.append(self._action("BLOCKER", "preview_json_missing", f"No preview json found under {source_dir}.", "Rerun M4 historical signal preview dry-run."))
        if not preview_rows_path.exists():
            action_items.append(self._action("BLOCKER", "preview_rows_missing", f"No preview rows csv found under {source_dir}.", "Rerun M4 historical signal preview dry-run."))
        if str(preview_payload.get("status")) not in {"PASS", "PASS_WITH_WARN"}:
            action_items.append(self._action("BLOCKER", "preview_status", f"Preview status is {preview_payload.get('status')}.", "Resolve historical signal preview blockers before DB write preview."))
        if not bool_value(source_decision.get("can_start_m4_historical_signal_db_write_preview")):
            action_items.append(self._action("BLOCKER", "db_write_preview_gate_closed", "Historical preview did not open the DB-write preview gate.", "Rerun historical signal preview after feature coverage is fixed."))
        if bool_value(source_decision.get("can_write_strategy_signal_now")):
            action_items.append(self._action("BLOCKER", "unexpected_write_gate_open", "Source preview unexpectedly allows direct strategy_signal write.", "Keep direct writes blocked and use controlled DB write only."))
        if not preview_rows:
            action_items.append(self._action("BLOCKER", "preview_rows_empty", "No historical preview rows were found.", "Rerun preview dry-run."))
        if self.engine is None:
            action_items.append(self._action("BLOCKER", "db_engine_missing", "A DB engine is required to validate strategy_signal write contracts.", "Run this task from the project environment with V2_SQLALCHEMY_URL configured."))

        strategy_version_profile: dict[str, Any] = {
            "query_status": "SKIPPED",
            "strategy_definition_id": None,
            "strategy_version_id": None,
        }
        existing_by_pair: dict[tuple[str, str], int] = {}
        if not any(item.get("severity") == "BLOCKER" for item in action_items):
            assert self.engine is not None
            with self.engine.connect() as conn:
                table_columns = self._load_table_columns(conn)
                contract_check.extend(self._db_contract_checks(table_columns))
                strategy_version_profile = self._resolve_strategy_version(conn, config.strategy_code, config.strategy_version_code)
                contract_check.append(
                    self._check(
                        "strategy_version_resolved",
                        "PASS" if strategy_version_profile.get("query_status") == "PASS" else "FAIL",
                        json.dumps(strategy_version_profile, ensure_ascii=False, default=json_default),
                        rows=1 if strategy_version_profile.get("strategy_version_id") else 0,
                    )
                )
                strategy_version_id = safe_int(strategy_version_profile.get("strategy_version_id"))
                if strategy_version_id is None:
                    action_items.append(self._action("BLOCKER", "strategy_version_resolved", "Could not resolve strategy_version_id.", "Seed or repair strategy metadata before historical signal DB write preview."))
                else:
                    prepared_rows, preparation_checks = self._prepare_candidate_rows(preview_rows, strategy_version_id=strategy_version_id, config=config)
                    contract_check.extend(preparation_checks)
                    instrument_ids = [safe_int(row.get("instrument_id")) for row in prepared_rows]
                    existing_instruments = self._load_existing_instrument_ids(conn, [value for value in instrument_ids if value is not None])
                    missing_instruments = sorted({value for value in instrument_ids if value is not None and value not in existing_instruments})
                    contract_check.append(self._check("instrument_resolution", "PASS" if not missing_instruments else "FAIL", f"missing_instrument_count={len(missing_instruments)}", rows=len(prepared_rows)))
                    if missing_instruments:
                        action_items.append(self._action("BLOCKER", "instrument_resolution", f"Some candidate instrument_id values are missing: {missing_instruments[:10]}", "Fix instrument metadata or regenerate preview rows."))
                    existing_by_pair = self._load_existing_signal_counts_by_pair(conn, strategy_version_id=strategy_version_id, candidate_rows=prepared_rows)
                    candidate_rows = self._attach_existing_counts(prepared_rows, existing_by_pair=existing_by_pair)
                    date_summary = self._build_date_summary(candidate_rows, existing_by_pair=existing_by_pair)
                    if len(candidate_rows) < config.min_candidate_rows:
                        action_items.append(self._action("BLOCKER", "candidate_row_count", f"candidate_rows={len(candidate_rows)} below min_candidate_rows={config.min_candidate_rows}", "Do not continue until historical preview row count is complete."))
                    existing_rows = sum(existing_by_pair.values())
                    existing_pairs = sum(1 for value in existing_by_pair.values() if value > 0)
                    existing_status = "WARN" if existing_rows > 0 else "PASS"
                    contract_check.append(self._check("existing_signal_rows_same_version_dates", existing_status, f"existing_pairs={existing_pairs}; existing_rows={existing_rows}; allow_existing_same_version_date={config.allow_existing_same_version_date}", rows=existing_rows))
                    if existing_rows > 0:
                        severity = "WARN" if config.allow_existing_same_version_date else "WARN"
                        action_items.append(
                            self._action(
                                severity,
                                "existing_signal_rows_same_version_dates",
                                f"{existing_rows} strategy_signal rows already exist for {existing_pairs} same strategy_version/as_of/effective date pair(s).",
                                "Before the controlled write step, decide whether to append a new historical run or skip already-written preview dates.",
                            )
                        )

        fail_checks = [row for row in contract_check if str(row.get("status", "")).upper() == "FAIL"]
        blocker_count = sum(1 for item in action_items if item.get("severity") == "BLOCKER") + len(fail_checks)
        warn_count = sum(1 for item in action_items if item.get("severity") == "WARN") + sum(1 for row in contract_check if str(row.get("status", "")).upper() == "WARN")
        status = "FAIL" if blocker_count else "PASS_WITH_WARN" if warn_count else "PASS"

        distinct_as_of_dates = len({str(row.get("as_of_date")) for row in candidate_rows if row.get("as_of_date")})
        distinct_effective_dates = len({str(row.get("effective_date")) for row in candidate_rows if row.get("effective_date")})
        existing_signal_rows = sum(existing_by_pair.values())
        existing_signal_pairs = sum(1 for value in existing_by_pair.values() if value > 0)
        summary = {
            "research_backtest_request_id": request_id,
            "source_preview_status": preview_payload.get("status"),
            "source_preview_row_count": source_summary.get("preview_signal_row_count") or len(preview_rows),
            "candidate_row_count": len(candidate_rows),
            "distinct_as_of_dates": distinct_as_of_dates,
            "distinct_effective_dates": distinct_effective_dates,
            "strategy_version_profile": strategy_version_profile,
            "existing_same_version_date_pair_count": existing_signal_pairs,
            "existing_signal_rows_same_version_dates": existing_signal_rows,
            "planned_write_mode": HISTORICAL_DB_WRITE_CANDIDATE_MODE,
            "write_mode": HISTORICAL_DB_WRITE_PREVIEW_WRITE_MODE,
            "file_reuse_decision": {
                "new_files_added_by_this_patch": 0,
                "modified_existing_files": [
                    "src/stock_quant_v2/strategy_domain/services/regime_sector_industry_historical_signal_generation_design_service.py",
                    "src/stock_quant_v2/strategy_domain/tasks/build_regime_sector_industry_historical_signal_generation_design.py",
                    "src/stock_quant_v2/scripts/bootstrap_m4_historical_signal_generation_design.py",
                    "tests/strategy/test_regime_sector_industry_historical_signal_generation_design_service.py",
                ],
                "reason": "DB write preview is a continuation of the M4 historical signal generation module; it is artifact-only and should not add another service/script file.",
            },
        }
        validation_decision = {
            "manual_review_required": True,
            "blocker_count": blocker_count,
            "warn_count": warn_count,
            "can_start_m4_historical_signal_controlled_db_write": status != "FAIL",
            "can_write_strategy_signal_now": False,
            "can_start_m5_historical_backtest_request_write_preview": False,
            "can_execute_backtest_now": False,
            "can_create_research_backtest_result_now": False,
            "can_start_m5_backtest_result_write_preview": False,
            "can_route_to_paper_trading_now": False,
            "performance_claim_allowed": False,
            "historical_signal_db_write_preview_only": True,
            "next_research_step": "Review candidate rows and existing-signal warnings, then run a controlled historical strategy_signal DB write only with explicit confirmation.",
        }
        if status != "FAIL":
            action_items.extend(
                [
                    self._action("WARN", "artifact_only_boundary", "This step generated DB-write candidates only; no strategy_signal rows were inserted.", "Run the controlled write step only after manual review."),
                    self._action("WARN", "m5_still_blocked", "M5 historical request write remains blocked until historical strategy_signal rows are actually written and verified.", "Do not start M5 historical request write preview yet."),
                ]
            )
            warn_count = sum(1 for item in action_items if item.get("severity") == "WARN") + sum(1 for row in contract_check if str(row.get("status", "")).upper() == "WARN")
            status = "PASS_WITH_WARN" if warn_count else "PASS"
            validation_decision["warn_count"] = warn_count
            validation_decision["blocker_count"] = blocker_count

        result = RegimeSectorIndustryHistoricalSignalDbWritePreviewResult(
            status=status,
            generated_at=utc_now_iso(),
            report_date=config.report_date,
            strategy_code=config.strategy_code,
            strategy_version_code=config.strategy_version_code,
            stage=HISTORICAL_DB_WRITE_PREVIEW_STAGE,
            source_stage=HISTORICAL_DB_WRITE_PREVIEW_SOURCE_STAGE,
            research_backtest_request_id=request_id,
            benchmark_index_code=config.benchmark_index_code,
            summary=summary,
            validation_decision=validation_decision,
            date_summary=date_summary,
            contract_check=contract_check,
            action_items=action_items,
            artifacts=None,
        )
        artifacts = self._write_artifacts(output_dir, config.report_date, result, candidate_rows)
        return RegimeSectorIndustryHistoricalSignalDbWritePreviewResult(**{**asdict(result), "artifacts": artifacts})

    def _read_csv(self, path: Path) -> list[dict[str, Any]]:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]

    def _load_table_columns(self, conn: Any) -> dict[str, set[str]]:
        rows = conn.execute(
            text(
                """
                select table_name, column_name
                from information_schema.columns
                where table_schema = current_schema()
                  and table_name in ('strategy_signal', 'ops_run', 'meta_instrument', 'strategy_definition', 'strategy_version')
                """
            )
        ).mappings().all()
        table_columns: dict[str, set[str]] = {}
        for row in rows:
            table_columns.setdefault(str(row["table_name"]), set()).add(str(row["column_name"]))
        return table_columns

    def _db_contract_checks(self, table_columns: Mapping[str, set[str]]) -> list[dict[str, Any]]:
        checks: list[dict[str, Any]] = []
        for table_name in ("strategy_signal", "ops_run", "meta_instrument", "strategy_definition", "strategy_version"):
            checks.append(self._check(f"db_table:{table_name}", "PASS" if table_name in table_columns else "FAIL", f"columns={sorted(table_columns.get(table_name, []))}", rows=0))
        signal_required = (
            "run_id",
            "strategy_version_id",
            "as_of_date",
            "effective_date",
            "subject_type",
            "subject_key",
            "instrument_id",
            "signal_role",
            "signal_side",
            "signal_action",
            "raw_score",
            "normalized_score",
            "confidence_score",
            "rank_in_batch",
            "universe_size",
            "reason_code",
            "reason_payload_json",
            "parameter_payload_json",
            "published_at",
            "created_at",
        )
        signal_missing = [column for column in signal_required if column not in table_columns.get("strategy_signal", set())]
        checks.append(self._check("strategy_signal_required_columns", "PASS" if not signal_missing else "FAIL", f"missing={signal_missing}", rows=0))
        return checks

    def _resolve_strategy_version(self, conn: Any, strategy_code: str, strategy_version_code: str) -> dict[str, Any]:
        profile = {
            "query_status": "NOT_RUN",
            "strategy_code": strategy_code,
            "strategy_version_code": strategy_version_code,
            "strategy_definition_id": None,
            "strategy_version_id": None,
            "version_status": None,
        }
        try:
            columns = self._table_columns(conn, "strategy_version")
            version_code_column = "version_code" if "version_code" in columns else "code" if "code" in columns else None
            status_expr = "sv.status" if "status" in columns else "cast(null as text)"
            if version_code_column is None:
                profile["query_status"] = "MISSING_VERSION_CODE_COLUMN"
                return profile
            row = conn.execute(
                text(
                    f"""
                    select sd.id as strategy_definition_id,
                           sv.id as strategy_version_id,
                           {status_expr} as version_status
                    from strategy_definition sd
                    join strategy_version sv on sv.strategy_definition_id = sd.id
                    where sd.strategy_code = :strategy_code
                      and sv.{version_code_column} = :strategy_version_code
                    order by sv.id desc
                    limit 1
                    """
                ),
                {"strategy_code": strategy_code, "strategy_version_code": strategy_version_code},
            ).mappings().first()
            if not row:
                profile["query_status"] = "NOT_FOUND"
                return profile
            profile.update({key: json_default(value) if value is not None else None for key, value in dict(row).items()})
            profile["query_status"] = "PASS"
            return profile
        except Exception as exc:
            profile["query_status"] = "ERROR"
            profile["error"] = str(exc)[:500]
            return profile

    def _table_columns(self, conn: Any, table_name: str) -> set[str]:
        rows = conn.execute(
            text(
                """
                select column_name
                from information_schema.columns
                where table_schema = current_schema()
                  and table_name = :table_name
                """
            ),
            {"table_name": table_name},
        ).mappings().all()
        return {str(row["column_name"]) for row in rows}

    def _prepare_candidate_rows(
        self,
        preview_rows: Sequence[Mapping[str, Any]],
        *,
        strategy_version_id: int,
        config: RegimeSectorIndustryHistoricalSignalDbWritePreviewConfig,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        prepared: list[dict[str, Any]] = []
        checks: list[dict[str, Any]] = []
        required_columns = (
            "preview_signal_id",
            "as_of_date",
            "effective_date",
            "subject_type",
            "subject_key",
            "instrument_id",
            "signal_role",
            "signal_side",
            "signal_action",
            "raw_score",
            "normalized_score",
            "confidence_score",
            "rank_in_batch",
            "universe_size",
            "reason_code",
            "reason_payload_json",
            "parameter_payload_json",
        )
        missing_columns = [column for column in required_columns if preview_rows and column not in preview_rows[0]]
        if missing_columns:
            checks.append(self._check("preview_required_columns", "FAIL", f"missing={missing_columns}", rows=len(preview_rows)))
            return [], checks

        empty_counts: dict[str, int] = {column: 0 for column in required_columns}
        json_errors = 0
        score_out_of_bounds = 0
        duplicate_key_count = 0
        seen_keys: set[tuple[Any, ...]] = set()
        for index, row in enumerate(preview_rows, start=1):
            for column in required_columns:
                if not self._has_value(row.get(column)):
                    empty_counts[column] += 1
            try:
                reason_payload = self._parse_json_object(row.get("reason_payload_json"))
                parameter_payload = self._parse_json_object(row.get("parameter_payload_json"))
            except Exception:
                json_errors += 1
                reason_payload = {}
                parameter_payload = {}
            normalized_score = self._quantize_8(row.get("normalized_score"))
            confidence_score = self._quantize_8(row.get("confidence_score"))
            raw_score = self._quantize_8(row.get("raw_score"))
            for value in (normalized_score, confidence_score):
                if value is not None and (value < Decimal("0") or value > Decimal("1")):
                    score_out_of_bounds += 1
            as_of_date = self._parse_date(row.get("as_of_date"))
            effective_date = self._parse_date(row.get("effective_date"))
            subject_key = str(row.get("subject_key") or "").strip()
            signal_action = str(row.get("signal_action") or "").strip()
            unique_key = (strategy_version_id, as_of_date, effective_date, subject_key, signal_action)
            if unique_key in seen_keys:
                duplicate_key_count += 1
            seen_keys.add(unique_key)
            source_preview_signal_id = str(row.get("preview_signal_id") or "").strip()
            reason_payload.update(
                {
                    "db_write_preview_scope": True,
                    "planned_write_mode": HISTORICAL_DB_WRITE_CANDIDATE_MODE,
                    "source_preview_signal_id": source_preview_signal_id,
                    "m5_submission_allowed": False,
                    "paper_trading_allowed": False,
                }
            )
            parameter_payload.update(
                {
                    "write_mode": HISTORICAL_DB_WRITE_CANDIDATE_MODE,
                    "historical_signal_db_write_preview": True,
                    "m5_submission_allowed": False,
                    "paper_trading_allowed": False,
                }
            )
            prepared.append(
                {
                    "db_write_candidate_id": f"{config.strategy_code}:{as_of_date}:{index:05d}:{row.get('instrument_id')}",
                    "source_preview_signal_id": source_preview_signal_id,
                    "planned_write_mode": HISTORICAL_DB_WRITE_CANDIDATE_MODE,
                    "strategy_code": config.strategy_code,
                    "strategy_version_code": config.strategy_version_code,
                    "strategy_version_id": strategy_version_id,
                    "source_preview_stage": HISTORICAL_PREVIEW_STAGE,
                    "as_of_date": as_of_date,
                    "effective_date": effective_date,
                    "subject_type": str(row.get("subject_type") or "").strip(),
                    "subject_key": subject_key,
                    "instrument_id": safe_int(row.get("instrument_id")),
                    "signal_role": str(row.get("signal_role") or "").strip(),
                    "signal_side": str(row.get("signal_side") or "").strip(),
                    "signal_action": signal_action,
                    "raw_score": raw_score,
                    "normalized_score": normalized_score,
                    "confidence_score": confidence_score,
                    "rank_in_batch": safe_int(row.get("rank_in_batch")),
                    "universe_size": safe_int(row.get("universe_size")),
                    "reason_code": str(row.get("reason_code") or "").strip(),
                    "reason_payload_json": json.dumps(reason_payload, ensure_ascii=False, sort_keys=True, default=json_default),
                    "parameter_payload_json": json.dumps(parameter_payload, ensure_ascii=False, sort_keys=True, default=json_default),
                    "instrument_code": row.get("instrument_code"),
                    "display_name": row.get("display_name"),
                    "sequence_no": safe_int(row.get("sequence_no")),
                    "source_feature_date": self._parse_date(row.get("source_feature_date")),
                    "market_regime": row.get("market_regime"),
                    "existing_same_version_date_rows": 0,
                    "candidate_status": "PLANNED",
                    "candidate_detail": "artifact_only_no_strategy_signal_write",
                }
            )
        empty_failures = {column: count for column, count in empty_counts.items() if count > 0}
        checks.append(self._check("candidate_row_count", "PASS" if prepared else "FAIL", f"candidate_rows={len(prepared)}", rows=len(prepared)))
        checks.append(self._check("preview_required_values", "PASS" if not empty_failures else "FAIL", f"empty_counts={empty_failures}", rows=len(prepared)))
        checks.append(self._check("candidate_json_payloads", "PASS" if json_errors == 0 else "FAIL", f"json_errors={json_errors}", rows=len(prepared)))
        checks.append(self._check("candidate_score_bounds", "PASS" if score_out_of_bounds == 0 else "FAIL", f"score_out_of_bounds={score_out_of_bounds}", rows=len(prepared)))
        checks.append(self._check("candidate_unique_keys", "PASS" if duplicate_key_count == 0 else "FAIL", f"duplicate_key_count={duplicate_key_count}", rows=len(prepared)))
        return prepared, checks

    def _load_existing_instrument_ids(self, conn: Any, instrument_ids: Sequence[int]) -> set[int]:
        if not instrument_ids:
            return set()
        stmt = text("select id from meta_instrument where id in :ids").bindparams(bindparam("ids", expanding=True))
        rows = conn.execute(stmt, {"ids": sorted(set(instrument_ids))}).mappings().all()
        return {int(row["id"]) for row in rows}

    def _load_existing_signal_counts_by_pair(self, conn: Any, *, strategy_version_id: int, candidate_rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], int]:
        pairs = sorted({(str(row.get("as_of_date")), str(row.get("effective_date"))) for row in candidate_rows if row.get("as_of_date") and row.get("effective_date")})
        counts: dict[tuple[str, str], int] = {}
        for as_of_text, effective_text in pairs:
            count = int(
                conn.execute(
                    text(
                        """
                        select count(*)
                        from strategy_signal
                        where strategy_version_id = :strategy_version_id
                          and as_of_date = :as_of_date
                          and effective_date = :effective_date
                        """
                    ),
                    {
                        "strategy_version_id": strategy_version_id,
                        "as_of_date": self._parse_date(as_of_text),
                        "effective_date": self._parse_date(effective_text),
                    },
                ).scalar_one()
            )
            counts[(as_of_text, effective_text)] = count
        return counts

    def _attach_existing_counts(self, rows: Sequence[Mapping[str, Any]], *, existing_by_pair: Mapping[tuple[str, str], int]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for row in rows:
            pair = (str(row.get("as_of_date")), str(row.get("effective_date")))
            existing = int(existing_by_pair.get(pair, 0))
            new_row = dict(row)
            new_row["existing_same_version_date_rows"] = existing
            if existing > 0:
                new_row["candidate_status"] = "WARN"
                new_row["candidate_detail"] = "same strategy_version/as_of/effective rows already exist; controlled write must decide append-vs-skip"
            out.append(new_row)
        return out

    def _build_date_summary(self, rows: Sequence[Mapping[str, Any]], *, existing_by_pair: Mapping[tuple[str, str], int]) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str], int] = {}
        for row in rows:
            pair = (str(row.get("as_of_date")), str(row.get("effective_date")))
            grouped[pair] = grouped.get(pair, 0) + 1
        summary: list[dict[str, Any]] = []
        for pair, count in sorted(grouped.items()):
            existing = int(existing_by_pair.get(pair, 0))
            status = "WARN" if existing > 0 else "PASS"
            summary.append(
                {
                    "as_of_date": pair[0],
                    "effective_date": pair[1],
                    "source_preview_row_count": count,
                    "candidate_row_count": count,
                    "existing_same_version_date_rows": existing,
                    "status": status,
                    "detail": "existing same-version rows require append-vs-skip decision" if existing > 0 else "ready for controlled write preview",
                }
            )
        return summary

    def _write_artifacts(
        self,
        output_dir: Path,
        report_date: str,
        result: RegimeSectorIndustryHistoricalSignalDbWritePreviewResult,
        candidate_rows: Sequence[Mapping[str, Any]],
    ) -> HistoricalSignalDbWritePreviewArtifacts:
        json_path = output_dir / f"m4_historical_signal_db_write_preview_{report_date}.json"
        markdown_path = output_dir / f"m4_historical_signal_db_write_preview_{report_date}.md"
        candidate_rows_path = output_dir / f"m4_historical_signal_db_write_candidate_rows_{report_date}.csv"
        date_summary_path = output_dir / f"m4_historical_signal_db_write_date_summary_{report_date}.csv"
        contract_check_path = output_dir / f"m4_historical_signal_db_write_contract_check_{report_date}.csv"
        action_items_path = output_dir / f"m4_historical_signal_db_write_action_items_{report_date}.csv"

        artifact_payload = asdict(result)
        artifact_payload["artifacts"] = None
        json_path.write_text(json.dumps(artifact_payload, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
        markdown_path.write_text(self._build_markdown(result), encoding="utf-8")
        write_csv(candidate_rows_path, candidate_rows, HISTORICAL_DB_WRITE_CANDIDATE_COLUMNS)
        write_csv(date_summary_path, result.date_summary, HISTORICAL_DB_WRITE_DATE_SUMMARY_COLUMNS)
        write_csv(contract_check_path, result.contract_check, HISTORICAL_DB_WRITE_CONTRACT_CHECK_COLUMNS)
        write_csv(action_items_path, result.action_items, HISTORICAL_DB_WRITE_ACTION_COLUMNS)
        return HistoricalSignalDbWritePreviewArtifacts(
            json_path=str(json_path),
            markdown_path=str(markdown_path),
            candidate_rows_csv_path=str(candidate_rows_path),
            date_summary_csv_path=str(date_summary_path),
            contract_check_csv_path=str(contract_check_path),
            action_items_csv_path=str(action_items_path),
        )

    def _build_markdown(self, result: RegimeSectorIndustryHistoricalSignalDbWritePreviewResult) -> str:
        summary = result.summary
        decision = result.validation_decision
        lines = [
            f"# M4 Historical Signal DB Write Preview - {result.report_date}",
            "",
            f"- status: `{result.status}`",
            f"- request_id: `{result.research_backtest_request_id}`",
            f"- candidate_row_count: `{summary.get('candidate_row_count')}`",
            f"- distinct_as_of_dates: `{summary.get('distinct_as_of_dates')}`",
            f"- existing_signal_rows_same_version_dates: `{summary.get('existing_signal_rows_same_version_dates')}`",
            f"- can_start_m4_historical_signal_controlled_db_write: `{decision.get('can_start_m4_historical_signal_controlled_db_write')}`",
            f"- can_write_strategy_signal_now: `{decision.get('can_write_strategy_signal_now')}`",
            f"- can_start_m5_historical_backtest_request_write_preview: `{decision.get('can_start_m5_historical_backtest_request_write_preview')}`",
            f"- can_execute_backtest_now: `{decision.get('can_execute_backtest_now')}`",
            "",
            "## Boundary",
            "",
            "This artifact prepares DB-write candidate rows only. It does not insert strategy_signal, create M5 requests/results, execute backtests, or route to paper trading.",
        ]
        return "\n".join(lines) + "\n"

    def _parse_json_object(self, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return dict(value)
        text_value = str(value).strip()
        if not text_value:
            return {}
        parsed = json.loads(text_value)
        if not isinstance(parsed, dict):
            raise ValueError("JSON payload is not an object")
        return parsed

    def _has_value(self, value: Any) -> bool:
        return value is not None and not (isinstance(value, str) and value.strip() == "")

    def _parse_date(self, value: Any) -> date | None:
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

    def _to_decimal(self, value: Any) -> Decimal | None:
        if value is None:
            return None
        text_value = str(value).strip()
        if not text_value:
            return None
        try:
            return Decimal(text_value)
        except Exception:
            return None

    def _quantize_8(self, value: Any) -> Decimal | None:
        decimal_value = self._to_decimal(value)
        if decimal_value is None:
            return None
        return decimal_value.quantize(Decimal("0.00000001"))

    def _check(self, check_name: str, status: str, detail: str, *, rows: int) -> dict[str, Any]:
        return {"check_name": check_name, "status": status, "row_count": rows, "detail": detail}

    def _action(self, severity: str, item: str, reason: str, next_step: str) -> dict[str, Any]:
        return {"severity": severity, "item": item, "reason": reason, "next_step": next_step}


# Controlled historical strategy_signal DB write
# This section intentionally reuses the existing historical signal generation
# service module instead of adding another M4 file. It is the first controlled
# DB writer in this historical flow and must remain explicit, idempotent by
# default, and blocked from M5/M6/result claims.

HISTORICAL_CONTROLLED_DB_WRITE_STAGE = "M4_HISTORICAL_SIGNAL_CONTROLLED_DB_WRITE"
HISTORICAL_CONTROLLED_DB_WRITE_SOURCE_STAGE = "M4_HISTORICAL_SIGNAL_DB_WRITE_PREVIEW"
HISTORICAL_CONTROLLED_DB_WRITE_OUTPUT_DIR = Path("artifacts") / "m4" / "historical_signal_controlled_db_write"
HISTORICAL_CONTROLLED_DB_WRITE_RUN_TYPE = "M4_HIST_SIGNAL_WRITE"
HISTORICAL_CONTROLLED_DB_WRITE_MODE = "HISTORICAL_PREVIEW_SCOPE_CONTROLLED_DB_WRITE"

HISTORICAL_CONTROLLED_DB_WRITE_COLUMNS = (
    "write_row_id",
    "db_write_candidate_id",
    "strategy_signal_id",
    "ops_run_id",
    "strategy_version_id",
    "as_of_date",
    "effective_date",
    "subject_key",
    "instrument_id",
    "rank_in_batch",
    "candidate_status",
    "write_status",
    "detail",
)

HISTORICAL_CONTROLLED_DB_WRITE_DATE_SUMMARY_COLUMNS = (
    "as_of_date",
    "effective_date",
    "candidate_row_count",
    "inserted_row_count",
    "skipped_existing_row_count",
    "existing_same_version_date_rows_before",
    "status",
    "detail",
)

HISTORICAL_CONTROLLED_DB_WRITE_CONTRACT_CHECK_COLUMNS = (
    "check_name",
    "status",
    "row_count",
    "detail",
)

HISTORICAL_CONTROLLED_DB_WRITE_ACTION_COLUMNS = ACTION_COLUMNS


@dataclass(frozen=True)
class RegimeSectorIndustryHistoricalSignalControlledDbWriteConfig:
    report_date: str
    db_write_preview_artifact_dir: Path = DEFAULT_HISTORICAL_DB_WRITE_PREVIEW_OUTPUT_DIR
    output_dir: Path = HISTORICAL_CONTROLLED_DB_WRITE_OUTPUT_DIR
    strategy_code: str = STRATEGY_CODE
    strategy_version_code: str = DEFAULT_STRATEGY_VERSION_CODE
    research_backtest_request_id: int | None = None
    benchmark_index_code: str = "000300.SH"
    min_inserted_rows: int = 1000
    max_rows: int | None = None
    existing_date_policy: str = "skip"  # skip | fail | append
    dry_run: bool = False


@dataclass(frozen=True)
class HistoricalSignalControlledDbWriteArtifacts:
    json_path: str
    markdown_path: str
    inserted_rows_csv_path: str
    skipped_rows_csv_path: str
    date_summary_csv_path: str
    contract_check_csv_path: str
    action_items_csv_path: str


@dataclass(frozen=True)
class RegimeSectorIndustryHistoricalSignalControlledDbWriteResult:
    status: str
    generated_at: str
    report_date: str
    strategy_code: str
    strategy_version_code: str
    stage: str
    source_stage: str
    research_backtest_request_id: int | None
    benchmark_index_code: str
    summary: dict[str, Any]
    validation_decision: dict[str, Any]
    date_summary: list[dict[str, Any]]
    contract_check: list[dict[str, Any]]
    action_items: list[dict[str, Any]]
    artifacts: HistoricalSignalControlledDbWriteArtifacts | None = None


@dataclass(frozen=True)
class RegimeSectorIndustryHistoricalSignalControlledDbWriteTaskResult:
    result: RegimeSectorIndustryHistoricalSignalControlledDbWriteResult


class RegimeSectorIndustryHistoricalSignalControlledDbWriteService:
    """Controlled writer for historical strategy_signal rows.

    Default behavior is idempotent for the already-written latest preview date:
    if a same strategy_version/as_of/effective pair already has rows, the whole
    pair is skipped unless existing_date_policy=append is explicitly supplied.
    This avoids duplicating the 2026-04-29 -> 2026-04-30 preview-scope rows.
    """

    def __init__(self, engine: Engine | None) -> None:
        self.engine = engine

    def controlled_write(
        self,
        config: RegimeSectorIndustryHistoricalSignalControlledDbWriteConfig,
        *,
        progress_callback: Callable[[str], None] | None = None,
    ) -> RegimeSectorIndustryHistoricalSignalControlledDbWriteResult:
        def progress(message: str) -> None:
            if progress_callback:
                progress_callback(message)

        source_dir = Path(config.db_write_preview_artifact_dir)
        output_dir = Path(config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        preview_json_path = find_artifact_file(source_dir, "m4_historical_signal_db_write_preview", config.report_date, "json")
        candidate_rows_path = find_artifact_file(source_dir, "m4_historical_signal_db_write_candidate_rows", config.report_date, "csv")
        preview_payload = read_json(preview_json_path) if preview_json_path.exists() else {}
        candidate_rows = self._read_csv(candidate_rows_path) if candidate_rows_path.exists() else []
        if config.max_rows is not None:
            candidate_rows = candidate_rows[: max(0, config.max_rows)]
        progress(f"DB_WRITE_PREVIEW_ARTIFACTS_LOADED status={preview_payload.get('status')} candidates={len(candidate_rows)} json={preview_json_path} csv={candidate_rows_path}")

        source_summary = dict(preview_payload.get("summary") or {})
        source_decision = dict(preview_payload.get("validation_decision") or {})
        request_id = config.research_backtest_request_id or safe_int(preview_payload.get("research_backtest_request_id")) or safe_int(source_summary.get("research_backtest_request_id"))
        existing_date_policy = str(config.existing_date_policy or "skip").strip().lower()

        action_items: list[dict[str, Any]] = []
        contract_check: list[dict[str, Any]] = []
        date_summary: list[dict[str, Any]] = []
        inserted_rows: list[dict[str, Any]] = []
        skipped_rows: list[dict[str, Any]] = []
        ops_run_id: int | None = None

        if existing_date_policy not in {"skip", "fail", "append"}:
            action_items.append(self._action("BLOCKER", "existing_date_policy", f"Unsupported existing_date_policy={existing_date_policy}.", "Use skip, fail, or append."))
        if not preview_json_path.exists():
            action_items.append(self._action("BLOCKER", "db_write_preview_json_missing", f"No DB write preview json found under {source_dir}.", "Rerun mode=db_write_preview."))
        if not candidate_rows_path.exists():
            action_items.append(self._action("BLOCKER", "candidate_rows_missing", f"No DB write candidate rows csv found under {source_dir}.", "Rerun mode=db_write_preview."))
        if str(preview_payload.get("status")) not in {"PASS", "PASS_WITH_WARN"}:
            action_items.append(self._action("BLOCKER", "db_write_preview_status", f"DB write preview status is {preview_payload.get('status')}.", "Resolve DB write preview blockers before controlled write."))
        if not bool_value(source_decision.get("can_start_m4_historical_signal_controlled_db_write")):
            action_items.append(self._action("BLOCKER", "controlled_write_gate_closed", "DB write preview did not open controlled write gate.", "Rerun DB write preview after resolving blockers."))
        if bool_value(source_decision.get("can_write_strategy_signal_now")):
            action_items.append(self._action("BLOCKER", "unexpected_direct_write_gate_open", "DB write preview unexpectedly allows direct writes.", "Keep direct writes blocked and use this controlled writer only."))
        if not candidate_rows:
            action_items.append(self._action("BLOCKER", "candidate_rows_empty", "No candidate rows were found.", "Rerun historical signal DB write preview."))
        if self.engine is None:
            action_items.append(self._action("BLOCKER", "db_engine_missing", "A DB engine is required for controlled strategy_signal write.", "Run this task from the project environment with V2_SQLALCHEMY_URL configured."))

        candidate_count = len(candidate_rows)
        if not any(item.get("severity") == "BLOCKER" for item in action_items):
            assert self.engine is not None
            with self.engine.begin() as conn:
                table_columns = self._load_table_columns(conn)
                contract_check.extend(self._db_contract_checks(table_columns))
                if any(row.get("status") == "FAIL" for row in contract_check):
                    action_items.append(self._action("BLOCKER", "db_contract", "Required DB table or column contract check failed.", "Repair schema contract before controlled write."))
                    prepared_rows = []
                    prep_checks = []
                    pair_policy_rows = []
                    to_insert = []
                    existing_by_pair = {}
                else:
                    strategy_version_id = self._resolve_strategy_version_id(conn, config.strategy_code, config.strategy_version_code)
                    contract_check.append(self._check("strategy_version_resolved", "PASS" if strategy_version_id is not None else "FAIL", f"strategy_version_id={strategy_version_id}", rows=1 if strategy_version_id else 0))
                    if strategy_version_id is None:
                        action_items.append(self._action("BLOCKER", "strategy_version_resolved", "Could not resolve strategy_version_id.", "Seed or repair strategy metadata before controlled write."))
                        pair_policy_rows = []
                        existing_by_pair = {}
                    else:
                        prepared_rows, prep_checks = self._prepare_rows(candidate_rows, strategy_version_id=strategy_version_id)
                        contract_check.extend(prep_checks)
                        if any(row.get("status") == "FAIL" for row in prep_checks):
                            action_items.append(self._action("BLOCKER", "candidate_preparation", "Candidate rows failed validation.", "Fix DB write preview candidates before controlled write."))
                        existing_by_pair = self._load_existing_signal_counts_by_pair(conn, strategy_version_id=strategy_version_id, rows=prepared_rows)
                        pair_policy_rows = self._apply_existing_date_policy(prepared_rows, existing_by_pair=existing_by_pair, policy=existing_date_policy)
                        to_insert = [row for row in pair_policy_rows if row["write_status"] == "READY_TO_INSERT"]
                        skipped_rows = [self._write_row_projection(row, ops_run_id=None, strategy_signal_id=None) for row in pair_policy_rows if row["write_status"].startswith("SKIPPED")]
                        existing_pair_count = sum(1 for value in existing_by_pair.values() if value > 0)
                        existing_row_count = sum(int(value) for value in existing_by_pair.values() if value > 0)
                        contract_check.append(self._check("existing_date_policy", "FAIL" if existing_pair_count and existing_date_policy == "fail" else ("WARN" if existing_pair_count else "PASS"), f"policy={existing_date_policy}; existing_pairs={existing_pair_count}; existing_rows={existing_row_count}", rows=existing_row_count))
                        if existing_pair_count and existing_date_policy == "fail":
                            action_items.append(self._action("BLOCKER", "existing_same_version_dates", f"{existing_pair_count} same-version date pair(s) already have strategy_signal rows.", "Rerun with --existing-date-policy skip, or review and explicitly choose append."))
                        if not to_insert and existing_date_policy != "fail":
                            action_items.append(self._action("BLOCKER", "no_rows_to_insert", "No rows remain for controlled insert after applying existing-date policy.", "Review candidate rows and existing-date policy."))
                        if len(to_insert) < config.min_inserted_rows and not config.dry_run:
                            action_items.append(self._action("BLOCKER", "min_inserted_rows", f"Rows eligible for insert {len(to_insert)} < min_inserted_rows {config.min_inserted_rows}.", "Lower threshold only for diagnostics, or repair candidates."))
                        if not any(item.get("severity") == "BLOCKER" for item in action_items):
                            if config.dry_run:
                                ops_run_id = None
                                inserted_rows = [self._write_row_projection(row, ops_run_id=None, strategy_signal_id=None, status="DRY_RUN") for row in to_insert]
                            else:
                                ops_run_id = self._create_ops_run(conn, config=config, candidate_count=candidate_count, insert_count=len(to_insert), skip_count=len(skipped_rows), existing_date_policy=existing_date_policy)
                                inserted_rows = self._insert_strategy_signal_rows(conn, to_insert, ops_run_id=ops_run_id)
                        date_summary = self._build_date_summary(pair_policy_rows, existing_by_pair=existing_by_pair)
                        contract_check.append(self._check("controlled_insert_row_count", "PASS" if len(inserted_rows) >= config.min_inserted_rows or config.dry_run else "FAIL", f"inserted_rows={len(inserted_rows)}; skipped_rows={len(skipped_rows)}; dry_run={config.dry_run}", rows=len(inserted_rows)))
        try:
            if not date_summary and candidate_rows:
                date_summary = self._fallback_date_summary(candidate_rows)
        except Exception:
            date_summary = []

        blocker_count = sum(1 for row in contract_check if row.get("status") == "FAIL") + sum(1 for item in action_items if item.get("severity") == "BLOCKER")
        warn_count = sum(1 for row in contract_check if row.get("status") == "WARN") + sum(1 for item in action_items if item.get("severity") == "WARN")
        status = "FAIL" if blocker_count else ("PASS_WITH_WARN" if warn_count else "PASS")
        if status != "FAIL":
            action_items.extend(self._success_action_items(inserted_count=len(inserted_rows), skipped_count=len(skipped_rows)))
        summary = {
            "research_backtest_request_id": request_id,
            "source_preview_status": preview_payload.get("status"),
            "candidate_row_count": candidate_count,
            "inserted_row_count": len(inserted_rows),
            "skipped_existing_row_count": len(skipped_rows),
            "distinct_as_of_dates": len({str(row.get("as_of_date")) for row in candidate_rows if row.get("as_of_date")}),
            "ops_run_id": ops_run_id,
            "existing_date_policy": existing_date_policy,
            "dry_run": config.dry_run,
            "write_mode": HISTORICAL_CONTROLLED_DB_WRITE_MODE if not config.dry_run else "DRY_RUN_NO_DB_WRITE",
            "file_reuse_decision": {
                "new_files_added_by_this_patch": 0,
                "reused_entrypoint": "bootstrap_m4_historical_signal_generation_design.py",
                "reused_service_module": "regime_sector_industry_historical_signal_generation_design_service.py",
            },
        }
        decision = {
            "manual_review_required": True,
            "blocker_count": blocker_count,
            "warn_count": warn_count,
            "can_start_m5_historical_backtest_request_write_preview": status != "FAIL" and not config.dry_run,
            "can_write_strategy_signal_now": False,
            "can_execute_backtest_now": False,
            "can_create_research_backtest_result_now": False,
            "can_start_m5_backtest_result_write_preview": False,
            "can_route_to_paper_trading_now": False,
            "performance_claim_allowed": False,
            "historical_signal_controlled_db_write_done": status != "FAIL" and not config.dry_run,
            "next_research_step": "Run M5 historical backtest request write preview against the controlled historical signal scope; do not execute backtest yet." if status != "FAIL" else "Resolve controlled write blockers before M5.",
        }
        result = RegimeSectorIndustryHistoricalSignalControlledDbWriteResult(
            status=status,
            generated_at=utc_now_iso(),
            report_date=config.report_date,
            strategy_code=config.strategy_code,
            strategy_version_code=config.strategy_version_code,
            stage=HISTORICAL_CONTROLLED_DB_WRITE_STAGE,
            source_stage=HISTORICAL_CONTROLLED_DB_WRITE_SOURCE_STAGE,
            research_backtest_request_id=request_id,
            benchmark_index_code=config.benchmark_index_code,
            summary=summary,
            validation_decision=decision,
            date_summary=date_summary,
            contract_check=contract_check,
            action_items=action_items,
            artifacts=None,
        )
        artifacts = self._write_artifacts(output_dir, config.report_date, result, inserted_rows=inserted_rows, skipped_rows=skipped_rows)
        return RegimeSectorIndustryHistoricalSignalControlledDbWriteResult(**{**asdict(result), "artifacts": artifacts})

    def _read_csv(self, path: Path) -> list[dict[str, Any]]:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]

    def _action(self, severity: str, item: str, reason: str, next_step: str) -> dict[str, Any]:
        return {"severity": severity, "item": item, "reason": reason, "next_step": next_step}

    def _check(self, name: str, status: str, detail: str, *, rows: int = 0) -> dict[str, Any]:
        return {"check_name": name, "status": status, "row_count": rows, "detail": detail}

    def _load_table_columns(self, conn: Any) -> dict[str, set[str]]:
        required_tables = ["strategy_signal", "ops_run", "strategy_definition", "strategy_version", "meta_instrument"]
        return {table: self._table_columns(conn, table) for table in required_tables}

    def _table_columns(self, conn: Any, table_name: str) -> set[str]:
        rows = conn.execute(
            text(
                """
                select column_name
                from information_schema.columns
                where table_schema = current_schema()
                  and table_name = :table_name
                """
            ),
            {"table_name": table_name},
        ).all()
        return {str(row[0]) for row in rows}

    def _db_contract_checks(self, table_columns: Mapping[str, set[str]]) -> list[dict[str, Any]]:
        checks: list[dict[str, Any]] = []
        required_signal_columns = {
            "strategy_version_id", "run_id", "subject_type", "subject_key", "instrument_id", "signal_role", "signal_side", "signal_action",
            "as_of_date", "effective_date", "raw_score", "normalized_score", "confidence_score", "rank_in_batch", "universe_size",
            "reason_code", "reason_payload_json", "parameter_payload_json",
        }
        required_ops_columns = {"run_uid", "run_name", "run_type", "status", "trigger_type", "context_json", "started_at", "ended_at"}
        for table_name in ["strategy_signal", "ops_run", "strategy_definition", "strategy_version", "meta_instrument"]:
            cols = table_columns.get(table_name, set())
            checks.append(self._check(f"db_table:{table_name}", "PASS" if cols else "FAIL", f"columns={sorted(cols)}", rows=0))
        missing_signal = sorted(required_signal_columns - table_columns.get("strategy_signal", set()))
        checks.append(self._check("strategy_signal_required_columns", "PASS" if not missing_signal else "FAIL", f"missing={missing_signal}", rows=0))
        missing_ops = sorted(required_ops_columns - table_columns.get("ops_run", set()))
        checks.append(self._check("ops_run_required_columns", "PASS" if not missing_ops else "FAIL", f"missing={missing_ops}", rows=0))
        return checks

    def _resolve_strategy_version_id(self, conn: Any, strategy_code: str, strategy_version_code: str) -> int | None:
        columns = self._table_columns(conn, "strategy_version")
        version_code_column = "version_code" if "version_code" in columns else "code" if "code" in columns else None
        if version_code_column is None:
            return None
        row = conn.execute(
            text(
                f"""
                select sv.id as strategy_version_id
                from strategy_definition sd
                join strategy_version sv on sv.strategy_definition_id = sd.id
                where sd.strategy_code = :strategy_code
                  and sv.{version_code_column} = :strategy_version_code
                order by sv.id desc
                limit 1
                """
            ),
            {"strategy_code": strategy_code, "strategy_version_code": strategy_version_code},
        ).mappings().first()
        return safe_int(row["strategy_version_id"]) if row else None

    def _prepare_rows(self, rows: Sequence[Mapping[str, Any]], *, strategy_version_id: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        prepared: list[dict[str, Any]] = []
        checks: list[dict[str, Any]] = []
        required = ["as_of_date", "effective_date", "subject_type", "subject_key", "instrument_id", "signal_role", "signal_side", "signal_action", "raw_score", "normalized_score", "confidence_score", "rank_in_batch", "universe_size", "reason_code", "reason_payload_json", "parameter_payload_json"]
        empty_counts = {column: 0 for column in required}
        json_errors = 0
        decimal_errors = 0
        for row in rows:
            for column in required:
                if not self._has_value(row.get(column)):
                    empty_counts[column] += 1
            try:
                reason_payload = self._parse_json_object(row.get("reason_payload_json"))
                parameter_payload = self._parse_json_object(row.get("parameter_payload_json"))
            except Exception:
                json_errors += 1
                reason_payload = {}
                parameter_payload = {}
            values = {
                "raw_score": self._to_decimal(row.get("raw_score")),
                "normalized_score": self._to_decimal(row.get("normalized_score")),
                "confidence_score": self._to_decimal(row.get("confidence_score")),
            }
            if any(value is None for value in values.values()):
                decimal_errors += 1
            as_of_date = self._parse_date(row.get("as_of_date"))
            effective_date = self._parse_date(row.get("effective_date"))
            prepared.append(
                {
                    "db_write_candidate_id": row.get("db_write_candidate_id"),
                    "strategy_version_id": strategy_version_id,
                    "as_of_date": as_of_date,
                    "effective_date": effective_date,
                    "subject_type": str(row.get("subject_type") or DEFAULT_SUBJECT_TYPE),
                    "subject_key": str(row.get("subject_key") or ""),
                    "instrument_id": safe_int(row.get("instrument_id")),
                    "signal_role": str(row.get("signal_role") or DEFAULT_SIGNAL_ROLE),
                    "signal_side": str(row.get("signal_side") or DEFAULT_SIGNAL_SIDE),
                    "signal_action": str(row.get("signal_action") or DEFAULT_SIGNAL_ACTION),
                    "raw_score": values["raw_score"],
                    "normalized_score": values["normalized_score"],
                    "confidence_score": values["confidence_score"],
                    "rank_in_batch": safe_int(row.get("rank_in_batch")),
                    "universe_size": safe_int(row.get("universe_size")),
                    "reason_code": str(row.get("reason_code") or ""),
                    "reason_payload_json": {**reason_payload, "controlled_db_write_scope": True, "m5_submission_allowed": False, "paper_trading_allowed": False},
                    "parameter_payload_json": {**parameter_payload, "controlled_db_write_scope": True, "write_mode": HISTORICAL_CONTROLLED_DB_WRITE_MODE, "m5_submission_allowed": False, "paper_trading_allowed": False},
                    "candidate_status": str(row.get("candidate_status") or "PLANNED"),
                    "write_status": "READY_TO_INSERT",
                    "detail": "ready for controlled insert",
                }
            )
        empty_failures = {column: count for column, count in empty_counts.items() if count > 0}
        checks.append(self._check("candidate_row_count", "PASS" if prepared else "FAIL", f"candidate_rows={len(prepared)}", rows=len(prepared)))
        checks.append(self._check("candidate_required_values", "PASS" if not empty_failures else "FAIL", f"empty_counts={empty_failures}", rows=len(prepared)))
        checks.append(self._check("candidate_json_payloads", "PASS" if json_errors == 0 else "FAIL", f"json_errors={json_errors}", rows=len(prepared)))
        checks.append(self._check("candidate_numeric_values", "PASS" if decimal_errors == 0 else "FAIL", f"decimal_errors={decimal_errors}", rows=len(prepared)))
        return prepared, checks

    def _load_existing_signal_counts_by_pair(self, conn: Any, *, strategy_version_id: int, rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], int]:
        pairs = sorted({(str(row.get("as_of_date")), str(row.get("effective_date"))) for row in rows if row.get("as_of_date") and row.get("effective_date")})
        counts: dict[tuple[str, str], int] = {}
        for as_of_text, effective_text in pairs:
            count = int(
                conn.execute(
                    text(
                        """
                        select count(*)
                        from strategy_signal
                        where strategy_version_id = :strategy_version_id
                          and as_of_date = :as_of_date
                          and effective_date = :effective_date
                        """
                    ),
                    {"strategy_version_id": strategy_version_id, "as_of_date": self._parse_date(as_of_text), "effective_date": self._parse_date(effective_text)},
                ).scalar_one()
            )
            counts[(as_of_text, effective_text)] = count
        return counts

    def _apply_existing_date_policy(self, rows: Sequence[Mapping[str, Any]], *, existing_by_pair: Mapping[tuple[str, str], int], policy: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for row in rows:
            pair = (str(row.get("as_of_date")), str(row.get("effective_date")))
            existing = int(existing_by_pair.get(pair, 0))
            new_row = dict(row)
            new_row["existing_same_version_date_rows_before"] = existing
            if existing > 0 and policy == "skip":
                new_row["write_status"] = "SKIPPED_EXISTING_DATE"
                new_row["detail"] = "same strategy_version/as_of/effective date already has rows; skipped by policy=skip"
            elif existing > 0 and policy == "append":
                new_row["write_status"] = "READY_TO_INSERT"
                new_row["detail"] = "same strategy_version/as_of/effective date already has rows; append explicitly requested"
            elif existing > 0 and policy == "fail":
                new_row["write_status"] = "BLOCKED_EXISTING_DATE"
                new_row["detail"] = "same strategy_version/as_of/effective date already has rows; policy=fail"
            else:
                new_row["write_status"] = "READY_TO_INSERT"
                new_row["detail"] = "ready for controlled insert"
            out.append(new_row)
        return out

    def _create_ops_run(self, conn: Any, *, config: RegimeSectorIndustryHistoricalSignalControlledDbWriteConfig, candidate_count: int, insert_count: int, skip_count: int, existing_date_policy: str) -> int:
        now = utc_now()
        run_external_key = f"m4-hist-signal-write-{config.report_date}-{uuid.uuid4().hex[:12]}"
        # ops_run.run_uid is a PostgreSQL uuid column in the V2 schema. Keep the
        # human-readable key in context_json/run_name, and store a canonical UUID
        # in run_uid so controlled writes do not fail before strategy_signal insert.
        run_uid = str(uuid.uuid4())
        context = {
            "stage": HISTORICAL_CONTROLLED_DB_WRITE_STAGE,
            "run_external_key": run_external_key,
            "strategy_code": config.strategy_code,
            "strategy_version_code": config.strategy_version_code,
            "research_backtest_request_id": config.research_backtest_request_id,
            "benchmark_index_code": config.benchmark_index_code,
            "candidate_row_count": candidate_count,
            "planned_insert_row_count": insert_count,
            "planned_skip_row_count": skip_count,
            "existing_date_policy": existing_date_policy,
            "guardrails": ["historical_preview_scope", "skip_existing_date_by_default", "m5_submission_still_separate", "no_backtest_execution", "no_paper_trading"],
        }
        row = conn.execute(
            text(
                """
                insert into ops_run (
                    run_uid, run_name, run_type, status, trigger_type,
                    context_json, requested_at, started_at, ended_at, created_at, updated_at
                ) values (
                    :run_uid, :run_name, :run_type, :status, :trigger_type,
                    cast(:context_json as jsonb), :requested_at, :started_at, :ended_at, :created_at, :updated_at
                ) returning id
                """
            ),
            {
                "run_uid": run_uid,
                "run_name": f"M4 historical signal controlled DB write {config.report_date}",
                "run_type": HISTORICAL_CONTROLLED_DB_WRITE_RUN_TYPE,
                "status": "SUCCESS",
                "trigger_type": "MANUAL",
                "context_json": json.dumps(context, ensure_ascii=False, default=json_default),
                "requested_at": now,
                "started_at": now,
                "ended_at": now,
                "created_at": now,
                "updated_at": now,
            },
        ).mappings().first()
        return int(row["id"])

    def _insert_strategy_signal_rows(self, conn: Any, rows: Sequence[Mapping[str, Any]], *, ops_run_id: int) -> list[dict[str, Any]]:
        inserted: list[dict[str, Any]] = []
        now = utc_now()
        stmt = text(
            """
            insert into strategy_signal (
                strategy_version_id, run_id, subject_type, subject_key, instrument_id,
                signal_role, signal_side, signal_action, as_of_date, effective_date,
                raw_score, normalized_score, confidence_score, rank_in_batch, universe_size,
                reason_code, reason_payload_json, parameter_payload_json, created_at
            ) values (
                :strategy_version_id, :run_id, :subject_type, :subject_key, :instrument_id,
                :signal_role, :signal_side, :signal_action, :as_of_date, :effective_date,
                :raw_score, :normalized_score, :confidence_score, :rank_in_batch, :universe_size,
                :reason_code, cast(:reason_payload_json as jsonb), cast(:parameter_payload_json as jsonb), :created_at
            ) returning id
            """
        )
        for index, row in enumerate(rows, start=1):
            inserted_id = conn.execute(
                stmt,
                {
                    "strategy_version_id": row.get("strategy_version_id"),
                    "run_id": ops_run_id,
                    "subject_type": row.get("subject_type"),
                    "subject_key": row.get("subject_key"),
                    "instrument_id": row.get("instrument_id"),
                    "signal_role": row.get("signal_role"),
                    "signal_side": row.get("signal_side"),
                    "signal_action": row.get("signal_action"),
                    "as_of_date": row.get("as_of_date"),
                    "effective_date": row.get("effective_date"),
                    "raw_score": row.get("raw_score"),
                    "normalized_score": row.get("normalized_score"),
                    "confidence_score": row.get("confidence_score"),
                    "rank_in_batch": row.get("rank_in_batch"),
                    "universe_size": row.get("universe_size"),
                    "reason_code": row.get("reason_code"),
                    "reason_payload_json": json.dumps(row.get("reason_payload_json") or {}, ensure_ascii=False, default=json_default),
                    "parameter_payload_json": json.dumps(row.get("parameter_payload_json") or {}, ensure_ascii=False, default=json_default),
                    "created_at": now,
                },
            ).scalar_one()
            inserted.append(self._write_row_projection(row, ops_run_id=ops_run_id, strategy_signal_id=int(inserted_id), status="INSERTED", sequence=index))
        return inserted

    def _write_row_projection(self, row: Mapping[str, Any], *, ops_run_id: int | None, strategy_signal_id: int | None, status: str | None = None, sequence: int | None = None) -> dict[str, Any]:
        return {
            "write_row_id": f"write:{sequence or 0}:{row.get('db_write_candidate_id')}",
            "db_write_candidate_id": row.get("db_write_candidate_id"),
            "strategy_signal_id": strategy_signal_id,
            "ops_run_id": ops_run_id,
            "strategy_version_id": row.get("strategy_version_id"),
            "as_of_date": row.get("as_of_date"),
            "effective_date": row.get("effective_date"),
            "subject_key": row.get("subject_key"),
            "instrument_id": row.get("instrument_id"),
            "rank_in_batch": row.get("rank_in_batch"),
            "candidate_status": row.get("candidate_status"),
            "write_status": status or row.get("write_status"),
            "detail": row.get("detail"),
        }

    def _build_date_summary(self, rows: Sequence[Mapping[str, Any]], *, existing_by_pair: Mapping[tuple[str, str], int]) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str], dict[str, int]] = {}
        for row in rows:
            pair = (str(row.get("as_of_date")), str(row.get("effective_date")))
            if pair not in grouped:
                grouped[pair] = {"candidate": 0, "inserted": 0, "skipped": 0}
            grouped[pair]["candidate"] += 1
            if row.get("write_status") == "READY_TO_INSERT":
                grouped[pair]["inserted"] += 1
            if str(row.get("write_status", "")).startswith("SKIPPED"):
                grouped[pair]["skipped"] += 1
        out: list[dict[str, Any]] = []
        for pair, counts in sorted(grouped.items()):
            existing = int(existing_by_pair.get(pair, 0))
            status = "WARN" if counts["skipped"] else "PASS"
            out.append(
                {
                    "as_of_date": pair[0],
                    "effective_date": pair[1],
                    "candidate_row_count": counts["candidate"],
                    "inserted_row_count": counts["inserted"],
                    "skipped_existing_row_count": counts["skipped"],
                    "existing_same_version_date_rows_before": existing,
                    "status": status,
                    "detail": "existing rows skipped by policy=skip" if counts["skipped"] else "controlled insert completed for date pair",
                }
            )
        return out

    def _fallback_date_summary(self, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str], int] = {}
        for row in rows:
            pair = (str(row.get("as_of_date")), str(row.get("effective_date")))
            grouped[pair] = grouped.get(pair, 0) + 1
        return [
            {
                "as_of_date": pair[0],
                "effective_date": pair[1],
                "candidate_row_count": count,
                "inserted_row_count": 0,
                "skipped_existing_row_count": 0,
                "existing_same_version_date_rows_before": 0,
                "status": "NOT_RUN",
                "detail": "controlled write did not reach insert planning",
            }
            for pair, count in sorted(grouped.items())
        ]

    def _success_action_items(self, *, inserted_count: int, skipped_count: int) -> list[dict[str, Any]]:
        return [
            self._action("WARN", "m5_still_preview_only", f"Inserted historical strategy_signal rows={inserted_count}; skipped existing rows={skipped_count}.", "Next run M5 historical backtest request write preview; do not execute backtest yet."),
            self._action("WARN", "paper_trading_still_blocked", "M4 historical signal write does not authorize M6 paper trading.", "Keep M6 blocked until M5/M9/M7 gates pass."),
        ]

    def _write_artifacts(
        self,
        output_dir: Path,
        report_date: str,
        result: RegimeSectorIndustryHistoricalSignalControlledDbWriteResult,
        *,
        inserted_rows: Sequence[Mapping[str, Any]],
        skipped_rows: Sequence[Mapping[str, Any]],
    ) -> HistoricalSignalControlledDbWriteArtifacts:
        json_path = output_dir / f"m4_historical_signal_controlled_db_write_{report_date}.json"
        markdown_path = output_dir / f"m4_historical_signal_controlled_db_write_{report_date}.md"
        inserted_rows_path = output_dir / f"m4_historical_signal_controlled_inserted_rows_{report_date}.csv"
        skipped_rows_path = output_dir / f"m4_historical_signal_controlled_skipped_rows_{report_date}.csv"
        date_summary_path = output_dir / f"m4_historical_signal_controlled_date_summary_{report_date}.csv"
        contract_check_path = output_dir / f"m4_historical_signal_controlled_contract_check_{report_date}.csv"
        action_items_path = output_dir / f"m4_historical_signal_controlled_action_items_{report_date}.csv"
        artifact_payload = asdict(result)
        artifact_payload["artifacts"] = None
        json_path.write_text(json.dumps(artifact_payload, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
        markdown_path.write_text(self._build_markdown(result), encoding="utf-8")
        write_csv(inserted_rows_path, inserted_rows, HISTORICAL_CONTROLLED_DB_WRITE_COLUMNS)
        write_csv(skipped_rows_path, skipped_rows, HISTORICAL_CONTROLLED_DB_WRITE_COLUMNS)
        write_csv(date_summary_path, result.date_summary, HISTORICAL_CONTROLLED_DB_WRITE_DATE_SUMMARY_COLUMNS)
        write_csv(contract_check_path, result.contract_check, HISTORICAL_CONTROLLED_DB_WRITE_CONTRACT_CHECK_COLUMNS)
        write_csv(action_items_path, result.action_items, HISTORICAL_CONTROLLED_DB_WRITE_ACTION_COLUMNS)
        return HistoricalSignalControlledDbWriteArtifacts(
            json_path=str(json_path),
            markdown_path=str(markdown_path),
            inserted_rows_csv_path=str(inserted_rows_path),
            skipped_rows_csv_path=str(skipped_rows_path),
            date_summary_csv_path=str(date_summary_path),
            contract_check_csv_path=str(contract_check_path),
            action_items_csv_path=str(action_items_path),
        )

    def _build_markdown(self, result: RegimeSectorIndustryHistoricalSignalControlledDbWriteResult) -> str:
        summary = result.summary
        decision = result.validation_decision
        return "\n".join(
            [
                f"# M4 Historical Signal Controlled DB Write - {result.report_date}",
                "",
                f"- status: `{result.status}`",
                f"- request_id: `{result.research_backtest_request_id}`",
                f"- ops_run_id: `{summary.get('ops_run_id')}`",
                f"- candidate_row_count: `{summary.get('candidate_row_count')}`",
                f"- inserted_row_count: `{summary.get('inserted_row_count')}`",
                f"- skipped_existing_row_count: `{summary.get('skipped_existing_row_count')}`",
                f"- existing_date_policy: `{summary.get('existing_date_policy')}`",
                f"- can_start_m5_historical_backtest_request_write_preview: `{decision.get('can_start_m5_historical_backtest_request_write_preview')}`",
                f"- can_execute_backtest_now: `{decision.get('can_execute_backtest_now')}`",
                f"- can_create_research_backtest_result_now: `{decision.get('can_create_research_backtest_result_now')}`",
                "",
                "## Boundary",
                "",
                "This step writes historical strategy_signal rows only. It does not create M5 requests/results, execute backtests, or route to paper trading.",
            ]
        ) + "\n"

    def _has_value(self, value: Any) -> bool:
        return value is not None and not (isinstance(value, str) and value.strip() == "")

    def _parse_json_object(self, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return dict(value)
        text_value = str(value).strip()
        if not text_value:
            return {}
        parsed = json.loads(text_value)
        if not isinstance(parsed, dict):
            raise ValueError("JSON payload is not an object")
        return parsed

    def _parse_date(self, value: Any) -> date | None:
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

    def _to_decimal(self, value: Any) -> Decimal | None:
        if value is None:
            return None
        text_value = str(value).strip()
        if not text_value:
            return None
        try:
            return Decimal(text_value)
        except Exception:
            return None
