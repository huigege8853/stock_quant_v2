"""Contract adapter and guarded DB writer for M4 regime/sector/industry signals.

This service consumes the S3 preview artifact produced by
``bootstrap_m4_regime_sector_industry_signal_preview_s3`` and converts it into
rows shaped for ``public.strategy_signal``.

Default behavior is contract dry-run only. It writes artifacts and does not
insert into the database unless ``write_db=True`` and the explicit confirmation
string is supplied.
"""

from __future__ import annotations

import csv
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Engine

STRATEGY_CODE = "regime_sector_industry_selection_v1"
DEFAULT_STRATEGY_VERSION_CODE = "v1"
STAGE = "M4_SIGNAL_PREVIEW_DB_WRITE_CONTRACT"
SOURCE_STAGE = "M4_S3_SIGNAL_PREVIEW"
DEFAULT_PREVIEW_ARTIFACT_DIR = Path("artifacts") / "m4" / "strategy_signal_preview_v1_1"
DEFAULT_OUTPUT_DIR = Path("artifacts") / "m4" / "strategy_signal_db_write_contract"
WRITE_MODE_DRY_RUN = "CONTRACT_DRY_RUN_ONLY"
WRITE_MODE_DB = "PREVIEW_SCOPE_DB_WRITE"
REQUIRED_WRITE_CONFIRMATION = "PREVIEW_SCOPE_ONLY"
RUN_TYPE = "M4_SIGNAL_PREVIEW_WRITE"
TRIGGER_TYPE = "MANUAL"

PREVIEW_REQUIRED_COLUMNS = (
    "preview_signal_id",
    "strategy_code",
    "as_of_date",
    "instrument_id",
    "rank_in_batch",
    "universe_size",
    "reason_code",
    "reason_payload_json",
    "parameter_payload_json",
)

DB_RESULT_ROW_COLUMNS = (
    "write_row_id",
    "strategy_signal_id",
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
    "instrument_code",
    "display_name",
    "source_preview_signal_id",
    "source_preview_rank",
    "source_raw_score",
    "source_normalized_score",
    "source_confidence_score",
    "source_v1_1_preview_score",
    "source_v1_1_scoring_mode",
    "write_mode",
)


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
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        return None
    text_value = str(value).strip()
    if not text_value:
        return None
    try:
        return date.fromisoformat(text_value[:10])
    except ValueError:
        return None


def to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    text_value = str(value).strip()
    if not text_value:
        return None
    try:
        return Decimal(text_value)
    except (InvalidOperation, ValueError):
        return None


def quantize_8(value: Any) -> Decimal | None:
    decimal_value = to_decimal(value)
    if decimal_value is None:
        return None
    return decimal_value.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)


def safe_int(value: Any) -> int | None:
    if value is None:
        return None
    text_value = str(value).strip()
    if not text_value:
        return None
    try:
        return int(Decimal(text_value))
    except (InvalidOperation, ValueError):
        return None


def parse_json_object(value: Any) -> dict[str, Any]:
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


def has_value(value: Any) -> bool:
    return value is not None and not (isinstance(value, str) and value.strip() == "")


@dataclass(slots=True)
class SignalPreviewDbWriteContractConfig:
    report_date: str
    preview_artifact_dir: Path = DEFAULT_PREVIEW_ARTIFACT_DIR
    output_dir: Path = DEFAULT_OUTPUT_DIR
    strategy_code: str = STRATEGY_CODE
    strategy_version_code: str = DEFAULT_STRATEGY_VERSION_CODE
    effective_date: date | None = None
    write_db: bool = False
    write_confirmation: str = ""
    allow_existing_same_version_date: bool = False
    max_rows: int | None = None


@dataclass(slots=True)
class SignalPreviewDbWriteArtifacts:
    json_path: str
    markdown_path: str
    candidate_rows_path: str
    result_rows_path: str
    contract_check_path: str
    action_items_path: str
    run_summary_path: str


@dataclass(slots=True)
class SignalPreviewDbWriteContractResult:
    status: str
    generated_at: str
    report_date: str
    strategy_code: str
    strategy_version_code: str
    stage: str
    source_stage: str
    source_preview_status: str | None
    as_of_date: date | None
    effective_date: date | None
    run_id: int | None
    run_uid: str | None
    summary: dict[str, Any]
    validation_decision: dict[str, Any]
    contract_check: list[dict[str, Any]]
    action_items: list[dict[str, Any]]
    guardrails: list[str]
    artifacts: SignalPreviewDbWriteArtifacts | None = None
    candidate_rows: list[dict[str, Any]] = field(default_factory=list)
    result_rows: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self, *, include_rows: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "generated_at": self.generated_at,
            "report_date": self.report_date,
            "strategy_code": self.strategy_code,
            "strategy_version_code": self.strategy_version_code,
            "stage": self.stage,
            "source_stage": self.source_stage,
            "source_preview_status": self.source_preview_status,
            "as_of_date": self.as_of_date,
            "effective_date": self.effective_date,
            "run_id": self.run_id,
            "run_uid": self.run_uid,
            "summary": self.summary,
            "validation_decision": self.validation_decision,
            "contract_check": self.contract_check,
            "action_items": self.action_items,
            "guardrails": self.guardrails,
            "artifacts": asdict(self.artifacts) if self.artifacts else None,
        }
        if include_rows:
            payload["candidate_rows"] = self.candidate_rows
            payload["result_rows"] = self.result_rows
        return payload


class RegimeSectorIndustrySignalPreviewDbWriteService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def build_contract_or_write(
        self,
        config: SignalPreviewDbWriteContractConfig,
        *,
        progress_callback: Callable[[str], None] | None = None,
    ) -> SignalPreviewDbWriteContractResult:
        preview_json_path = self._resolve_artifact_path(
            config.preview_artifact_dir,
            exact_name=f"regime_sector_industry_signal_preview_{config.report_date}.json",
            pattern="regime_sector_industry_signal_preview_*.json",
        )
        preview_rows_path = self._resolve_artifact_path(
            config.preview_artifact_dir,
            exact_name=f"signal_preview_rows_{config.report_date}.csv",
            pattern="signal_preview_rows_*.csv",
        )
        if progress_callback:
            progress_callback(f"PREVIEW_ARTIFACTS_RESOLVED json={preview_json_path} rows={preview_rows_path}")

        preview_payload = self._read_json(preview_json_path)
        preview_rows = self._read_csv(preview_rows_path)
        if config.max_rows is not None:
            preview_rows = preview_rows[: max(0, int(config.max_rows))]

        contract_check: list[dict[str, Any]] = []
        action_items: list[dict[str, Any]] = []

        source_status = str(preview_payload.get("status") or "") if preview_payload else None
        preview_decision = preview_payload.get("validation_decision") or {}
        preview_summary = preview_payload.get("preview_summary") or {}
        source_blocker_count = int(preview_decision.get("blocker_count") or 0)
        source_can_start_write = bool(preview_decision.get("can_start_m4_signal_db_write_design"))
        source_row_count = int(preview_summary.get("signal_preview_row_count") or len(preview_rows) or 0)

        contract_check.append(self._check("source_preview_status", "PASS" if source_status in {"PASS", "PASS_WITH_WARN"} else "FAIL", f"status={source_status}", rows=source_row_count))
        contract_check.append(self._check("source_preview_blockers", "PASS" if source_blocker_count == 0 else "FAIL", f"blocker_count={source_blocker_count}", rows=source_row_count))
        contract_check.append(self._check("source_write_gate", "PASS" if source_can_start_write else "FAIL", f"can_start_m4_signal_db_write_design={source_can_start_write}", rows=source_row_count))
        contract_check.append(self._check("source_preview_rows", "PASS" if preview_rows else "FAIL", f"preview_rows={len(preview_rows)}", rows=len(preview_rows)))

        if config.write_db and config.write_confirmation != REQUIRED_WRITE_CONFIRMATION:
            action_items.append(
                self._action(
                    "BLOCKER",
                    "write_confirmation",
                    f"DB write requested but confirmation is not {REQUIRED_WRITE_CONFIRMATION}.",
                    f"Rerun with --write-db --write-confirmation {REQUIRED_WRITE_CONFIRMATION} only after dry-run review.",
                )
            )

        strategy_version_id: int | None = None
        strategy_version_status: str | None = None
        strategy_definition_id: int | None = None
        existing_count = 0
        run_id: int | None = None
        run_uid_value: str | None = None
        inserted_rows: list[dict[str, Any]] = []
        table_columns: dict[str, set[str]] = {}

        with self.engine.connect() as conn:
            table_columns = self._load_table_columns(conn)
            contract_check.extend(self._db_contract_checks(table_columns))
            version_row = self._resolve_strategy_version(
                conn,
                strategy_code=config.strategy_code,
                strategy_version_code=config.strategy_version_code,
            )
            if version_row is None:
                contract_check.append(self._check("strategy_version_resolution", "FAIL", f"missing={config.strategy_code}/{config.strategy_version_code}", rows=0))
                action_items.append(
                    self._action(
                        "BLOCKER",
                        "strategy_version_resolution",
                        f"Strategy version not found: {config.strategy_code}/{config.strategy_version_code}.",
                        "Run/verify M4 strategy metadata seed before DB write. This patch does not create metadata.",
                    )
                )
            else:
                strategy_version_id = int(version_row["strategy_version_id"])
                strategy_definition_id = int(version_row["strategy_definition_id"])
                strategy_version_status = str(version_row.get("lifecycle_status") or "")
                contract_check.append(
                    self._check(
                        "strategy_version_resolution",
                        "PASS",
                        f"strategy_definition_id={strategy_definition_id}; strategy_version_id={strategy_version_id}; lifecycle_status={strategy_version_status}; is_current={version_row.get('is_current')}",
                        rows=1,
                    )
                )

        candidate_rows, candidate_checks = self._prepare_candidate_rows(
            preview_rows,
            preview_payload=preview_payload,
            strategy_version_id=strategy_version_id,
            effective_date_override=config.effective_date,
        )
        contract_check.extend(candidate_checks)

        as_of_dates = sorted({row["as_of_date"] for row in candidate_rows if row.get("as_of_date") is not None})
        effective_dates = sorted({row["effective_date"] for row in candidate_rows if row.get("effective_date") is not None})
        as_of_date = as_of_dates[0] if len(as_of_dates) == 1 else None
        effective_date = effective_dates[0] if len(effective_dates) == 1 else None
        if len(as_of_dates) != 1:
            contract_check.append(self._check("as_of_date_singleton", "FAIL", f"as_of_dates={as_of_dates}", rows=len(candidate_rows)))
        if len(effective_dates) != 1:
            contract_check.append(self._check("effective_date_singleton", "FAIL", f"effective_dates={effective_dates}", rows=len(candidate_rows)))

        with self.engine.connect() as conn:
            existing_instruments = self._load_existing_instrument_ids(conn, [row["instrument_id"] for row in candidate_rows if row.get("instrument_id") is not None])
            missing_instruments = sorted({row["instrument_id"] for row in candidate_rows if row.get("instrument_id") is not None and row["instrument_id"] not in existing_instruments})
            contract_check.append(self._check("instrument_resolution", "PASS" if not missing_instruments else "FAIL", f"missing_instrument_count={len(missing_instruments)}", rows=len(candidate_rows)))
            if missing_instruments:
                action_items.append(self._action("BLOCKER", "instrument_resolution", f"Missing instrument_id values: {missing_instruments[:10]}", "Regenerate S3 preview after instrument metadata is fixed."))

            if strategy_version_id is not None and as_of_date is not None:
                existing_count = self._load_existing_signal_count(conn, strategy_version_id=strategy_version_id, as_of_date=as_of_date, effective_date=effective_date)
            existing_status = "WARN" if existing_count > 0 else "PASS"
            contract_check.append(
                self._check(
                    "existing_signal_rows_same_version_date",
                    existing_status,
                    f"existing_rows={existing_count}; allow_existing_same_version_date={config.allow_existing_same_version_date}",
                    rows=existing_count,
                )
            )
            if existing_count > 0 and not config.allow_existing_same_version_date:
                action_items.append(
                    self._action(
                        "BLOCKER",
                        "existing_signal_rows_same_version_date",
                        "Rows already exist for the same strategy_version/as_of_date/effective_date. Append is blocked by default.",
                        "Review existing runs; rerun with --allow-existing-same-version-date only if append-new-run is intentional.",
                    )
                )

        blocker_count = self._blocker_count(action_items, contract_check)
        write_mode = WRITE_MODE_DB if config.write_db else WRITE_MODE_DRY_RUN
        if blocker_count == 0 and config.write_db:
            if progress_callback:
                progress_callback(f"DB_WRITE_START rows={len(candidate_rows)} strategy_version_id={strategy_version_id}")
            run_id, run_uid_value, inserted_rows = self._insert_preview_scope_rows(
                candidate_rows,
                report_date=config.report_date,
                strategy_code=config.strategy_code,
                strategy_version_code=config.strategy_version_code,
                preview_payload=preview_payload,
                progress_callback=progress_callback,
            )
            contract_check.append(self._check("ops_run_created", "PASS", f"run_id={run_id} run_uid={run_uid_value}", rows=1))
            contract_check.append(self._check("strategy_signal_inserted", "PASS", f"inserted_rows={len(inserted_rows)}", rows=len(inserted_rows)))
            action_items.extend(self._post_write_action_items())
        elif blocker_count == 0:
            contract_check.append(self._check("write_boundary", "PASS", "dry-run only; no strategy_signal rows inserted", rows=0))
            action_items.extend(self._dry_run_action_items())
        else:
            contract_check.append(self._check("write_boundary", "PASS", "blockers detected; no strategy_signal rows inserted", rows=0))

        final_blocker_count = self._blocker_count(action_items, contract_check)
        warn_count = self._warn_count(action_items, contract_check)
        result_rows = self._build_result_rows(inserted_rows, run_id=run_id, fallback_rows=candidate_rows if not config.write_db else [])
        summary = self._build_summary(
            preview_payload=preview_payload,
            candidate_rows=candidate_rows,
            inserted_rows=result_rows if config.write_db else [],
            run_id=run_id,
            run_uid=run_uid_value,
            existing_signal_rows_before_write=existing_count,
            write_mode=write_mode,
        )
        status = "FAIL" if final_blocker_count > 0 else "PASS_WITH_WARN"
        validation_decision = {
            "can_write_strategy_signal_now": (final_blocker_count == 0 and not config.write_db),
            "can_start_m5_backtest_design": (final_blocker_count == 0 and config.write_db and bool(run_id)),
            "can_submit_m5_backtest_now": False,
            "can_route_to_paper_trading_now": False,
            "manual_review_required": True,
            "blocker_count": final_blocker_count,
            "warn_count": warn_count,
            "reason": self._decision_reason(final_blocker_count=final_blocker_count, write_db=config.write_db, run_id=run_id),
        }
        result = SignalPreviewDbWriteContractResult(
            status=status,
            generated_at=utc_now_iso(),
            report_date=config.report_date,
            strategy_code=config.strategy_code,
            strategy_version_code=config.strategy_version_code,
            stage=STAGE,
            source_stage=SOURCE_STAGE,
            source_preview_status=source_status,
            as_of_date=as_of_date,
            effective_date=effective_date,
            run_id=run_id,
            run_uid=run_uid_value,
            summary=summary,
            validation_decision=validation_decision,
            contract_check=contract_check,
            action_items=action_items,
            guardrails=self._guardrails(write_db=config.write_db),
            candidate_rows=candidate_rows,
            result_rows=result_rows,
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

    def _prepare_candidate_rows(
        self,
        preview_rows: Sequence[Mapping[str, Any]],
        *,
        preview_payload: Mapping[str, Any],
        strategy_version_id: int | None,
        effective_date_override: date | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        checks: list[dict[str, Any]] = []
        prepared: list[dict[str, Any]] = []
        missing_columns = self._missing_columns(preview_rows, PREVIEW_REQUIRED_COLUMNS)
        checks.append(self._check("preview_required_columns", "PASS" if not missing_columns else "FAIL", f"missing_columns={missing_columns}", rows=len(preview_rows)))
        if missing_columns:
            return [], checks

        empty_counts: dict[str, int] = {column: 0 for column in PREVIEW_REQUIRED_COLUMNS}
        json_errors = 0
        score_missing = 0
        score_out_of_bounds = 0
        duplicate_key_count = 0
        seen_keys: set[tuple[Any, ...]] = set()
        report_date = parse_date(preview_payload.get("report_date"))
        preview_summary = preview_payload.get("preview_summary") or {}
        source_s2_actual_trade_date = parse_date(preview_summary.get("source_s2_actual_trade_date"))

        for row in preview_rows:
            for column in PREVIEW_REQUIRED_COLUMNS:
                if not has_value(row.get(column)):
                    empty_counts[column] += 1
            try:
                reason_payload = parse_json_object(row.get("reason_payload_json"))
                parameter_payload = parse_json_object(row.get("parameter_payload_json"))
            except Exception:
                json_errors += 1
                reason_payload = {}
                parameter_payload = {}

            as_of_date = parse_date(row.get("as_of_date")) or source_s2_actual_trade_date
            effective_date = self._resolve_effective_date(
                as_of_date=as_of_date,
                row_effective_date=parse_date(row.get("effective_date")),
                report_date=report_date,
                override=effective_date_override,
            )
            instrument_id = safe_int(row.get("instrument_id"))
            rank_in_batch = safe_int(row.get("rank_in_batch"))
            universe_size = safe_int(row.get("universe_size"))
            source_raw_score = quantize_8(row.get("raw_score"))
            source_normalized_score = quantize_8(row.get("normalized_score"))
            source_confidence_score = quantize_8(row.get("confidence_score"))
            v1_1_score = quantize_8(row.get("v1_1_preview_score"))
            db_score = v1_1_score if v1_1_score is not None else source_normalized_score
            if db_score is None:
                score_missing += 1
            elif db_score < Decimal("0") or db_score > Decimal("1"):
                score_out_of_bounds += 1

            subject_type = "instrument"
            subject_key = f"instrument:{instrument_id}" if instrument_id is not None else ""
            signal_action = "select"
            unique_key = (strategy_version_id, as_of_date, subject_key, signal_action)
            if unique_key in seen_keys:
                duplicate_key_count += 1
            seen_keys.add(unique_key)

            reason_payload.update(
                {
                    "db_write_scope": "preview_scope_candidate",
                    "preview_scope_db_write": True,
                    "source_preview_signal_id": row.get("preview_signal_id"),
                    "source_preview_rank": row.get("rank_in_batch"),
                    "score_written_to_db": "v1_1_preview_score" if v1_1_score is not None else "normalized_score",
                    "source_raw_score": json_default(source_raw_score),
                    "source_normalized_score": json_default(source_normalized_score),
                    "source_confidence_score": json_default(source_confidence_score),
                    "source_v1_1_preview_score": json_default(v1_1_score),
                    "m5_submission_allowed": False,
                    "paper_trading_allowed": False,
                }
            )
            parameter_payload.update(
                {
                    "write_mode": WRITE_MODE_DB,
                    "preview_scope_db_write": True,
                    "score_written_to_db": "v1_1_preview_score" if v1_1_score is not None else "normalized_score",
                    "m5_submission_allowed": False,
                    "paper_trading_allowed": False,
                }
            )
            prepared.append(
                {
                    "source_preview_signal_id": row.get("preview_signal_id"),
                    "strategy_version_id": strategy_version_id,
                    "as_of_date": as_of_date,
                    "effective_date": effective_date,
                    "subject_type": subject_type,
                    "subject_key": subject_key,
                    "instrument_id": instrument_id,
                    "signal_role": "selection",
                    "signal_side": "long",
                    "signal_action": signal_action,
                    "raw_score": db_score,
                    "normalized_score": db_score,
                    "confidence_score": source_confidence_score if source_confidence_score is not None else db_score,
                    "rank_in_batch": rank_in_batch,
                    "universe_size": universe_size,
                    "reason_code": str(row.get("reason_code") or "M4_V1_1_SELECTED")[:64],
                    "reason_payload_json": json.dumps(reason_payload, ensure_ascii=False, sort_keys=True, default=json_default),
                    "parameter_payload_json": json.dumps(parameter_payload, ensure_ascii=False, sort_keys=True, default=json_default),
                    "instrument_code": row.get("instrument_code"),
                    "display_name": row.get("display_name"),
                    "source_preview_rank": row.get("rank_in_batch"),
                    "source_raw_score": source_raw_score,
                    "source_normalized_score": source_normalized_score,
                    "source_confidence_score": source_confidence_score,
                    "source_v1_1_preview_score": v1_1_score,
                    "source_v1_1_scoring_mode": row.get("v1_1_scoring_mode"),
                    "write_mode": WRITE_MODE_DB,
                }
            )

        empty_failures = {column: count for column, count in empty_counts.items() if count > 0}
        required_value_failures = dict(empty_failures)
        if strategy_version_id is None:
            required_value_failures["strategy_version_id"] = len(preview_rows)
        if score_missing:
            required_value_failures["db_score"] = score_missing
        checks.append(self._check("candidate_row_count", "PASS" if prepared else "FAIL", f"candidate_rows={len(prepared)}", rows=len(prepared)))
        checks.append(self._check("required_candidate_values", "PASS" if not required_value_failures else "FAIL", f"empty_counts={required_value_failures}", rows=len(prepared)))
        checks.append(self._check("candidate_json_payloads", "PASS" if json_errors == 0 else "FAIL", f"json_errors={json_errors}", rows=len(prepared)))
        checks.append(self._check("candidate_score_bounds", "PASS" if score_out_of_bounds == 0 else "FAIL", f"score_out_of_bounds={score_out_of_bounds}", rows=len(prepared)))
        checks.append(self._check("candidate_unique_keys", "PASS" if duplicate_key_count == 0 else "FAIL", f"duplicate_key_count={duplicate_key_count}", rows=len(prepared)))
        return prepared, checks

    def _resolve_effective_date(
        self,
        *,
        as_of_date: date | None,
        row_effective_date: date | None,
        report_date: date | None,
        override: date | None,
    ) -> date | None:
        if override is not None:
            return override
        if as_of_date is not None and report_date is not None and report_date > as_of_date:
            return report_date
        return row_effective_date or report_date or as_of_date

    def _missing_columns(self, rows: Sequence[Mapping[str, Any]], required_columns: Sequence[str]) -> list[str]:
        if not rows:
            return []
        columns = set(rows[0].keys())
        return [column for column in required_columns if column not in columns]

    def _load_table_columns(self, conn) -> dict[str, set[str]]:
        rows = conn.execute(
            text(
                """
                select table_name, column_name
                from information_schema.columns
                where table_schema = 'public'
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
        ops_required = ("run_uid", "run_type", "run_name", "status", "trigger_type", "requested_at", "started_at", "ended_at", "context_json", "created_at", "updated_at")
        signal_missing = [column for column in signal_required if column not in table_columns.get("strategy_signal", set())]
        ops_missing = [column for column in ops_required if column not in table_columns.get("ops_run", set())]
        checks.append(self._check("strategy_signal_required_columns", "PASS" if not signal_missing else "FAIL", f"missing={signal_missing}", rows=0))
        checks.append(self._check("ops_run_required_columns", "PASS" if not ops_missing else "FAIL", f"missing={ops_missing}", rows=0))
        return checks

    def _resolve_strategy_version(self, conn, *, strategy_code: str, strategy_version_code: str) -> dict[str, Any] | None:
        row = conn.execute(
            text(
                """
                select
                    sd.id as strategy_definition_id,
                    sd.strategy_code,
                    sv.id as strategy_version_id,
                    sv.version_code,
                    sv.lifecycle_status,
                    sv.is_current
                from strategy_definition sd
                join strategy_version sv on sv.strategy_definition_id = sd.id
                where sd.strategy_code = :strategy_code
                  and sv.version_code = :strategy_version_code
                order by sv.is_current desc, sv.id desc
                limit 1
                """
            ),
            {"strategy_code": strategy_code, "strategy_version_code": strategy_version_code},
        ).mappings().first()
        return dict(row) if row is not None else None

    def _load_existing_instrument_ids(self, conn, instrument_ids: Sequence[int]) -> set[int]:
        ids = sorted({int(value) for value in instrument_ids if value is not None})
        if not ids:
            return set()
        stmt = text("select id from meta_instrument where id in :ids").bindparams(bindparam("ids", expanding=True))
        rows = conn.execute(stmt, {"ids": ids}).mappings().all()
        return {int(row["id"]) for row in rows}

    def _load_existing_signal_count(self, conn, *, strategy_version_id: int, as_of_date: date, effective_date: date | None) -> int:
        filters = "strategy_version_id = :strategy_version_id and as_of_date = :as_of_date"
        params: dict[str, Any] = {"strategy_version_id": strategy_version_id, "as_of_date": as_of_date}
        if effective_date is not None:
            filters += " and effective_date = :effective_date"
            params["effective_date"] = effective_date
        return int(conn.execute(text(f"select count(*) from strategy_signal where {filters}"), params).scalar_one())

    def _insert_preview_scope_rows(
        self,
        rows: Sequence[Mapping[str, Any]],
        *,
        report_date: str,
        strategy_code: str,
        strategy_version_code: str,
        preview_payload: Mapping[str, Any],
        progress_callback: Callable[[str], None] | None,
    ) -> tuple[int, str, list[dict[str, Any]]]:
        now = utc_now()
        run_uid_value = str(uuid.uuid4())
        run_name = f"{strategy_code}:{strategy_version_code}:preview_signal_write:{report_date}"
        context_json = {
            "stage": STAGE,
            "source_stage": SOURCE_STAGE,
            "write_mode": WRITE_MODE_DB,
            "strategy_code": strategy_code,
            "strategy_version_code": strategy_version_code,
            "report_date": report_date,
            "source_preview_status": preview_payload.get("status"),
            "candidate_row_count": len(rows),
            "score_written_to_db": "v1_1_preview_score",
            "m5_submission_allowed": False,
            "paper_trading_allowed": False,
        }
        inserted_rows: list[dict[str, Any]] = []
        with self.engine.begin() as conn:
            run_id = int(
                conn.execute(
                    text(
                        """
                        insert into ops_run (
                            run_uid, run_type, run_name, status, trigger_type,
                            requested_at, started_at, context_json, created_at, updated_at
                        ) values (
                            cast(:run_uid as uuid), :run_type, :run_name, :status, :trigger_type,
                            :requested_at, :started_at, cast(:context_json as jsonb), :created_at, :updated_at
                        )
                        returning id
                        """
                    ),
                    {
                        "run_uid": run_uid_value,
                        "run_type": RUN_TYPE,
                        "run_name": run_name[:128],
                        "status": "RUNNING",
                        "trigger_type": TRIGGER_TYPE,
                        "requested_at": now,
                        "started_at": now,
                        "context_json": json.dumps(context_json, ensure_ascii=False, default=json_default),
                        "created_at": now,
                        "updated_at": now,
                    },
                ).scalar_one()
            )
            insert_stmt = text(
                """
                insert into strategy_signal (
                    run_id, strategy_version_id, as_of_date, effective_date,
                    subject_type, subject_key, instrument_id,
                    signal_role, signal_side, signal_action,
                    raw_score, normalized_score, confidence_score,
                    rank_in_batch, universe_size, reason_code,
                    reason_payload_json, parameter_payload_json,
                    published_at, created_at
                ) values (
                    :run_id, :strategy_version_id, :as_of_date, :effective_date,
                    :subject_type, :subject_key, :instrument_id,
                    :signal_role, :signal_side, :signal_action,
                    :raw_score, :normalized_score, :confidence_score,
                    :rank_in_batch, :universe_size, :reason_code,
                    cast(:reason_payload_json as jsonb), cast(:parameter_payload_json as jsonb),
                    :published_at, :created_at
                )
                returning id
                """
            )
            for index, row in enumerate(rows, start=1):
                params = {
                    "run_id": run_id,
                    "strategy_version_id": row.get("strategy_version_id"),
                    "as_of_date": row.get("as_of_date"),
                    "effective_date": row.get("effective_date"),
                    "subject_type": row.get("subject_type"),
                    "subject_key": row.get("subject_key"),
                    "instrument_id": row.get("instrument_id"),
                    "signal_role": row.get("signal_role"),
                    "signal_side": row.get("signal_side"),
                    "signal_action": row.get("signal_action"),
                    "raw_score": row.get("raw_score"),
                    "normalized_score": row.get("normalized_score"),
                    "confidence_score": row.get("confidence_score"),
                    "rank_in_batch": row.get("rank_in_batch"),
                    "universe_size": row.get("universe_size"),
                    "reason_code": row.get("reason_code"),
                    "reason_payload_json": row.get("reason_payload_json"),
                    "parameter_payload_json": row.get("parameter_payload_json"),
                    "published_at": now,
                    "created_at": now,
                }
                signal_id = int(conn.execute(insert_stmt, params).scalar_one())
                inserted = dict(row)
                inserted["strategy_signal_id"] = signal_id
                inserted["run_id"] = run_id
                inserted_rows.append(inserted)
                if progress_callback and (index == len(rows) or index % 50 == 0):
                    progress_callback(f"DB_WRITE_PROGRESS inserted={index}/{len(rows)} run_id={run_id}")
            conn.execute(
                text(
                    """
                    update ops_run
                    set status = :status,
                        ended_at = :ended_at,
                        updated_at = :updated_at
                    where id = :run_id
                    """
                ),
                {"status": "SUCCESS", "ended_at": utc_now(), "updated_at": utc_now(), "run_id": run_id},
            )
        return run_id, run_uid_value, inserted_rows

    def _build_result_rows(
        self,
        inserted_rows: Sequence[Mapping[str, Any]],
        *,
        run_id: int | None,
        fallback_rows: Sequence[Mapping[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        source_rows = list(inserted_rows) if inserted_rows else list(fallback_rows or [])
        result_rows: list[dict[str, Any]] = []
        for index, row in enumerate(source_rows, start=1):
            result_rows.append(
                {
                    "write_row_id": f"{row.get('strategy_version_id')}:{row.get('as_of_date')}:{index:05d}:{row.get('instrument_id')}",
                    "strategy_signal_id": row.get("strategy_signal_id"),
                    "run_id": row.get("run_id") or run_id,
                    "strategy_version_id": row.get("strategy_version_id"),
                    "as_of_date": row.get("as_of_date"),
                    "effective_date": row.get("effective_date"),
                    "subject_type": row.get("subject_type"),
                    "subject_key": row.get("subject_key"),
                    "instrument_id": row.get("instrument_id"),
                    "signal_role": row.get("signal_role"),
                    "signal_side": row.get("signal_side"),
                    "signal_action": row.get("signal_action"),
                    "raw_score": row.get("raw_score"),
                    "normalized_score": row.get("normalized_score"),
                    "confidence_score": row.get("confidence_score"),
                    "rank_in_batch": row.get("rank_in_batch"),
                    "universe_size": row.get("universe_size"),
                    "reason_code": row.get("reason_code"),
                    "instrument_code": row.get("instrument_code"),
                    "display_name": row.get("display_name"),
                    "source_preview_signal_id": row.get("source_preview_signal_id"),
                    "source_preview_rank": row.get("source_preview_rank"),
                    "source_raw_score": row.get("source_raw_score"),
                    "source_normalized_score": row.get("source_normalized_score"),
                    "source_confidence_score": row.get("source_confidence_score"),
                    "source_v1_1_preview_score": row.get("source_v1_1_preview_score"),
                    "source_v1_1_scoring_mode": row.get("source_v1_1_scoring_mode"),
                    "write_mode": row.get("write_mode") or WRITE_MODE_DRY_RUN,
                }
            )
        return result_rows

    def _build_summary(
        self,
        *,
        preview_payload: Mapping[str, Any],
        candidate_rows: Sequence[Mapping[str, Any]],
        inserted_rows: Sequence[Mapping[str, Any]],
        run_id: int | None,
        run_uid: str | None,
        existing_signal_rows_before_write: int,
        write_mode: str,
    ) -> dict[str, Any]:
        reason_counts: dict[str, int] = {}
        for row in candidate_rows:
            reason = str(row.get("reason_code") or "UNKNOWN")
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        preview_summary = preview_payload.get("preview_summary") or {}
        return {
            "source_preview_status": preview_payload.get("status"),
            "source_preview_row_count": preview_summary.get("signal_preview_row_count"),
            "source_s2_actual_trade_date": preview_summary.get("source_s2_actual_trade_date"),
            "candidate_row_count": len(candidate_rows),
            "inserted_row_count": len(inserted_rows),
            "run_id": run_id,
            "run_uid": run_uid,
            "existing_signal_rows_before_write": existing_signal_rows_before_write,
            "reason_code_counts": reason_counts,
            "write_mode": write_mode,
            "score_written_to_db": "v1_1_preview_score",
        }

    def _decision_reason(self, *, final_blocker_count: int, write_db: bool, run_id: int | None) -> str:
        if final_blocker_count > 0:
            return "Contract blockers remain; no strategy_signal rows were inserted."
        if write_db and run_id:
            return "Preview-scope strategy_signal rows were inserted and are ready for manual review before M5 design."
        return "DB-write contract dry-run passed. strategy_signal write is allowed only with explicit PREVIEW_SCOPE_ONLY confirmation."

    def _blocker_count(self, action_items: Sequence[Mapping[str, Any]], contract_check: Sequence[Mapping[str, Any]]) -> int:
        return sum(1 for item in action_items if item.get("severity") == "BLOCKER") + sum(1 for check in contract_check if check.get("status") == "FAIL")

    def _warn_count(self, action_items: Sequence[Mapping[str, Any]], contract_check: Sequence[Mapping[str, Any]]) -> int:
        return sum(1 for item in action_items if item.get("severity") == "WARN") + sum(1 for check in contract_check if check.get("status") == "WARN")

    def _check(self, check_name: str, status: str, detail: str, *, rows: int) -> dict[str, Any]:
        return {"check_name": check_name, "status": status, "row_count": rows, "detail": detail}

    def _action(self, severity: str, item: str, reason: str, next_step: str) -> dict[str, Any]:
        return {"severity": severity, "item": item, "reason": reason, "next_step": next_step}

    def _dry_run_action_items(self) -> list[dict[str, Any]]:
        return [
            self._action(
                "WARN",
                "dry_run_only",
                "This run generated candidate rows and contract checks only; it did not write strategy_signal.",
                f"After manual review, rerun with --write-db --write-confirmation {REQUIRED_WRITE_CONFIRMATION}.",
            ),
            self._action(
                "WARN",
                "m5_boundary",
                "M5 backtest submission remains blocked until preview-scope DB rows are reviewed.",
                "Do not submit M5 from this dry-run artifact.",
            ),
        ]

    def _post_write_action_items(self) -> list[dict[str, Any]]:
        return [
            self._action(
                "WARN",
                "manual_review_required",
                "Preview-scope strategy_signal rows were inserted, but this is not production trading approval.",
                "Review DB rows, run summary, and reason payloads before M5 design.",
            ),
            self._action(
                "WARN",
                "m5_boundary",
                "M5 design may start after review, but direct M5 submission remains blocked by this task.",
                "Create a separate M5 handoff/backtest-design gate only after manual review.",
            ),
            self._action(
                "WARN",
                "paper_trading_boundary",
                "Rows are not routed to paper trading, target position, order, or risk workflow.",
                "Keep M6/M7 blocked until M5 and risk gates are explicitly passed.",
            ),
        ]

    def _guardrails(self, *, write_db: bool) -> list[str]:
        return [
            "consumes_existing_s3_preview_artifact_only",
            "does_not_create_strategy_metadata",
            "does_not_submit_m5_backtest",
            "does_not_route_to_paper_trading",
            "does_not_change_risk_rules",
            "writes_strategy_signal_only_when_write_db_and_confirmation_are_supplied" if write_db else "dry_run_only_no_db_write",
            "blocks_append_when_existing_same_version_date_unless_explicitly_allowed",
            "score_written_to_db_is_v1_1_preview_score",
        ]

    def _write_artifacts(self, *, config: SignalPreviewDbWriteContractConfig, result: SignalPreviewDbWriteContractResult) -> SignalPreviewDbWriteContractResult:
        output_dir = Path(config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        suffix = config.report_date
        stem = "regime_sector_industry_signal_preview_db_write"
        json_path = output_dir / f"{stem}_{suffix}.json"
        md_path = output_dir / f"{stem}_{suffix}.md"
        candidate_rows_path = output_dir / f"signal_db_write_candidate_rows_{suffix}.csv"
        result_rows_path = output_dir / f"signal_preview_db_write_result_rows_{suffix}.csv"
        contract_path = output_dir / f"signal_preview_db_write_contract_check_{suffix}.csv"
        action_path = output_dir / f"signal_preview_db_write_action_items_{suffix}.csv"
        run_summary_path = output_dir / f"signal_preview_db_write_run_summary_{suffix}.csv"
        result.artifacts = SignalPreviewDbWriteArtifacts(
            json_path=str(json_path),
            markdown_path=str(md_path),
            candidate_rows_path=str(candidate_rows_path),
            result_rows_path=str(result_rows_path),
            contract_check_path=str(contract_path),
            action_items_path=str(action_path),
            run_summary_path=str(run_summary_path),
        )
        json_path.write_text(json.dumps(result.to_dict(include_rows=False), ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
        md_path.write_text(self._render_markdown(result), encoding="utf-8")
        self._write_csv(candidate_rows_path, result.candidate_rows, fieldnames=DB_RESULT_ROW_COLUMNS)
        self._write_csv(result_rows_path, result.result_rows, fieldnames=DB_RESULT_ROW_COLUMNS)
        self._write_csv(contract_path, result.contract_check)
        self._write_csv(action_path, result.action_items)
        self._write_csv(run_summary_path, [result.summary])
        return result

    def _render_markdown(self, result: SignalPreviewDbWriteContractResult) -> str:
        decision = result.validation_decision
        summary = result.summary
        lines = [
            f"# M4 Signal Preview DB Write Contract - {result.strategy_code}",
            "",
            f"- status: `{result.status}`",
            f"- report_date: `{result.report_date}`",
            f"- source_preview_status: `{result.source_preview_status}`",
            f"- as_of_date: `{result.as_of_date}`",
            f"- effective_date: `{result.effective_date}`",
            f"- run_id: `{result.run_id}`",
            f"- candidate_row_count: `{summary.get('candidate_row_count')}`",
            f"- inserted_row_count: `{summary.get('inserted_row_count')}`",
            f"- can_write_strategy_signal_now: `{decision.get('can_write_strategy_signal_now')}`",
            f"- can_start_m5_backtest_design: `{decision.get('can_start_m5_backtest_design')}`",
            f"- can_submit_m5_backtest_now: `{decision.get('can_submit_m5_backtest_now')}`",
            "",
            "## Guardrails",
            "",
        ]
        for guardrail in result.guardrails:
            lines.append(f"- {guardrail}")
        lines.extend(["", "## Contract checks", ""])
        for check in result.contract_check:
            lines.append(f"- `{check.get('status')}` **{check.get('check_name')}**: {check.get('detail')}")
        lines.extend(["", "## Action items", ""])
        for item in result.action_items:
            lines.append(f"- `{item.get('severity')}` **{item.get('item')}**: {item.get('reason')} Next: {item.get('next_step')}")
        lines.extend(
            [
                "",
                "## Boundary note",
                "",
                "This task is a preview-scope adapter. It does not submit M5 backtests, does not route to paper trading, and does not approve production trading.",
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
