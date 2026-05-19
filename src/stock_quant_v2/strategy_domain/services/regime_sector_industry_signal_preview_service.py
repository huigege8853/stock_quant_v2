"""M4 S3 signal preview artifacts for regime / sector / industry selection.

This module is intentionally artifact-only. It consumes S2 rule-validation
artifacts and emits preview rows shaped like the platform strategy_signal
contract, but it does not insert into strategy_signal, does not create M5
backtest requests, does not touch paper trading, and does not alter risk rules.
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

try:  # SQLAlchemy is optional for pure artifact smoke tests.
    from sqlalchemy import create_engine, text
except Exception:  # pragma: no cover
    create_engine = None  # type: ignore[assignment]
    text = None  # type: ignore[assignment]

STRATEGY_CODE = "regime_sector_industry_selection_v1"
STRATEGY_STAGE = "M4_S3_SIGNAL_PREVIEW"
SOURCE_STAGE = "M4_S2_RULE_VALIDATION"
DEFAULT_REPORT_DIR = Path("artifacts") / "m4" / "strategy_signal_preview"
DEFAULT_S2_ARTIFACT_DIR = Path("artifacts") / "m4" / "strategy_rule_validation"
PREVIEW_SIGNAL_ROLE = "SELECTION"
PREVIEW_SIGNAL_SIDE = "LONG"
PREVIEW_SIGNAL_ACTION = "CANDIDATE"
PREVIEW_SUBJECT_TYPE = "INSTRUMENT"
PREVIEW_WRITE_MODE = "PREVIEW_ARTIFACT_ONLY"
V1_1_SCORE_MODE = "M4_V1_1_CONCEPT_CAPITAL_SCORING_PREVIEW_ONLY"
CONCEPT_TAG_TYPE = "CONCEPT_EM"
CONCEPT_TAXONOMY_SOURCE = "EASTMONEY"
INDUSTRY_TAXONOMY_SOURCE = "SW_2021"

# Concept labels from public vendors often include trading channels, market-state
# tags, style labels, or heat labels. They are useful for observation, but must
# not be treated as theme/mainline strength in M4 v1.1 scoring preview. This
# artifact-only filter is intentionally conservative; filtered names are kept in
# preview outputs for manual review.
GENERIC_CONCEPT_TAG_NAMES: frozenset[str] = frozenset(
    {
        "融资融券", "沪股通", "深股通", "富时罗素", "标普道琼斯A股", "MSCI概念",
        "证金持股", "QFII重仓", "机构重仓", "社保重仓", "基金重仓",
        "百元股", "小盘股", "中盘股", "大盘股", "低价股", "高价股",
        "创业板综", "上证180", "上证380", "深证100R", "中证500", "中证1000", "沪深300",
        "昨日涨停", "昨日连板", "昨日触板", "昨日高振幅", "昨日高换手",
        "近期新高", "百日新高", "历史新高", "东方财富热股", "同花顺热股", "热门股",
        "破净股", "预盈预增", "送转填权", "转债标的", "注册制次新股", "次新股", "ST股",
    }
)
GENERIC_CONCEPT_KEYWORDS: tuple[str, ...] = (
    "融资融券", "沪股通", "深股通", "QFII", "机构重仓", "基金重仓", "社保重仓",
    "百元股", "小盘股", "中盘股", "大盘股", "创业板综", "昨日", "新高", "热股",
    "高振幅", "高换手", "次新股", "ST股",
)
DB_ENV_KEYS = (
    "V2_SQLALCHEMY_URL",
    "STOCK_QUANT_V2_DATABASE_URL",
    "DATABASE_URL",
    "POSTGRES_URL",
    "SQLALCHEMY_DATABASE_URI",
)
DEFAULT_ENV_FILE_CANDIDATES = (".env.research", ".env", ".env.local")

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


def market_regime_display_label(market_regime: Any) -> str:
    return REGIME_DISPLAY_LABELS.get(str(market_regime or "UNKNOWN"), str(market_regime or "UNKNOWN"))


def route_name_for_regime(market_regime: Any) -> str:
    return REGIME_ROUTE_NAMES.get(str(market_regime or "UNKNOWN"), REGIME_ROUTE_NAMES["UNKNOWN"])

REQUIRED_S2_SCORE_COLUMNS = (
    "preview_rank",
    "instrument_id",
    "instrument_code",
    "display_name",
    "industry_tag_code",
    "industry_tag_name",
    "market_regime",
    "feat_industry_strength_20",
    "feat_mom_20",
    "feat_trend_strength_20",
    "feat_volatility_rank_20",
    "feat_tradability_score",
    "feat_tradable_flag",
    "stock_alpha_score",
    "risk_penalty_score",
    "final_preview_score",
    "reason_code",
)

REQUIRED_SIGNAL_COLUMNS = (
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
)

SIGNAL_PREVIEW_COLUMNS = (
    "preview_signal_id",
    "signal_write_mode",
    "strategy_code",
    "strategy_stage",
    "source_stage",
    *REQUIRED_SIGNAL_COLUMNS,
    "instrument_code",
    "display_name",
    "industry_tag_code",
    "industry_tag_name",
    "market_regime",
    "market_regime_display",
    "route_name",
    "reason_summary",
    "source_preview_rank",
    "source_final_preview_score",
    "stock_alpha_score",
    "risk_penalty_score",
    "feat_industry_strength_20",
    "feat_mom_20",
    "feat_trend_strength_20",
    "feat_volatility_rank_20",
    "feat_tradability_score",
    "feat_tradable_flag",
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
    "filtered_generic_concept_count",
    "filtered_generic_concept_names",
    "concept_cleaning_status",
    "sw_l2_names",
    "sw_l3_names",
    "v1_1_preview_score",
    "v1_1_score_delta",
    "cleaned_v1_1_preview_score",
    "cleaned_v1_1_score_delta",
    "v1_1_scoring_mode",
)


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
    text_value = str(value).strip()
    if text_value == "":
        return None
    try:
        return Decimal(text_value)
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


def min_max_normalize(value: Any, *, min_value: Decimal, max_value: Decimal) -> Decimal | None:
    decimal_value = to_decimal(value)
    if decimal_value is None:
        return None
    if max_value == min_value:
        return Decimal("1")
    return quantize((decimal_value - min_value) / (max_value - min_value))


def confidence_score(*, normalized_score: Any, risk_penalty_score_value: Any, tradability_score: Any) -> Decimal | None:
    normalized = clamp_0_1(normalized_score)
    risk = clamp_0_1(risk_penalty_score_value, default=Decimal("0.5"))
    tradability = clamp_0_1(tradability_score, default=Decimal("0.5"))
    if normalized is None:
        return None
    return quantize(Decimal("0.50") * normalized + Decimal("0.30") * tradability + Decimal("0.20") * (Decimal("1") - risk))


def _parse_date(value: Any) -> date | None:
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


def _parse_env_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    if stripped.startswith("export "):
        stripped = stripped[len("export ") :].strip()
    key, value = stripped.split("=", 1)
    key = key.strip()
    value = value.strip()
    if not key:
        return None
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return key, value


def load_env_file(env_file: str | Path | None, *, project_root: Path) -> dict[str, Any]:
    candidates: list[Path] = []
    if env_file:
        path = Path(env_file)
        candidates.append(path if path.is_absolute() else project_root / path)
    else:
        candidates.extend(project_root / name for name in DEFAULT_ENV_FILE_CANDIDATES)

    selected: Path | None = None
    for path in candidates:
        if path.exists():
            selected = path
            break
    if selected is None:
        return {"loaded": False, "path": None, "loaded_keys": [], "skipped_existing_keys": [], "reason": "No env file found or provided."}

    loaded_keys: list[str] = []
    skipped_existing_keys: list[str] = []
    try:
        lines = selected.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception as exc:  # noqa: BLE001
        return {"loaded": False, "path": str(selected), "loaded_keys": [], "skipped_existing_keys": [], "reason": f"Failed to read env file: {exc}"}

    for line in lines:
        parsed = _parse_env_line(line)
        if parsed is None:
            continue
        key, value = parsed
        if key in os.environ and os.environ.get(key):
            skipped_existing_keys.append(key)
            continue
        os.environ[key] = value
        loaded_keys.append(key)
    return {"loaded": True, "path": str(selected), "loaded_keys": loaded_keys, "skipped_existing_keys": skipped_existing_keys, "secret_values_returned": False}


def resolve_database_url(explicit_url: str | None = None) -> tuple[str | None, str | None]:
    if explicit_url:
        return explicit_url, "--database-url"
    for key in DB_ENV_KEYS:
        value = os.environ.get(key)
        if value:
            return value, key
    return None, None


def safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except Exception:
        return None


def safe_float(value: Any) -> float | None:
    decimal_value = to_decimal(value)
    return float(decimal_value) if decimal_value is not None else None


def decimal_to_score(value: Any) -> Decimal | None:
    decimal_value = clamp_0_1(value)
    return quantize(decimal_value) if decimal_value is not None else None


def clamp_score(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    if value < Decimal("0"):
        return Decimal("0")
    if value > Decimal("1"):
        return Decimal("1")
    return quantize(value)


@dataclass(slots=True)
class SignalPreviewConfig:
    report_date: str
    s2_artifact_dir: Path
    output_dir: Path
    effective_date: date | None = None
    max_preview_rows: int | None = None
    strategy_version_ref: str = "regime_sector_industry_selection_v1/S3_PREVIEW"
    project_root: Path = Path(".")
    env_file: str | Path | None = None
    database_url: str | None = None
    enable_v1_1_scoring_preview: bool = True


@dataclass(slots=True)
class SignalPreviewArtifacts:
    json_path: str
    markdown_path: str
    signal_preview_rows_path: str
    signal_schema_check_path: str
    signal_reason_payload_preview_path: str
    signal_preview_action_items_path: str


@dataclass(slots=True)
class SignalPreviewResult:
    status: str
    generated_at: str
    report_date: str
    strategy_code: str
    stage: str
    source_stage: str
    source_s2_status: str | None
    as_of_date: date | None
    effective_date: date | None
    preview_summary: dict[str, Any]
    validation_decision: dict[str, Any]
    schema_check: list[dict[str, Any]]
    action_items: list[dict[str, Any]]
    guardrails: list[str]
    artifacts: SignalPreviewArtifacts | None = None
    signal_preview_rows: list[dict[str, Any]] = field(default_factory=list)
    reason_payload_preview_rows: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self, *, include_rows: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "generated_at": self.generated_at,
            "report_date": self.report_date,
            "strategy_code": self.strategy_code,
            "stage": self.stage,
            "source_stage": self.source_stage,
            "source_s2_status": self.source_s2_status,
            "as_of_date": self.as_of_date,
            "effective_date": self.effective_date,
            "preview_summary": self.preview_summary,
            "validation_decision": self.validation_decision,
            "schema_check": self.schema_check,
            "action_items": self.action_items,
            "guardrails": self.guardrails,
            "artifacts": asdict(self.artifacts) if self.artifacts else None,
        }
        if include_rows:
            payload["signal_preview_rows"] = self.signal_preview_rows
            payload["reason_payload_preview_rows"] = self.reason_payload_preview_rows
        return payload


class RegimeSectorIndustrySignalPreviewService:
    def build_preview(
        self,
        config: SignalPreviewConfig,
        *,
        progress_callback: Callable[[str], None] | None = None,
    ) -> SignalPreviewResult:
        s2_json_path = self._resolve_artifact_path(
            config.s2_artifact_dir,
            exact_name=f"regime_sector_industry_rule_validation_{config.report_date}.json",
            pattern="regime_sector_industry_rule_validation_*.json",
        )
        s2_score_path = self._resolve_artifact_path(
            config.s2_artifact_dir,
            exact_name=f"score_preview_{config.report_date}.csv",
            pattern="score_preview_*.csv",
        )
        if progress_callback:
            progress_callback(f"S2_ARTIFACTS_RESOLVED json={s2_json_path} score_preview={s2_score_path}")

        s2_payload = self._read_json(s2_json_path)
        s2_rows = self._read_csv(s2_score_path)
        if config.max_preview_rows is not None:
            s2_rows = s2_rows[: max(0, config.max_preview_rows)]

        action_items: list[dict[str, Any]] = []
        source_status = str(s2_payload.get("status") or "") if s2_payload else None
        source_decision = s2_payload.get("validation_decision") or {}
        can_start_s3 = bool(source_decision.get("can_start_s3_signal_preview_design"))
        if source_status not in {"PASS", "PASS_WITH_WARN"} or not can_start_s3:
            action_items.append(
                {
                    "severity": "BLOCKER",
                    "item": "s2_gate",
                    "reason": f"S2 gate is not open. status={source_status} can_start_s3={can_start_s3}.",
                    "next_step": "Rerun S2 rule validation and resolve blockers before signal preview.",
                }
            )

        missing_columns = self._missing_score_columns(s2_rows)
        if missing_columns:
            action_items.append(
                {
                    "severity": "BLOCKER",
                    "item": "score_preview_columns",
                    "reason": f"score_preview is missing required columns: {','.join(missing_columns)}.",
                    "next_step": "Regenerate S2 score_preview with the current S2 patch.",
                }
            )

        if not s2_rows:
            action_items.append(
                {
                    "severity": "BLOCKER",
                    "item": "score_preview_rows",
                    "reason": "S2 score_preview has no rows.",
                    "next_step": "Resolve S2 candidate filters before S3 preview.",
                }
            )

        actual_trade_date = _parse_date(s2_payload.get("actual_trade_date")) if s2_payload else None
        effective_date = config.effective_date or actual_trade_date
        if effective_date == actual_trade_date:
            action_items.append(
                {
                    "severity": "WARN",
                    "item": "effective_date_policy",
                    "reason": "effective_date defaults to actual_trade_date in artifact-only preview; it is not a trading-calendar-adjusted next session date.",
                    "next_step": "Before DB signal write, freeze effective_date policy using the platform trading calendar.",
                }
            )

        action_items.extend(self._manual_review_action_items())

        preview_rows = self._build_signal_preview_rows(
            s2_rows,
            s2_payload=s2_payload,
            as_of_date=actual_trade_date,
            effective_date=effective_date,
            strategy_version_ref=config.strategy_version_ref,
        ) if not missing_columns else []

        if progress_callback:
            progress_callback(f"SIGNAL_PREVIEW_ROWS_BUILT rows={len(preview_rows)}")

        enrichment_summary: dict[str, Any] = {"status": "SKIPPED", "reason": "v1_1_scoring_preview_disabled"}
        if preview_rows and config.enable_v1_1_scoring_preview:
            preview_rows, enrichment_summary, enrichment_action_items = self._enrich_v1_1_scoring_preview_rows(
                preview_rows,
                config=config,
                as_of_date=actual_trade_date,
                progress_callback=progress_callback,
            )
            action_items.extend(enrichment_action_items)

        reason_payload_rows = self._build_reason_payload_preview_rows(preview_rows)
        schema_check = self._build_schema_check(preview_rows)
        for row in schema_check:
            if row.get("status") == "FAIL":
                action_items.append(
                    {
                        "severity": "BLOCKER",
                        "item": "signal_schema_check",
                        "reason": f"Preview schema column failed: {row.get('column_name')} issue={row.get('issue')}",
                        "next_step": "Fix S3 preview schema before M4 signal DB-write design.",
                    }
                )

        blocker_count = sum(1 for item in action_items if item.get("severity") == "BLOCKER")
        warn_count = sum(1 for item in action_items if item.get("severity") == "WARN")
        status = "PASS_WITH_WARN" if blocker_count == 0 else "FAIL"
        preview_summary = self._build_preview_summary(preview_rows, s2_payload=s2_payload, enrichment_summary=enrichment_summary)
        validation_decision = {
            "can_start_m4_signal_db_write_design": blocker_count == 0,
            "can_write_strategy_signal_now": False,
            "can_submit_m5_backtest_now": False,
            "manual_review_required": True,
            "blocker_count": blocker_count,
            "warn_count": warn_count,
            "reason": (
                "S3 signal preview artifacts are ready for manual review; DB strategy_signal write remains blocked by stage boundary."
                if blocker_count == 0
                else "S3 signal preview blockers remain. Do not implement DB strategy_signal write."
            ),
        }

        result = SignalPreviewResult(
            status=status,
            generated_at=utc_now_iso(),
            report_date=config.report_date,
            strategy_code=STRATEGY_CODE,
            stage=STRATEGY_STAGE,
            source_stage=SOURCE_STAGE,
            source_s2_status=source_status,
            as_of_date=actual_trade_date,
            effective_date=effective_date,
            preview_summary=preview_summary,
            validation_decision=validation_decision,
            schema_check=schema_check,
            action_items=action_items,
            guardrails=self._guardrails(),
            signal_preview_rows=preview_rows,
            reason_payload_preview_rows=reason_payload_rows,
        )
        return self._write_artifacts(config=config, result=result)

    def _resolve_artifact_path(self, directory: Path, *, exact_name: str, pattern: str) -> Path:
        directory = Path(directory)
        exact_path = directory / exact_name
        if exact_path.exists():
            return exact_path
        candidates = sorted(directory.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
        if candidates:
            return candidates[0]
        raise FileNotFoundError(f"No artifact found in {directory}: {exact_name} or {pattern}")

    def _read_json(self, path: Path) -> dict[str, Any]:
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def _read_csv(self, path: Path) -> list[dict[str, Any]]:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]

    def _missing_score_columns(self, rows: Sequence[Mapping[str, Any]]) -> list[str]:
        if not rows:
            return []
        columns = set(rows[0].keys())
        return [column for column in REQUIRED_S2_SCORE_COLUMNS if column not in columns]

    def _build_signal_preview_rows(
        self,
        rows: Sequence[Mapping[str, Any]],
        *,
        s2_payload: Mapping[str, Any],
        as_of_date: date | None,
        effective_date: date | None,
        strategy_version_ref: str,
    ) -> list[dict[str, Any]]:
        numeric_scores = [to_decimal(row.get("final_preview_score")) for row in rows]
        numeric_scores = [score for score in numeric_scores if score is not None]
        min_score = min(numeric_scores) if numeric_scores else Decimal("0")
        max_score = max(numeric_scores) if numeric_scores else Decimal("0")
        universe_size = int((s2_payload.get("preview_summary") or {}).get("eligible_candidate_count") or len(rows) or 0)
        route_config = s2_payload.get("route_config") or {}
        market_inputs = s2_payload.get("market_inputs") or {}
        preview_rows: list[dict[str, Any]] = []
        for index, row in enumerate(rows, start=1):
            rank = int(to_decimal(row.get("preview_rank")) or index)
            raw_score = quantize(to_decimal(row.get("final_preview_score")))
            normalized = min_max_normalize(raw_score, min_value=min_score, max_value=max_score) if raw_score is not None else None
            confidence = confidence_score(
                normalized_score=normalized,
                risk_penalty_score_value=row.get("risk_penalty_score"),
                tradability_score=row.get("feat_tradability_score"),
            )
            reason_payload = self._build_reason_payload(row, s2_payload=s2_payload, route_config=route_config, market_inputs=market_inputs)
            parameter_payload = self._build_parameter_payload(s2_payload=s2_payload, strategy_version_ref=strategy_version_ref)
            preview_rows.append(
                {
                    "preview_signal_id": f"{STRATEGY_CODE}:{as_of_date or 'UNKNOWN'}:{rank:05d}:{row.get('instrument_code') or row.get('instrument_id')}",
                    "signal_write_mode": PREVIEW_WRITE_MODE,
                    "strategy_code": STRATEGY_CODE,
                    "strategy_stage": STRATEGY_STAGE,
                    "source_stage": SOURCE_STAGE,
                    "run_id": "",
                    "strategy_version_id": "",
                    "as_of_date": as_of_date,
                    "effective_date": effective_date,
                    "subject_type": PREVIEW_SUBJECT_TYPE,
                    "subject_key": row.get("instrument_code") or row.get("instrument_id"),
                    "instrument_id": row.get("instrument_id"),
                    "signal_role": PREVIEW_SIGNAL_ROLE,
                    "signal_side": PREVIEW_SIGNAL_SIDE,
                    "signal_action": PREVIEW_SIGNAL_ACTION,
                    "raw_score": raw_score,
                    "normalized_score": normalized,
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
                    "market_regime": row.get("market_regime"),
                    "market_regime_display": row.get("market_regime_display") or market_regime_display_label(row.get("market_regime") or s2_payload.get("market_regime")),
                    "route_name": row.get("route_name") or route_name_for_regime(row.get("market_regime") or s2_payload.get("market_regime")),
                    "reason_summary": row.get("reason_summary") or self._fallback_reason_summary(row, s2_payload=s2_payload),
                    "source_preview_rank": row.get("preview_rank"),
                    "source_final_preview_score": row.get("final_preview_score"),
                    "stock_alpha_score": row.get("stock_alpha_score"),
                    "risk_penalty_score": row.get("risk_penalty_score"),
                    "feat_industry_strength_20": row.get("feat_industry_strength_20"),
                    "feat_mom_20": row.get("feat_mom_20"),
                    "feat_trend_strength_20": row.get("feat_trend_strength_20"),
                    "feat_volatility_rank_20": row.get("feat_volatility_rank_20"),
                    "feat_tradability_score": row.get("feat_tradability_score"),
                    "feat_tradable_flag": row.get("feat_tradable_flag"),
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
                    "filtered_generic_concept_count": row.get("filtered_generic_concept_count"),
                    "filtered_generic_concept_names": row.get("filtered_generic_concept_names"),
                    "concept_cleaning_status": row.get("concept_cleaning_status"),
                    "sw_l2_names": row.get("sw_l2_names"),
                    "sw_l3_names": row.get("sw_l3_names"),
                    "v1_1_preview_score": row.get("v1_1_preview_score"),
                    "v1_1_score_delta": row.get("v1_1_score_delta"),
                    "cleaned_v1_1_preview_score": row.get("cleaned_v1_1_preview_score"),
                    "cleaned_v1_1_score_delta": row.get("cleaned_v1_1_score_delta"),
                    "v1_1_scoring_mode": row.get("v1_1_scoring_mode"),
                }
            )
        return preview_rows

    def _build_reason_payload(
        self,
        row: Mapping[str, Any],
        *,
        s2_payload: Mapping[str, Any],
        route_config: Mapping[str, Any],
        market_inputs: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "strategy_code": STRATEGY_CODE,
            "source_stage": SOURCE_STAGE,
            "source_reason_code": row.get("reason_code"),
            "market_regime": row.get("market_regime") or s2_payload.get("market_regime"),
            "market_regime_display": row.get("market_regime_display") or market_regime_display_label(row.get("market_regime") or s2_payload.get("market_regime")),
            "route_name": row.get("route_name") or route_name_for_regime(row.get("market_regime") or s2_payload.get("market_regime")),
            "reason_summary": row.get("reason_summary") or self._fallback_reason_summary(row, s2_payload=s2_payload),
            "industry": {
                "tag_code": row.get("industry_tag_code"),
                "tag_name": row.get("industry_tag_name"),
                "strength_20": row.get("feat_industry_strength_20"),
                "ret_20": row.get("feat_industry_ret_20"),
                "breadth_20": row.get("feat_industry_breadth_20"),
            },
            "score_components": {
                "final_preview_score": row.get("final_preview_score"),
                "stock_alpha_score": row.get("stock_alpha_score"),
                "risk_penalty_score": row.get("risk_penalty_score"),
                "mom_20": row.get("feat_mom_20"),
                "trend_strength_20": row.get("feat_trend_strength_20"),
                "volatility_rank_20": row.get("feat_volatility_rank_20"),
                "tradability_score": row.get("feat_tradability_score"),
                "tradable_flag": row.get("feat_tradable_flag"),
                "capital_activity_score": row.get("capital_activity_score"),
                "concept_score": row.get("concept_score"),
                "cleaned_concept_score": row.get("cleaned_concept_score"),
                "v1_1_preview_score": row.get("v1_1_preview_score"),
                "v1_1_score_delta": row.get("v1_1_score_delta"),
                "cleaned_v1_1_preview_score": row.get("cleaned_v1_1_preview_score"),
                "cleaned_v1_1_score_delta": row.get("cleaned_v1_1_score_delta"),
            },
            "route_config": route_config,
            "market_inputs": {
                "benchmark_index_code": market_inputs.get("benchmark_index_code"),
                "benchmark_ret_20": market_inputs.get("benchmark_ret_20"),
                "advancer_ratio": market_inputs.get("advancer_ratio"),
            },
            "concept_strength_enabled": True,
            "concept_domain": {
                "enabled": True,
                "stage": "M4_V1_1_SCORING_PREVIEW_ONLY",
                "scope": "concept and capital activity may affect candidate scoring preview, but not buy/sell timing, M5 submission, M6 routing, or live trading.",
                "concept_count": row.get("concept_count"),
                "concept_score": row.get("concept_score"),
                "concept_names": row.get("concept_names"),
                "concept_top_drivers_json": row.get("concept_top_drivers_json"),
                "cleaned_concept_score": row.get("cleaned_concept_score"),
                "cleaned_concept_names": row.get("cleaned_concept_names"),
                "cleaned_concept_top_drivers_json": row.get("cleaned_concept_top_drivers_json"),
                "filtered_generic_concept_names": row.get("filtered_generic_concept_names"),
                "concept_cleaning_status": row.get("concept_cleaning_status"),
                "capital_activity_score": row.get("capital_activity_score"),
                "capital_activity_status": row.get("capital_activity_status"),
                "pct_change": row.get("pct_change"),
                "amount": row.get("amount"),
                "volume": row.get("volume"),
                "turnover_rate": row.get("turnover_rate"),
            },
            "research_production_boundary": {
                "research_use": "M4 preview and M5 backtest only until strategy promotion is approved.",
                "production_use": "Production may consume only a released strategy_version after M5/M7 gates pass.",
            },
            "preview_only": True,
        }

    def _fallback_reason_summary(self, row: Mapping[str, Any], *, s2_payload: Mapping[str, Any]) -> str:
        market_regime = row.get("market_regime") or s2_payload.get("market_regime")
        display_regime = market_regime_display_label(market_regime)
        route_name = route_name_for_regime(market_regime)
        industry = row.get("industry_tag_name") or row.get("industry_tag_code") or "UNKNOWN"
        return (
            f"市场状态={display_regime}（内部码={market_regime or 'UNKNOWN'}），采用{route_name}；"
            f"行业={industry}，行业强度20日={row.get('feat_industry_strength_20') or 'NA'}；"
            f"个股最终评分={row.get('final_preview_score') or 'NA'}；"
            f"v1.1预览评分={row.get('v1_1_preview_score') or 'NA'}；"
            f"概念数={row.get('concept_count') or 'NA'}，资金活跃度={row.get('capital_activity_score') or 'NA'}。"
        )

    def _build_parameter_payload(self, *, s2_payload: Mapping[str, Any], strategy_version_ref: str) -> dict[str, Any]:
        return {
            "strategy_version_ref": strategy_version_ref,
            "source_s2_report_date": s2_payload.get("report_date"),
            "source_s2_status": s2_payload.get("status"),
            "route_config": s2_payload.get("route_config") or {},
            "formula_refs": {
                "stock_alpha_score": "0.40*feat_mom_20 + 0.30*feat_trend_strength_20 + 0.20*feat_tradability_score + 0.10*(1-feat_volatility_rank_20)",
                "risk_penalty_score": "0.70*feat_volatility_rank_20 + 0.30*(1-feat_tradability_score)",
                "final_preview_score": "route.industry_strength_weight*feat_industry_strength_20 + route.stock_alpha_weight*stock_alpha_score - route.risk_penalty_weight*risk_penalty_score",
                "v1_1_preview_score": "clamp(0.70*normalized_score + 0.15*concept_score + 0.15*capital_activity_score - observation_penalty, 0, 1)",
                "cleaned_v1_1_preview_score": "clamp(0.70*normalized_score + 0.15*cleaned_concept_score + 0.15*capital_activity_score - observation_penalty, 0, 1)",
            },
            "industry_tag_type": "SW_INDUSTRY_L2",
            "concept_strength_enabled": True,
            "concept_strength_scope": "M4 scoring preview only; not buy/sell decision and not production signal write.",
            "write_mode": PREVIEW_WRITE_MODE,
        }

    def _enrich_v1_1_scoring_preview_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        config: SignalPreviewConfig,
        as_of_date: date | None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
        """Add concept + capital activity scoring-preview fields to S3 rows.

        This is still artifact-only. It reads production/research DB inputs and
        writes only additional preview columns. It does not mutate DB rows and
        does not change the existing S2/S3 base score used for stage gates.
        """

        action_items: list[dict[str, Any]] = []
        if create_engine is None or text is None:
            return rows, {"status": "SKIPPED", "reason": "sqlalchemy_unavailable"}, [
                {
                    "severity": "WARN",
                    "item": "v1_1_scoring_preview_db_enrichment",
                    "reason": "SQLAlchemy is unavailable; concept/capital preview fields were not enriched.",
                    "next_step": "Run inside the project runtime with SQLAlchemy installed.",
                }
            ]

        project_root = Path(config.project_root or ".").resolve()
        env_metadata = load_env_file(config.env_file, project_root=project_root)
        database_url, database_url_source = resolve_database_url(config.database_url)
        if not database_url:
            return rows, {
                "status": "SKIPPED",
                "reason": "database_url_missing",
                "env_file": env_metadata,
            }, [
                {
                    "severity": "WARN",
                    "item": "v1_1_scoring_preview_db_enrichment",
                    "reason": "No database URL was found. Existing S3 artifacts were generated without concept/capital enrichment.",
                    "next_step": "Set V2_SQLALCHEMY_URL or STOCK_QUANT_V2_DATABASE_URL and rerun S3 preview.",
                }
            ]

        if as_of_date is None:
            return rows, {"status": "SKIPPED", "reason": "as_of_date_missing"}, [
                {
                    "severity": "WARN",
                    "item": "v1_1_scoring_preview_db_enrichment",
                    "reason": "S2 actual_trade_date is missing, so DB enrichment cannot select latest core_daily_bar rows.",
                    "next_step": "Rerun S2 rule validation after M3/M4 readiness passes.",
                }
            ]

        instrument_ids = sorted({safe_int(row.get("instrument_id")) for row in rows if safe_int(row.get("instrument_id")) is not None})
        if not instrument_ids:
            return rows, {"status": "SKIPPED", "reason": "no_instrument_ids"}, [
                {
                    "severity": "WARN",
                    "item": "v1_1_scoring_preview_db_enrichment",
                    "reason": "S3 preview rows do not contain valid instrument_id values.",
                    "next_step": "Regenerate S2 score_preview with instrument_id.",
                }
            ]

        engine = create_engine(database_url)
        try:
            with engine.connect() as conn:
                market_rows = self._load_market_enrichment(conn, as_of_date=as_of_date, instrument_ids=instrument_ids)
                tag_rows = self._load_tag_enrichment(conn, as_of_date=as_of_date, instrument_ids=instrument_ids)
        except Exception as exc:  # noqa: BLE001
            return rows, {"status": "WARN", "reason": "db_enrichment_failed", "error": str(exc)}, [
                {
                    "severity": "WARN",
                    "item": "v1_1_scoring_preview_db_enrichment",
                    "reason": f"DB read-only enrichment failed: {exc}",
                    "next_step": "Inspect database URL/schema and rerun S3 preview.",
                }
            ]
        finally:
            engine.dispose()

        if progress_callback:
            progress_callback(f"V1_1_ENRICHMENT_LOADED market_rows={len(market_rows)} tag_rows={len(tag_rows)}")

        market_by_instrument = {int(row["instrument_id"]): row for row in market_rows if row.get("instrument_id") is not None}
        tag_by_instrument = self._aggregate_tag_enrichment(tag_rows)

        enriched_count = 0
        concept_score_count = 0
        cleaned_concept_score_count = 0
        filtered_generic_concept_row_count = 0
        capital_score_count = 0
        st_penalty_count = 0
        for row in rows:
            instrument_id = safe_int(row.get("instrument_id"))
            market = market_by_instrument.get(instrument_id or -1, {})
            tags = tag_by_instrument.get(instrument_id or -1, {})
            if market or tags:
                enriched_count += 1

            self._apply_market_enrichment(row, market)
            self._apply_tag_enrichment(row, tags)

            concept_score = to_decimal(row.get("concept_score"))
            cleaned_concept_score = to_decimal(row.get("cleaned_concept_score"))
            capital_score = to_decimal(row.get("capital_activity_score"))
            if concept_score is not None:
                concept_score_count += 1
            if cleaned_concept_score is not None:
                cleaned_concept_score_count += 1
            if safe_int(row.get("filtered_generic_concept_count")):
                filtered_generic_concept_row_count += 1
            if capital_score is not None:
                capital_score_count += 1

            observation_penalty = self._observation_penalty(row)
            if observation_penalty > 0:
                st_penalty_count += 1
            base = to_decimal(row.get("normalized_score"))
            if base is not None and concept_score is not None and capital_score is not None:
                v1_1_score = clamp_score(
                    Decimal("0.70") * base
                    + Decimal("0.15") * concept_score
                    + Decimal("0.15") * capital_score
                    - observation_penalty
                )
                row["v1_1_preview_score"] = v1_1_score
                row["v1_1_score_delta"] = quantize(v1_1_score - base) if v1_1_score is not None else None
            else:
                row["v1_1_preview_score"] = None
                row["v1_1_score_delta"] = None

            if base is not None and cleaned_concept_score is not None and capital_score is not None:
                cleaned_v1_1_score = clamp_score(
                    Decimal("0.70") * base
                    + Decimal("0.15") * cleaned_concept_score
                    + Decimal("0.15") * capital_score
                    - observation_penalty
                )
                row["cleaned_v1_1_preview_score"] = cleaned_v1_1_score
                row["cleaned_v1_1_score_delta"] = quantize(cleaned_v1_1_score - base) if cleaned_v1_1_score is not None else None
            else:
                row["cleaned_v1_1_preview_score"] = None
                row["cleaned_v1_1_score_delta"] = None
            row["v1_1_scoring_mode"] = V1_1_SCORE_MODE

            # Rebuild reason payload after enrichment so the JSON includes v1.1 fields.
            try:
                payload = json.loads(str(row.get("reason_payload_json") or "{}"))
            except Exception:
                payload = {}
            payload["concept_domain"] = {
                "enabled": True,
                "stage": "M4_V1_1_SCORING_PREVIEW_ONLY",
                "scope": "concept/capital affects candidate scoring preview only; not buy/sell timing or production signal write.",
                "concept_count": row.get("concept_count"),
                "concept_score": row.get("concept_score"),
                "concept_names": row.get("concept_names"),
                "concept_top_drivers_json": row.get("concept_top_drivers_json"),
                "cleaned_concept_score": row.get("cleaned_concept_score"),
                "cleaned_concept_names": row.get("cleaned_concept_names"),
                "cleaned_concept_top_drivers_json": row.get("cleaned_concept_top_drivers_json"),
                "filtered_generic_concept_names": row.get("filtered_generic_concept_names"),
                "concept_cleaning_status": row.get("concept_cleaning_status"),
                "capital_activity_score": row.get("capital_activity_score"),
                "capital_activity_status": row.get("capital_activity_status"),
                "pct_change": row.get("pct_change"),
                "amount": row.get("amount"),
                "volume": row.get("volume"),
                "turnover_rate": row.get("turnover_rate"),
                "v1_1_preview_score": row.get("v1_1_preview_score"),
                "v1_1_score_delta": row.get("v1_1_score_delta"),
            }
            payload["score_components"] = dict(payload.get("score_components") or {})
            payload["score_components"].update(
                {
                    "concept_score": row.get("concept_score"),
                    "cleaned_concept_score": row.get("cleaned_concept_score"),
                    "capital_activity_score": row.get("capital_activity_score"),
                    "v1_1_preview_score": row.get("v1_1_preview_score"),
                    "v1_1_score_delta": row.get("v1_1_score_delta"),
                    "cleaned_v1_1_preview_score": row.get("cleaned_v1_1_preview_score"),
                    "cleaned_v1_1_score_delta": row.get("cleaned_v1_1_score_delta"),
                }
            )
            row["reason_payload_json"] = json.dumps(payload, ensure_ascii=False, default=json_default, sort_keys=True)
            row["reason_summary"] = self._v1_1_reason_summary(row)

        summary = {
            "status": "PASS_WITH_WARN",
            "database_url_source": database_url_source,
            "env_file": env_metadata,
            "requested_instrument_count": len(instrument_ids),
            "enriched_row_count": enriched_count,
            "concept_score_count": concept_score_count,
            "cleaned_concept_score_count": cleaned_concept_score_count,
            "filtered_generic_concept_row_count": filtered_generic_concept_row_count,
            "capital_activity_score_count": capital_score_count,
            "observation_penalty_count": st_penalty_count,
            "formula": "clamp(0.70*normalized_score + 0.15*concept_score + 0.15*capital_activity_score - observation_penalty, 0, 1)",
            "cleaned_formula": "clamp(0.70*normalized_score + 0.15*cleaned_concept_score + 0.15*capital_activity_score - observation_penalty, 0, 1)",
            "concept_cleaning_scope": "Generic/channel/state/style tags are filtered out of cleaned_concept_score but preserved in filtered_generic_concept_names for manual review.",
            "scope": "artifact-only M4 v1.1 scoring preview; no strategy_signal write, no M5, no M6, no buy/sell decision.",
        }
        if concept_score_count == 0 or capital_score_count == 0:
            action_items.append(
                {
                    "severity": "WARN",
                    "item": "v1_1_scoring_preview_coverage",
                    "reason": f"Concept/capital enrichment is partial. concept_score_count={concept_score_count} capital_score_count={capital_score_count} rows={len(rows)}.",
                    "next_step": "Check core_daily_bar pct/amount/turnover_rate and CONCEPT_EM mapping coverage before using v1.1 score for ranking review.",
                }
            )
        else:
            action_items.append(
                {
                    "severity": "WARN",
                    "item": "v1_1_scoring_preview_boundary",
                    "reason": "Concept/capital fields were enriched successfully, but this remains artifact-only scoring preview.",
                    "next_step": "Review score deltas manually. Do not promote to DB signal write without a separate acceptance stage.",
                }
            )
        return rows, summary, action_items

    def _load_market_enrichment(self, conn: Any, *, as_of_date: date, instrument_ids: Sequence[int]) -> list[dict[str, Any]]:
        id_list = ",".join(str(int(value)) for value in instrument_ids)
        sql = f"""
with universe as (
  select
    b.instrument_id,
    b.trade_date,
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
)
select *
from capital
where instrument_id in ({id_list})
"""
        result = conn.execute(text(sql), {"as_of_date": as_of_date})
        return [dict(row._mapping) for row in result]

    def _load_tag_enrichment(self, conn: Any, *, as_of_date: date, instrument_ids: Sequence[int]) -> list[dict[str, Any]]:
        id_list = ",".join(str(int(value)) for value in instrument_ids)
        sql = f"""
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
    case
      when ar.amount_pct_rank is null or vr.volume_pct_rank is null or tr.turnover_rate_pct_rank is null then null
      else ((ar.amount_pct_rank + vr.volume_pct_rank + tr.turnover_rate_pct_rank) / 3.0)
    end as capital_activity_score
  from universe u
  left join amount_rank ar on ar.instrument_id = u.instrument_id
  left join volume_rank vr on vr.instrument_id = u.instrument_id
  left join turnover_rank tr on tr.instrument_id = u.instrument_id
),
concept_edges as (
  select
    it.instrument_id,
    t.id as tag_id,
    t.tag_name
  from public.instrument_tag it
  join public.tag t on t.id = it.tag_id
  where t.tag_type = :concept_tag_type
    and t.taxonomy_source = :concept_taxonomy_source
    and it.effective_from <= :as_of_date
    and (it.effective_to is null or it.effective_to >= :as_of_date)
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
  join capital c on c.instrument_id = ce.instrument_id
  group by ce.tag_id, ce.tag_name
),
concept_stats as (
  select
    csr.*,
    percent_rank() over (order by csr.concept_avg_pct_change) as concept_pct_change_rank,
    percent_rank() over (order by csr.concept_stock_count) as concept_coverage_rank,
    case
      when csr.concept_avg_capital_activity_score is null
        or csr.concept_positive_ratio is null
        or csr.concept_avg_pct_change is null
      then null
      else (
        0.40 * coalesce(csr.concept_avg_capital_activity_score, 0)
        + 0.30 * coalesce(csr.concept_positive_ratio, 0)
        + 0.20 * coalesce(percent_rank() over (order by csr.concept_avg_pct_change), 0)
        + 0.10 * coalesce(percent_rank() over (order by csr.concept_stock_count), 0)
      )
    end as concept_hot_score
  from concept_stats_raw csr
),
target_tags as (
  select
    it.instrument_id,
    t.tag_type,
    t.taxonomy_source,
    t.tag_name,
    cs.concept_stock_count,
    cs.concept_avg_capital_activity_score,
    cs.concept_avg_pct_change,
    cs.concept_positive_ratio,
    cs.concept_hot_score
  from public.instrument_tag it
  join public.tag t on t.id = it.tag_id
  left join concept_stats cs on cs.tag_id = t.id
  where it.instrument_id in ({id_list})
    and it.effective_from <= :as_of_date
    and (it.effective_to is null or it.effective_to >= :as_of_date)
    and (
      (t.tag_type = :concept_tag_type and t.taxonomy_source = :concept_taxonomy_source)
      or (t.tag_type in ('SW_INDUSTRY_L2', 'SW_INDUSTRY_L3') and t.taxonomy_source = :industry_taxonomy_source)
    )
)
select *
from target_tags
order by instrument_id, tag_type, concept_hot_score desc nulls last, tag_name
"""
        params = {
            "as_of_date": as_of_date,
            "concept_tag_type": CONCEPT_TAG_TYPE,
            "concept_taxonomy_source": CONCEPT_TAXONOMY_SOURCE,
            "industry_taxonomy_source": INDUSTRY_TAXONOMY_SOURCE,
        }
        result = conn.execute(text(sql), params)
        return [dict(row._mapping) for row in result]

    def _aggregate_tag_enrichment(self, rows: Sequence[Mapping[str, Any]]) -> dict[int, dict[str, Any]]:
        grouped: dict[int, dict[str, Any]] = {}
        for row in rows:
            instrument_id = safe_int(row.get("instrument_id"))
            if instrument_id is None:
                continue
            item = grouped.setdefault(instrument_id, {"concepts": [], "sw_l2": [], "sw_l3": []})
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
            elif tag_type == "SW_INDUSTRY_L2":
                if tag_name not in item["sw_l2"]:
                    item["sw_l2"].append(tag_name)
            elif tag_type == "SW_INDUSTRY_L3":
                if tag_name not in item["sw_l3"]:
                    item["sw_l3"].append(tag_name)
        return grouped

    def _apply_market_enrichment(self, row: dict[str, Any], market: Mapping[str, Any]) -> None:
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
            if value is not None:
                decimal_value = to_decimal(value)
                row[key] = quantize(decimal_value) if decimal_value is not None else value
            else:
                row[key] = None
        row["capital_activity_status"] = "READY_FOR_M4_SCORING_PREVIEW" if row.get("capital_activity_score") is not None else "MISSING_OR_NOT_TRADABLE"

    def _apply_tag_enrichment(self, row: dict[str, Any], tags: Mapping[str, Any]) -> None:
        concepts = list(tags.get("concepts") or [])
        concepts.sort(key=lambda item: (item.get("concept_hot_score") is None, -(item.get("concept_hot_score") or 0), item.get("concept_name") or ""))
        cleaned_concepts: list[dict[str, Any]] = []
        filtered_generic_concepts: list[dict[str, Any]] = []
        for concept in concepts:
            concept_name = str(concept.get("concept_name") or "").strip()
            if self._is_generic_concept_tag(concept_name):
                filtered_generic_concepts.append(concept)
            else:
                cleaned_concepts.append(concept)

        top_concepts = concepts[:5]
        cleaned_top_concepts = cleaned_concepts[:5]
        scores = [to_decimal(item.get("concept_hot_score")) for item in top_concepts]
        scores = [score for score in scores if score is not None]
        cleaned_scores = [to_decimal(item.get("concept_hot_score")) for item in cleaned_top_concepts]
        cleaned_scores = [score for score in cleaned_scores if score is not None]

        row["concept_count"] = len(concepts)
        row["concept_names"] = ",".join(item.get("concept_name") or "" for item in concepts[:20])
        row["concept_top_drivers_json"] = json.dumps(top_concepts, ensure_ascii=False, default=json_default)
        row["concept_score"] = quantize(sum(scores) / Decimal(len(scores))) if scores else None
        row["concept_status"] = "READY_FOR_M4_SCORING_PREVIEW" if scores else "NO_CONCEPT_SCORE"

        row["cleaned_concept_count"] = len(cleaned_concepts)
        row["cleaned_concept_names"] = ",".join(item.get("concept_name") or "" for item in cleaned_concepts[:20])
        row["cleaned_concept_top_drivers_json"] = json.dumps(cleaned_top_concepts, ensure_ascii=False, default=json_default)
        if cleaned_scores:
            row["cleaned_concept_score"] = quantize(sum(cleaned_scores) / Decimal(len(cleaned_scores)))
            row["cleaned_concept_status"] = "READY_FOR_M4_CLEANED_SCORING_PREVIEW"
        elif concepts:
            # Generic/channel/state-only labels should contribute zero theme strength,
            # not NULL. Keeping a numeric zero lets cleaned_v1_1_preview_score remain
            # comparable while filtered_generic_concept_names preserves review evidence.
            row["cleaned_concept_score"] = Decimal("0")
            row["cleaned_concept_status"] = "GENERIC_ONLY_ZERO_THEME_SCORE"
        else:
            row["cleaned_concept_score"] = None
            row["cleaned_concept_status"] = "NO_CONCEPT_TAGS"
        row["filtered_generic_concept_count"] = len(filtered_generic_concepts)
        row["filtered_generic_concept_names"] = ",".join(item.get("concept_name") or "" for item in filtered_generic_concepts[:20])
        if concepts and filtered_generic_concepts and cleaned_concepts:
            row["concept_cleaning_status"] = "FILTERED_GENERIC_AND_RETAINED_THEME"
        elif concepts and filtered_generic_concepts and not cleaned_concepts:
            row["concept_cleaning_status"] = "FILTERED_GENERIC_ONLY"
        elif concepts:
            row["concept_cleaning_status"] = "NO_GENERIC_FILTERED"
        else:
            row["concept_cleaning_status"] = "NO_CONCEPT_TAGS"

        row["sw_l2_names"] = ",".join(tags.get("sw_l2") or [])
        row["sw_l3_names"] = ",".join(tags.get("sw_l3") or [])

    def _is_generic_concept_tag(self, tag_name: str) -> bool:
        normalized = str(tag_name or "").strip()
        if not normalized:
            return False
        if normalized in GENERIC_CONCEPT_TAG_NAMES:
            return True
        return any(keyword in normalized for keyword in GENERIC_CONCEPT_KEYWORDS)

    def _observation_penalty(self, row: Mapping[str, Any]) -> Decimal:
        penalty = Decimal("0")
        display_name = str(row.get("display_name") or "")
        concept_names = str(row.get("concept_names") or "")
        if "ST" in display_name.upper() or "ST股" in concept_names:
            penalty += Decimal("0.35")
        if row.get("capital_activity_score") is None:
            penalty += Decimal("0.10")
        pct_change = to_decimal(row.get("pct_change"))
        if pct_change is not None and (pct_change >= Decimal("20") or pct_change <= Decimal("-20")):
            penalty += Decimal("0.05")
        return penalty

    def _v1_1_reason_summary(self, row: Mapping[str, Any]) -> str:
        base_summary = str(row.get("reason_summary") or "").strip()
        if not base_summary:
            base_summary = self._fallback_reason_summary(row, s2_payload={})
        def _score_text(value: Any) -> Any:
            return "NA" if value is None else value

        return (
            f"{base_summary} v1.1预览：concept_score={_score_text(row.get('concept_score'))}，"
            f"cleaned_concept_score={_score_text(row.get('cleaned_concept_score'))}，"
            f"capital_activity_score={_score_text(row.get('capital_activity_score'))}，"
            f"v1_1_preview_score={_score_text(row.get('v1_1_preview_score'))}，"
            f"cleaned_v1_1_preview_score={_score_text(row.get('cleaned_v1_1_preview_score'))}。"
            "概念/资金活跃度仅进入选股评分预览，不进入买卖点、M5提交、M6晋级或实盘；"
            "cleaned_concept_score 已剔除泛化/通道/状态类标签，仅用于研究评审。"
        )

    def _build_reason_payload_preview_rows(self, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        payload_rows: list[dict[str, Any]] = []
        for row in rows:
            payload_rows.append(
                {
                    "preview_signal_id": row.get("preview_signal_id"),
                    "instrument_code": row.get("instrument_code"),
                    "display_name": row.get("display_name"),
                    "reason_code": row.get("reason_code"),
                    "reason_summary": row.get("reason_summary"),
                    "reason_payload_json": row.get("reason_payload_json"),
                }
            )
        return payload_rows

    def _build_schema_check(self, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        if rows:
            preview_columns = set(rows[0].keys())
        else:
            preview_columns = set(SIGNAL_PREVIEW_COLUMNS)
        check_rows: list[dict[str, Any]] = []
        for column in REQUIRED_SIGNAL_COLUMNS:
            has_column = column in preview_columns
            non_empty_count = sum(1 for row in rows if str(row.get(column) or "").strip()) if rows else 0
            status = "PASS"
            issue = None
            if not has_column:
                status = "FAIL"
                issue = "missing_preview_column"
            elif column in {"run_id", "strategy_version_id"}:
                status = "WARN"
                issue = "preview_placeholder_resolved_only_during_db_write"
            elif rows and non_empty_count == 0:
                status = "FAIL"
                issue = "all_values_empty"
            check_rows.append(
                {
                    "column_name": column,
                    "required_by_strategy_signal": True,
                    "preview_has_column": has_column,
                    "non_empty_count": non_empty_count,
                    "row_count": len(rows),
                    "status": status,
                    "issue": issue,
                }
            )
        return check_rows

    def _build_preview_summary(self, rows: Sequence[Mapping[str, Any]], *, s2_payload: Mapping[str, Any], enrichment_summary: Mapping[str, Any] | None = None) -> dict[str, Any]:
        reason_counts: dict[str, int] = {}
        industry_counts: dict[str, int] = {}
        raw_scores: list[Decimal] = []
        confidence_scores: list[Decimal] = []
        v1_1_scores: list[Decimal] = []
        cleaned_v1_1_scores: list[Decimal] = []
        concept_scores: list[Decimal] = []
        cleaned_concept_scores: list[Decimal] = []
        filtered_generic_concept_row_count = 0
        capital_scores: list[Decimal] = []
        for row in rows:
            reason = str(row.get("reason_code") or "UNKNOWN")
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
            industry = str(row.get("industry_tag_name") or row.get("industry_tag_code") or "UNKNOWN")
            industry_counts[industry] = industry_counts.get(industry, 0) + 1
            raw = to_decimal(row.get("raw_score"))
            confidence = to_decimal(row.get("confidence_score"))
            if raw is not None:
                raw_scores.append(raw)
            if confidence is not None:
                confidence_scores.append(confidence)
            v1_1 = to_decimal(row.get("v1_1_preview_score"))
            cleaned_v1_1 = to_decimal(row.get("cleaned_v1_1_preview_score"))
            concept = to_decimal(row.get("concept_score"))
            cleaned_concept = to_decimal(row.get("cleaned_concept_score"))
            capital = to_decimal(row.get("capital_activity_score"))
            if v1_1 is not None:
                v1_1_scores.append(v1_1)
            if cleaned_v1_1 is not None:
                cleaned_v1_1_scores.append(cleaned_v1_1)
            if concept is not None:
                concept_scores.append(concept)
            if cleaned_concept is not None:
                cleaned_concept_scores.append(cleaned_concept)
            if safe_int(row.get("filtered_generic_concept_count")):
                filtered_generic_concept_row_count += 1
            if capital is not None:
                capital_scores.append(capital)
        top_industries = [
            {"industry": industry, "preview_count": count}
            for industry, count in sorted(industry_counts.items(), key=lambda item: (-item[1], item[0]))[:20]
        ]
        return {
            "source_s2_status": s2_payload.get("status"),
            "source_s2_actual_trade_date": s2_payload.get("actual_trade_date"),
            "signal_preview_row_count": len(rows),
            "source_preview_row_count": (s2_payload.get("preview_summary") or {}).get("preview_row_count"),
            "source_eligible_candidate_count": (s2_payload.get("preview_summary") or {}).get("eligible_candidate_count"),
            "max_raw_score": max(raw_scores) if raw_scores else None,
            "min_raw_score": min(raw_scores) if raw_scores else None,
            "max_confidence_score": max(confidence_scores) if confidence_scores else None,
            "min_confidence_score": min(confidence_scores) if confidence_scores else None,
            "reason_code_counts": reason_counts,
            "top_preview_industries": top_industries,
            "signal_write_mode": PREVIEW_WRITE_MODE,
            "v1_1_scoring_mode": V1_1_SCORE_MODE,
            "v1_1_enrichment_summary": dict(enrichment_summary or {}),
            "v1_1_score_nonnull_count": len(v1_1_scores),
            "cleaned_v1_1_score_nonnull_count": len(cleaned_v1_1_scores),
            "concept_score_nonnull_count": len(concept_scores),
            "cleaned_concept_score_nonnull_count": len(cleaned_concept_scores),
            "filtered_generic_concept_row_count": filtered_generic_concept_row_count,
            "capital_activity_score_nonnull_count": len(capital_scores),
            "max_v1_1_preview_score": max(v1_1_scores) if v1_1_scores else None,
            "min_v1_1_preview_score": min(v1_1_scores) if v1_1_scores else None,
            "max_cleaned_v1_1_preview_score": max(cleaned_v1_1_scores) if cleaned_v1_1_scores else None,
            "min_cleaned_v1_1_preview_score": min(cleaned_v1_1_scores) if cleaned_v1_1_scores else None,
            "max_concept_score": max(concept_scores) if concept_scores else None,
            "min_concept_score": min(concept_scores) if concept_scores else None,
            "max_cleaned_concept_score": max(cleaned_concept_scores) if cleaned_concept_scores else None,
            "min_cleaned_concept_score": min(cleaned_concept_scores) if cleaned_concept_scores else None,
            "max_capital_activity_score": max(capital_scores) if capital_scores else None,
            "min_capital_activity_score": min(capital_scores) if capital_scores else None,
        }

    def _manual_review_action_items(self) -> list[dict[str, Any]]:
        return [
            {
                "severity": "WARN",
                "item": "db_identity_fields",
                "reason": "run_id and strategy_version_id are intentionally blank in artifact-only preview.",
                "next_step": "Resolve concrete strategy_version_id and ops_run in the later DB-write patch only after S3 review.",
            },
            {
                "severity": "WARN",
                "item": "risk_penalty_formula",
                "reason": "S3 inherits the S2 candidate risk penalty formula; it is not yet frozen as production parameter schema.",
                "next_step": "Manual review before implementing strategy_signal DB write.",
            },
            {
                "severity": "WARN",
                "item": "concept_capital_scoring_preview",
                "reason": "CONCEPT_EM mapping and capital activity proxy are included only as M4 v1.1 scoring-preview fields.",
                "next_step": "Review v1_1_preview_score deltas manually; do not connect this preview to buy/sell, M5, M6, or live trading until later gates pass.",
            },
            {
                "severity": "WARN",
                "item": "concept_tag_cleaning_preview",
                "reason": "cleaned_concept_score filters generic/channel/state/style labels from concept scoring but keeps filtered_generic_concept_names for review.",
                "next_step": "Review cleaned_v1_1_preview_score and top30 changes before M5 validation; this is still artifact-only.",
            },
            {
                "severity": "WARN",
                "item": "stage_boundary",
                "reason": "This task emits preview artifacts only and intentionally does not write strategy_signal.",
                "next_step": "Review artifacts before starting the M4 signal DB-write design patch.",
            },
        ]

    def _guardrails(self) -> list[str]:
        return [
            "artifact_only",
            "no_strategy_signal_write",
            "no_m5_backtest_submit",
            "no_paper_trading",
            "no_risk_rule_change",
            "concept_capital_scoring_preview_only",
            "concept_cleaning_preview_only",
            "concept_capital_not_buy_sell_decision",
            "requires_manual_review_before_db_write",
        ]

    def _write_artifacts(self, *, config: SignalPreviewConfig, result: SignalPreviewResult) -> SignalPreviewResult:
        output_dir = Path(config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        suffix = config.report_date
        json_path = output_dir / f"regime_sector_industry_signal_preview_{suffix}.json"
        md_path = output_dir / f"regime_sector_industry_signal_preview_{suffix}.md"
        preview_path = output_dir / f"signal_preview_rows_{suffix}.csv"
        schema_path = output_dir / f"signal_schema_check_{suffix}.csv"
        reason_path = output_dir / f"signal_reason_payload_preview_{suffix}.csv"
        action_path = output_dir / f"signal_preview_action_items_{suffix}.csv"

        result.artifacts = SignalPreviewArtifacts(
            json_path=str(json_path),
            markdown_path=str(md_path),
            signal_preview_rows_path=str(preview_path),
            signal_schema_check_path=str(schema_path),
            signal_reason_payload_preview_path=str(reason_path),
            signal_preview_action_items_path=str(action_path),
        )
        json_path.write_text(json.dumps(result.to_dict(include_rows=False), ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
        md_path.write_text(self._render_markdown(result), encoding="utf-8")
        self._write_csv(preview_path, result.signal_preview_rows, fieldnames=SIGNAL_PREVIEW_COLUMNS)
        self._write_csv(schema_path, result.schema_check)
        self._write_csv(reason_path, result.reason_payload_preview_rows)
        self._write_csv(action_path, result.action_items)
        return result

    def _render_markdown(self, result: SignalPreviewResult) -> str:
        decision = result.validation_decision
        summary = result.preview_summary
        lines = [
            f"# M4 S3 Signal Preview - {result.strategy_code}",
            "",
            f"- status: `{result.status}`",
            f"- report_date: `{result.report_date}`",
            f"- source_s2_status: `{result.source_s2_status}`",
            f"- as_of_date: `{result.as_of_date}`",
            f"- effective_date: `{result.effective_date}`",
            f"- signal_write_mode: `{summary.get('signal_write_mode')}`",
            f"- can_start_m4_signal_db_write_design: `{decision.get('can_start_m4_signal_db_write_design')}`",
            f"- can_write_strategy_signal_now: `{decision.get('can_write_strategy_signal_now')}`",
            f"- can_submit_m5_backtest_now: `{decision.get('can_submit_m5_backtest_now')}`",
            "",
            "## Preview summary",
            "",
            f"- signal_preview_row_count: `{summary.get('signal_preview_row_count')}`",
            f"- source_eligible_candidate_count: `{summary.get('source_eligible_candidate_count')}`",
            f"- max_raw_score: `{summary.get('max_raw_score')}`",
            f"- min_raw_score: `{summary.get('min_raw_score')}`",
            f"- max_confidence_score: `{summary.get('max_confidence_score')}`",
            f"- min_confidence_score: `{summary.get('min_confidence_score')}`",
            f"- v1_1_score_nonnull_count: `{summary.get('v1_1_score_nonnull_count')}`",
            f"- concept_score_nonnull_count: `{summary.get('concept_score_nonnull_count')}`",
            f"- capital_activity_score_nonnull_count: `{summary.get('capital_activity_score_nonnull_count')}`",
            f"- max_v1_1_preview_score: `{summary.get('max_v1_1_preview_score')}`",
            f"- min_v1_1_preview_score: `{summary.get('min_v1_1_preview_score')}`",
            f"- cleaned_v1_1_score_nonnull_count: `{summary.get('cleaned_v1_1_score_nonnull_count')}`",
            f"- cleaned_concept_score_nonnull_count: `{summary.get('cleaned_concept_score_nonnull_count')}`",
            f"- filtered_generic_concept_row_count: `{summary.get('filtered_generic_concept_row_count')}`",
            f"- max_cleaned_v1_1_preview_score: `{summary.get('max_cleaned_v1_1_preview_score')}`",
            f"- min_cleaned_v1_1_preview_score: `{summary.get('min_cleaned_v1_1_preview_score')}`",
            "",
            "## Guardrails",
            "",
        ]
        for guardrail in result.guardrails:
            lines.append(f"- {guardrail}")
        lines.extend(["", "## Action items", ""])
        for item in result.action_items:
            lines.append(f"- `{item.get('severity')}` **{item.get('item')}**: {item.get('reason')} Next: {item.get('next_step')}")
        lines.extend(
            [
                "",
                "## Contract note",
                "",
                "This S3 artifact previews rows shaped like the platform strategy_signal contract. It intentionally leaves DB-owned identifiers blank and does not insert rows into strategy_signal.",
            ]
        )
        return "\n".join(lines) + "\n"

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
