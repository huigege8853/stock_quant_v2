from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from stock_quant_v2.config.settings import settings
from stock_quant_v2.data_domain.enums import SyncMode, SyncStatus
from stock_quant_v2.data_domain.provider_priority import MARKET_INDEX_BAR_PROVIDER_PRIORITY
from stock_quant_v2.data_domain.providers.paid.client import PaidClient
from stock_quant_v2.data_domain.providers.paid.market_index_bar_provider import PaidMarketIndexBarProvider
from stock_quant_v2.data_domain.providers.pytdx.client import PytdxClient
from stock_quant_v2.data_domain.providers.pytdx.market_index_bar_provider import PytdxMarketIndexBarProvider
from stock_quant_v2.data_domain.providers.sina.client import SinaClient
from stock_quant_v2.data_domain.providers.sina.market_index_bar_provider import SinaMarketIndexBarProvider
from stock_quant_v2.data_domain.repositories.core_repository import CoreRepository
from stock_quant_v2.data_domain.repositories.data_version_repository import DataVersionRepository
from stock_quant_v2.data_domain.repositories.market_index_lookup_repository import MarketIndexLookupRepository
from stock_quant_v2.data_domain.repositories.raw_repository import RawRepository
from stock_quant_v2.data_domain.repositories.staging_repository import StagingRepository
from stock_quant_v2.data_domain.repositories.sync_run_repository import SyncRunRepository
from stock_quant_v2.data_domain.services.lineage_service import LineageService
from stock_quant_v2.data_domain.services.provider_fallback_service import (
    ProviderAttemptDetail,
    ProviderFallbackService,
)
from stock_quant_v2.data_domain.services.quality_service import QualityService


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _json_safe(value):
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value) if not isinstance(value, (str, int, float, bool, type(None))) else value


def _hash_payload(payload: dict) -> str:
    body = json.dumps(_json_safe(payload), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _new_provider_counter() -> dict[str, int]:
    return {
        "baostock": 0,
        "sina": 0,
        "akshare": 0,
        "pytdx": 0,
        "tushare": 0,
        "paid": 0,
    }


def _attempts_to_json(attempts: list[ProviderAttemptDetail]) -> list[dict]:
    return [
        {
            "provider_name": item.provider_name,
            "success": item.success,
            "row_count": item.row_count,
            "error": item.error,
            "skipped": getattr(item, "skipped", False),
            "skipped_reason": getattr(item, "skipped_reason", None),
        }
        for item in attempts
    ]


def _load_market_index_bar_provider_priority() -> list[str]:
    configured = settings.get_market_index_bar_provider_priority()
    return configured or MARKET_INDEX_BAR_PROVIDER_PRIORITY


def _build_skipped_providers() -> dict[str, str]:
    skipped: dict[str, str] = {}
    if not settings.tushare_enabled:
        skipped["tushare"] = "disabled_by_config"
    return skipped


def _build_provider_attempts(
    index_code: str,
    trade_date: date,
    sina_provider: SinaMarketIndexBarProvider,
    pytdx_provider: PytdxMarketIndexBarProvider,
    paid_provider: PaidMarketIndexBarProvider,
) -> list[tuple[str, callable]]:
    handlers = {
        "baostock": lambda: [],
        "sina": lambda index_code=index_code, trade_date=trade_date: list(
            sina_provider.fetch({"index_code": index_code, "trade_date": trade_date})
        ),
        "akshare": lambda: [],
        "pytdx": lambda index_code=index_code, trade_date=trade_date: list(
            pytdx_provider.fetch({"index_code": index_code, "trade_date": trade_date})
        ),
        "tushare": lambda: [],
        "paid": lambda index_code=index_code, trade_date=trade_date: list(
            paid_provider.fetch({"index_code": index_code, "trade_date": trade_date})
        ),
    }

    attempts: list[tuple[str, callable]] = []
    for provider_name in _load_market_index_bar_provider_priority():
        if provider_name == "skip":
            continue
        handler = handlers.get(provider_name)
        if handler is not None:
            attempts.append((provider_name, handler))
    return attempts


def run_sync_market_index_bar(
    session: Session,
    sina_api_client,
    run_id: int,
    start_date: date,
    end_date: date,
    index_codes: list[str] | None = None,
    provider_name: str = "fallback",
    sync_mode: str | None = None,
) -> dict:
    sync_repo = SyncRunRepository()
    lookup_repo = MarketIndexLookupRepository()
    raw_repo = RawRepository()
    stg_repo = StagingRepository()
    core_repo = CoreRepository()
    version_repo = DataVersionRepository()

    fallback_service = ProviderFallbackService()
    quality_service = QualityService()
    lineage_service = LineageService()

    actual_sync_mode = sync_mode or (
        SyncMode.BACKFILL.value if start_date != end_date else SyncMode.INCREMENTAL.value
    )

    data_sync_run = sync_repo.create_data_sync_run(
        session,
        {
            "run_id": run_id,
            "sync_job_code": "sync_market_index_bar",
            "theme_code": "MarketIndex",
            "dataset_code": "market_index_bar",
            "provider_name": provider_name,
            "sync_mode": actual_sync_mode,
            "sync_granularity": "DATE",
            "partition_from": start_date,
            "partition_to": end_date,
            "status": SyncStatus.PENDING.value,
            "cursor_json": None,
            "request_params": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "index_codes": index_codes or [],
                "providers": _load_market_index_bar_provider_priority(),
            },
            "stats_json": None,
            "started_at": None,
            "finished_at": None,
        },
    )
    session.commit()

    sync_repo.mark_data_sync_run_running(session, data_sync_run)
    session.commit()

    sina_provider = SinaMarketIndexBarProvider(client=SinaClient(api_client=sina_api_client))
    pytdx_provider = PytdxMarketIndexBarProvider(client=PytdxClient(api_client=None))
    paid_provider = PaidMarketIndexBarProvider(client=PaidClient(api_client=None))

    total_input_rows = 0
    total_raw_rows = 0
    total_staging_rows = 0
    total_core_upsert_rows = 0
    total_error_rows = 0
    skipped_batches = 0

    total_provider_success_counter = _new_provider_counter()
    total_provider_empty_counter = _new_provider_counter()
    total_provider_error_counter = _new_provider_counter()

    indexes = lookup_repo.list_active_market_indexes(session, index_codes=index_codes)
    dates = lookup_repo.list_trading_dates(session, start_date=start_date, end_date=end_date)
    id_map = lookup_repo.get_market_index_id_map(session, [x.index_code for x in indexes])

    batch_no = 0
    for trade_date in dates:
        batch_no += 1

        batch = sync_repo.create_data_batch(
            session,
            {
                "data_sync_run_id": data_sync_run.id,
                "batch_no": batch_no,
                "batch_key": trade_date.isoformat(),
                "batch_type": "TRADE_DATE",
                "partition_date": trade_date,
                "partition_symbol": None,
                "page_no": None,
                "status": SyncStatus.PENDING.value,
                "retry_count": 0,
                "input_rows": None,
                "raw_rows": None,
                "staging_rows": None,
                "core_upsert_rows": None,
                "error_rows": None,
                "checkpoint_json": None,
                "error_message": None,
                "started_at": None,
                "finished_at": None,
            },
        )
        session.commit()

        sync_repo.mark_data_batch_running(session, batch)
        session.commit()

        batch_input = 0
        batch_raw = 0
        batch_stg = 0
        batch_core = 0
        batch_err = 0

        batch_provider_success_counter = _new_provider_counter()
        batch_provider_empty_counter = _new_provider_counter()
        batch_provider_error_counter = _new_provider_counter()
        batch_attempt_logs: list[dict] = []

        try:
            for idx in indexes:
                batch_input += 1

                provider_attempts = _build_provider_attempts(
                    index_code=idx.index_code,
                    trade_date=trade_date,
                    sina_provider=sina_provider,
                    pytdx_provider=pytdx_provider,
                    paid_provider=paid_provider,
                )

                result = fallback_service.try_providers(
                    provider_attempts,
                    skipped_providers=_build_skipped_providers(),
                )

                batch_attempt_logs.append(
                    {
                        "index_code": idx.index_code,
                        "trade_date": trade_date.isoformat(),
                        "selected_provider": result.provider_name,
                        "success": result.success,
                        "error": result.error,
                        "attempts": _attempts_to_json(result.attempts),
                    }
                )

                for attempt in result.attempts:
                    if getattr(attempt, "skipped", False):
                        continue
                    if attempt.success:
                        batch_provider_success_counter[attempt.provider_name] += 1
                    else:
                        if attempt.error == "empty rows":
                            batch_provider_empty_counter[attempt.provider_name] += 1
                        else:
                            batch_provider_error_counter[attempt.provider_name] += 1

                if not result.success:
                    sync_repo.add_quality_issue(
                        session,
                        {
                            "data_sync_run_id": data_sync_run.id,
                            "batch_id": batch.id,
                            "theme_code": "MarketIndex",
                            "dataset_code": "market_index_bar",
                            "layer_code": "RAW",
                            "issue_code": "ALL_PROVIDERS_UNAVAILABLE",
                            "severity": "WARN",
                            "business_key": f"{idx.index_code}:{trade_date}",
                            "provider_name": None,
                            "trade_date": trade_date,
                            "symbol": idx.index_code,
                            "record_ref": None,
                            "issue_detail": {
                                "error": result.error,
                                "attempts": _attempts_to_json(result.attempts),
                            },
                            "created_at": utc_now(),
                        },
                    )
                    continue

                rows = result.data or []
                if not rows:
                    continue

                for row in rows:
                    raw_payload = {
                        "provider_name": row["provider_name"],
                        "dataset_code": row["dataset_code"],
                        "provider_record_key": row["provider_record_key"],
                        "symbol": row["index_code"],
                        "trade_date": row["trade_date"],
                        "batch_id": batch.id,
                        "sync_run_id": data_sync_run.id,
                        "request_params": {
                            "index_code": idx.index_code,
                            "trade_date": trade_date.isoformat(),
                        },
                        "payload_json": _json_safe(row["raw_payload"]),
                        "payload_hash": _hash_payload(row["raw_payload"]),
                        "provider_update_ts": None,
                        "ingested_at": utc_now(),
                    }
                    raw_obj = raw_repo.upsert_raw_market_index(session, raw_payload)
                    batch_raw += 1

                    stg_payload = {
                        "sync_run_id": data_sync_run.id,
                        "batch_id": batch.id,
                        "provider_name": row["provider_name"],
                        "dataset_code": row["dataset_code"],
                        "index_code": row["index_code"],
                        "exchange_code": row.get("exchange_code") or idx.exchange_code,
                        "index_name": row.get("index_name") or idx.index_name,
                        "index_type": row.get("index_type") or idx.index_type,
                        "trade_date": row["trade_date"],
                        "open": row.get("open"),
                        "high": row.get("high"),
                        "low": row.get("low"),
                        "close": row.get("close"),
                        "volume": row.get("volume"),
                        "turnover": row.get("turnover"),
                        "provider_record_key": row["provider_record_key"],
                        "raw_record_id": raw_obj.id,
                    }

                    issues = quality_service.validate_market_index_bar_row(stg_payload)
                    for issue in issues:
                        if not issue.passed:
                            sync_repo.add_quality_issue(
                                session,
                                {
                                    "data_sync_run_id": data_sync_run.id,
                                    "batch_id": batch.id,
                                    "theme_code": "MarketIndex",
                                    "dataset_code": "market_index_bar",
                                    "layer_code": "STAGING",
                                    "issue_code": issue.issue_code,
                                    "severity": issue.severity,
                                    "business_key": f'{stg_payload["index_code"]}:{stg_payload["trade_date"]}',
                                    "provider_name": stg_payload["provider_name"],
                                    "trade_date": stg_payload["trade_date"],
                                    "symbol": stg_payload["index_code"],
                                    "record_ref": {"raw_record_id": raw_obj.id},
                                    "issue_detail": issue.detail,
                                    "created_at": utc_now(),
                                },
                            )

                    blocking_issues = [x for x in issues if not x.passed and x.severity in ("ERROR", "FATAL")]
                    if blocking_issues:
                        batch_err += 1
                        continue

                    stg_obj = stg_repo.upsert_stg_market_index(session, stg_payload)
                    batch_stg += 1

                    sync_repo.add_lineage(
                        session,
                        lineage_service.build_market_index_raw_to_staging(
                            sync_run_id=data_sync_run.id,
                            batch_id=batch.id,
                            raw_id=raw_obj.id,
                            stg_id=stg_obj.id,
                        ),
                    )

                    market_index_id = id_map.get(idx.index_code)
                    if market_index_id is None:
                        sync_repo.add_quality_issue(
                            session,
                            {
                                "data_sync_run_id": data_sync_run.id,
                                "batch_id": batch.id,
                                "theme_code": "MarketIndex",
                                "dataset_code": "market_index_bar",
                                "layer_code": "CORE",
                                "issue_code": "MARKET_INDEX_NOT_FOUND",
                                "severity": "ERROR",
                                "business_key": f'{stg_payload["index_code"]}:{stg_payload["trade_date"]}',
                                "provider_name": stg_payload["provider_name"],
                                "trade_date": stg_payload["trade_date"],
                                "symbol": stg_payload["index_code"],
                                "record_ref": {"stg_id": stg_obj.id},
                                "issue_detail": {"index_code": stg_payload["index_code"]},
                                "created_at": utc_now(),
                            },
                        )
                        batch_err += 1
                        continue

                    core_payload = {
                        "market_index_id": market_index_id,
                        "trade_date": row["trade_date"],
                        "open": row.get("open"),
                        "high": row.get("high"),
                        "low": row.get("low"),
                        "close": row.get("close"),
                        "volume": row.get("volume"),
                        "turnover": row.get("turnover"),
                        "source_provider": row["provider_name"],
                        "data_version_id": None,
                    }
                    core_repo.upsert_market_index_bar(session, core_payload)
                    batch_core += 1

                    sync_repo.add_lineage(
                        session,
                        lineage_service.build_market_index_staging_to_core(
                            sync_run_id=data_sync_run.id,
                            batch_id=batch.id,
                            stg_id=stg_obj.id,
                            market_index_id=market_index_id,
                            trade_date=str(stg_payload["trade_date"]),
                        ),
                    )

            for key in total_provider_success_counter:
                total_provider_success_counter[key] += batch_provider_success_counter[key]
                total_provider_empty_counter[key] += batch_provider_empty_counter[key]
                total_provider_error_counter[key] += batch_provider_error_counter[key]

            batch.checkpoint_json = {
                "provider_success_counter": batch_provider_success_counter,
                "provider_empty_counter": batch_provider_empty_counter,
                "provider_error_counter": batch_provider_error_counter,
                "attempt_log_sample": batch_attempt_logs[:100],
                "attempt_log_total": len(batch_attempt_logs),
            }

            batch_status = SyncStatus.SUCCESS.value if batch_err == 0 else SyncStatus.PARTIAL.value
            sync_repo.mark_data_batch_finished(
                session,
                batch,
                batch_status,
                input_rows=batch_input,
                raw_rows=batch_raw,
                staging_rows=batch_stg,
                core_upsert_rows=batch_core,
                error_rows=batch_err,
            )
            session.commit()

            if batch_raw == 0 and batch_stg == 0 and batch_core == 0:
                skipped_batches += 1

        except Exception as exc:  # noqa: BLE001
            session.rollback()
            batch = session.get(type(batch), batch.id)
            if batch is not None:
                batch.error_message = str(exc)
                sync_repo.mark_data_batch_finished(
                    session,
                    batch,
                    SyncStatus.FAILED.value,
                    input_rows=batch_input,
                    raw_rows=batch_raw,
                    staging_rows=batch_stg,
                    core_upsert_rows=batch_core,
                    error_rows=batch_err + 1,
                )
                session.commit()
            total_error_rows += 1
            continue

        total_input_rows += batch_input
        total_raw_rows += batch_raw
        total_staging_rows += batch_stg
        total_core_upsert_rows += batch_core
        total_error_rows += batch_err

    data_version_id = None
    if total_core_upsert_rows > 0:
        version = f"market_index_bar_{start_date.isoformat()}_{end_date.isoformat()}_{run_id}"
        dv = version_repo.create_data_version(
            session=session,
            dataset_code="market_index_bar",
            vendor_code="sina",
            run_id=run_id,
            version=version,
            as_of_date=end_date,
            row_count=total_core_upsert_rows,
            status="DRAFT",
            published=False,
        )
        version_repo.mark_published(session, dv, row_count=total_core_upsert_rows, content_hash=None)
        data_version_id = dv.id
        session.flush()

    final_status = SyncStatus.SUCCESS.value if total_error_rows == 0 else SyncStatus.PARTIAL.value
    sync_repo.mark_data_sync_run_finished(
        session,
        data_sync_run,
        final_status,
        {
            "input_rows": total_input_rows,
            "raw_rows": total_raw_rows,
            "staging_rows": total_staging_rows,
            "core_upsert_rows": total_core_upsert_rows,
            "error_rows": total_error_rows,
            "skipped_batches": skipped_batches,
            "data_version_id": data_version_id,
            "provider_success_counter": total_provider_success_counter,
            "provider_empty_counter": total_provider_empty_counter,
            "provider_error_counter": total_provider_error_counter,
        },
    )
    session.commit()

    return {
        "input_rows": total_input_rows,
        "raw_rows": total_raw_rows,
        "staging_rows": total_staging_rows,
        "core_upsert_rows": total_core_upsert_rows,
        "error_rows": total_error_rows,
        "skipped_batches": skipped_batches,
        "data_version_id": data_version_id,
        "provider_success_counter": total_provider_success_counter,
        "provider_empty_counter": total_provider_empty_counter,
        "provider_error_counter": total_provider_error_counter,
    }