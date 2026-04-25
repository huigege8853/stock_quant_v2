from __future__ import annotations

import io
import time
from collections import defaultdict
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from tqdm import tqdm

from stock_quant_v2.config.settings import settings
from stock_quant_v2.data_domain.dto.adjust_factor import AdjustFactorDTO
from stock_quant_v2.data_domain.enums import SyncMode, SyncStatus
from stock_quant_v2.data_domain.mappers.adjust_factor_mapper import (
    dto_to_raw_adjust_factor_dict,
    dto_to_staging_adjust_factor_dict,
)
from stock_quant_v2.data_domain.repositories._batching import iter_chunks
from stock_quant_v2.data_domain.repositories.core_repository import CoreRepository
from stock_quant_v2.data_domain.repositories.raw_repository import RawRepository
from stock_quant_v2.data_domain.repositories.staging_repository import StagingRepository
from stock_quant_v2.data_domain.repositories.sync_run_repository import SyncRunRepository
from stock_quant_v2.data_domain.services.adjust_factor_strict_service import (
    DailyExpandedAdjustFactor,
    expand_events_to_daily_factors,
    query_adjust_factor_events,
)
from stock_quant_v2.data_domain.services.backfill_universe_service import (
    load_cn_stock_backfill_universe,
)
from stock_quant_v2.db.models.core.daily_bar import CoreDailyBar


SYNC_JOB_CODE = "backfill_adjust_factor_by_symbol_range"
THEME_CODE = "AdjustFactor"
DATASET_CODE = "adjust_factor"
PROVIDER_NAME = "baostock"
SYNC_GRANULARITY = "SYMBOL_RANGE"
EXECUTION_MODE = "STRICT_EVENT_TO_DAILY_BACKFILL"


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _short_error_message(exc: Exception | str | None, max_len: int = 160) -> str:
    if exc is None:
        return ""
    text = str(exc).strip().replace("\r", " ").replace("\n", " ")
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _is_reconnectable_provider_error(message: str | None) -> bool:
    if not message:
        return False

    text = str(message).lower()
    keywords = [
        "10054",
        "10060",
        "10002007",
        "网络接收错误",
        "接收数据异常",
        "远程主机强迫关闭了一个现有的连接",
        "forcibly closed",
        "connection aborted",
        "connection reset",
        "connection refused",
        "connection timed out",
        "timed out",
        "broken pipe",
        "socket",
        "please reconnect",
        "query_history_k_data_plus failed",
    ]
    return any(keyword.lower() in text for keyword in keywords)


def _safe_logout(api_client) -> None:
    if api_client is None:
        return

    logout_fn = getattr(api_client, "logout", None)
    if callable(logout_fn):
        try:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                logout_fn()
        except Exception:
            pass


def _rebuild_baostock_api_client():
    from stock_quant_v2.data_domain.providers.baostock.builder import build_baostock_api_client

    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return build_baostock_api_client()


def _query_adjust_factor_events_with_reconnect(
    api_client,
    *,
    exchange_code: str,
    ticker: str,
    start_date: date,
    end_date: date,
    max_attempts: int,
    reconnect_sleep_seconds: float,
    log_fn: Callable[[str], None] | None = None,
):
    current_client = api_client
    last_error: Exception | None = None
    reconnects_used = 0

    for attempt in range(1, max_attempts + 1):
        try:
            events = query_adjust_factor_events(
                current_client,
                exchange_code=exchange_code,
                ticker=ticker,
                start_date=start_date,
                end_date=end_date,
            )
            return current_client, events, reconnects_used

        except Exception as exc:  # noqa: BLE001
            last_error = exc

            if not _is_reconnectable_provider_error(str(exc)):
                raise

            if attempt >= max_attempts:
                raise

            if log_fn is not None:
                log_fn(
                    f"[WARN] reconnectable adjust_factor provider error for "
                    f"{exchange_code}:{ticker}, retry {attempt}/{max_attempts - 1}: "
                    f"{_short_error_message(exc)}"
                )

            _safe_logout(current_client)
            sleep_seconds = reconnect_sleep_seconds * attempt
            time.sleep(sleep_seconds)
            current_client = _rebuild_baostock_api_client()
            reconnects_used += 1

    if last_error is not None:
        raise last_error

    return current_client, [], reconnects_used


def _load_expected_adjust_factor_dates(
    session: Session,
    *,
    instrument_id: int,
    start_date: date,
    end_date: date,
) -> list[date]:
    stmt = (
        select(CoreDailyBar.trade_date)
        .where(
            CoreDailyBar.instrument_id == instrument_id,
            CoreDailyBar.trade_date >= start_date,
            CoreDailyBar.trade_date <= end_date,
            CoreDailyBar.price_adjust_type == "RAW",
        )
        .order_by(CoreDailyBar.trade_date)
    )
    return list(session.execute(stmt).scalars().all())


def _build_event_dto(
    *,
    exchange_code: str,
    ticker: str,
    event,
) -> AdjustFactorDTO:
    return AdjustFactorDTO(
        provider_name="baostock",
        market_code="CN_A",
        exchange_code=exchange_code,
        ticker=ticker,
        vendor_symbol=event.vendor_symbol,
        trade_date=event.event_date,
        adjust_factor=event.forward_factor,
        provider_record_key=f"baostock:{exchange_code}:{ticker}:{event.event_date.isoformat()}",
        raw_payload=event.raw_payload,
    )


def _build_core_daily_payload(
    *,
    instrument_id: int,
    trade_date: date,
    expanded_row: DailyExpandedAdjustFactor,
    data_version_id: int,
) -> dict:
    return {
        "instrument_id": instrument_id,
        "trade_date": trade_date,
        "forward_factor": expanded_row.forward_factor,
        "backward_factor": expanded_row.backward_factor,
        "data_version_id": data_version_id,
        "updated_at": utc_now(),
    }


def _guard_against_duplicate_running_batches(
    *,
    session: Session,
    sync_repo: SyncRunRepository,
    start_date: date,
    end_date: date,
    symbol_chunk_size: int,
) -> None:
    if not settings.adjust_factor_running_guard_enabled:
        return

    running_batches = sync_repo.find_running_batches(
        session,
        sync_job_code=SYNC_JOB_CODE,
        theme_code=THEME_CODE,
        dataset_code=DATASET_CODE,
        provider_name=PROVIDER_NAME,
        partition_from=start_date,
        partition_to=end_date,
        sync_granularity=SYNC_GRANULARITY,
        symbol_chunk_size=symbol_chunk_size,
        execution_mode=EXECUTION_MODE,
    )

    if not running_batches:
        return

    now = utc_now()
    stale_threshold = timedelta(minutes=settings.adjust_factor_stale_running_minutes)

    stale_batches: list[dict] = []
    active_batches: list[dict] = []

    for item in running_batches:
        started_at = item.get("started_at")
        if started_at is None:
            active_batches.append(item)
            continue

        if now - started_at >= stale_threshold:
            stale_batches.append(item)
        else:
            active_batches.append(item)

    if settings.adjust_factor_auto_fail_stale_running and stale_batches:
        batch_ids = [int(item["batch_id"]) for item in stale_batches]
        data_sync_run_ids = [int(item["data_sync_run_id"]) for item in stale_batches]

        reason = (
            "auto marked failed: stale RUNNING adjust_factor batch before resume; "
            f"threshold_minutes={settings.adjust_factor_stale_running_minutes}"
        )

        sync_repo.mark_running_batches_failed_by_ids(
            session,
            batch_ids=batch_ids,
            data_sync_run_ids=data_sync_run_ids,
            reason=reason,
        )
        session.commit()

        tqdm.write(
            "[INFO] auto failed stale adjust_factor RUNNING batches: "
            + ", ".join(
                f"batch_id={item['batch_id']},chunk={item['batch_no']}"
                for item in stale_batches
            )
        )

    if active_batches:
        detail = "; ".join(
            (
                f"batch_id={item['batch_id']}, "
                f"run_id={item['data_sync_run_id']}, "
                f"chunk={item['batch_no']}, "
                f"started_at={item['started_at']}"
            )
            for item in active_batches
        )

        raise RuntimeError(
            "检测到 adjust_factor 同一区间仍有 RUNNING batch。"
            "为避免重复跑同一 chunk，本次启动已停止。"
            f" 请等待任务结束，或手工确认后标记 FAILED。active_batches=[{detail}]"
        )


def run_backfill_adjust_factor_by_symbol_range(
    session: Session,
    baostock_api_client,
    run_id: int,
    data_version_id: int,
    start_date: date,
    end_date: date,
    symbol_chunk_size: int = 100,
    *,
    resume_enabled: bool = True,
    force_rerun: bool = False,
    max_reconnect_attempts: int = 3,
    reconnect_sleep_seconds: float = 1.0,
    fail_fast: bool = False,
) -> None:
    sync_repo = SyncRunRepository()
    raw_repo = RawRepository()
    stg_repo = StagingRepository()
    core_repo = CoreRepository()

    universe = load_cn_stock_backfill_universe(
        session,
        start_date=start_date,
        end_date=end_date,
        market_code="CN_A",
    )
    if not universe:
        return

    if settings.daily_bar_debug_mode and settings.daily_bar_debug_limit_symbols:
        universe = universe[: settings.daily_bar_debug_limit_symbols]

    all_chunks = list(iter_chunks(universe, symbol_chunk_size))
    if not all_chunks:
        return

    _guard_against_duplicate_running_batches(
        session=session,
        sync_repo=sync_repo,
        start_date=start_date,
        end_date=end_date,
        symbol_chunk_size=symbol_chunk_size,
    )

    current_api_client = baostock_api_client

    if start_date == end_date:
        target_daily_bar_count = session.execute(
            select(func.count())
            .select_from(CoreDailyBar)
            .where(
                CoreDailyBar.trade_date == start_date,
                CoreDailyBar.price_adjust_type == "RAW",
            )
        ).scalar_one()

        if int(target_daily_bar_count or 0) == 0:
            raise RuntimeError(
                "adjust_factor strict single-date backfill aborted because "
                f"no RAW daily_bar rows exist for trade_date={start_date.isoformat()}."
            )

    last_successful_chunk_no = 0

    if force_rerun:
        tqdm.write(
            "[INFO] adjust_factor force_rerun enabled: ignore previous SUCCESS chunks, "
            "restart from chunk=1"
        )
    elif resume_enabled:
        last_successful_chunk_no = sync_repo.find_latest_successful_batch_no(
            session,
            sync_job_code=SYNC_JOB_CODE,
            theme_code=THEME_CODE,
            dataset_code=DATASET_CODE,
            provider_name=PROVIDER_NAME,
            partition_from=start_date,
            partition_to=end_date,
            sync_granularity=SYNC_GRANULARITY,
            symbol_chunk_size=symbol_chunk_size,
            execution_mode=EXECUTION_MODE,
        )

    start_chunk_no = 1 if force_rerun else (last_successful_chunk_no + 1 if resume_enabled else 1)

    if start_chunk_no > len(all_chunks):
        tqdm.write(
            f"[INFO] adjust_factor strict backfill already completed. "
            f"last_successful_chunk_no={last_successful_chunk_no}, "
            f"total_chunks={len(all_chunks)}"
        )
        _safe_logout(current_api_client)
        return

    if resume_enabled and last_successful_chunk_no > 0:
        tqdm.write(
            f"[INFO] adjust_factor resume enabled: skip finished chunks "
            f"1..{last_successful_chunk_no}, continue from chunk={start_chunk_no}"
        )

    for chunk_no, symbol_chunk in enumerate(all_chunks, start=1):
        if chunk_no < start_chunk_no:
            continue

        data_sync_run = sync_repo.create_data_sync_run(
            session,
            {
                "run_id": run_id,
                "sync_job_code": SYNC_JOB_CODE,
                "theme_code": THEME_CODE,
                "dataset_code": DATASET_CODE,
                "provider_name": PROVIDER_NAME,
                "sync_mode": SyncMode.FULL.value,
                "sync_granularity": SYNC_GRANULARITY,
                "partition_from": start_date,
                "partition_to": end_date,
                "status": SyncStatus.PENDING.value,
                "cursor_json": {
                    "chunk_no": chunk_no,
                    "symbol_chunk_size": symbol_chunk_size,
                },
                "request_params": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "execution_mode": EXECUTION_MODE,
                    "provider_name": PROVIDER_NAME,
                    "symbol_chunk_size": symbol_chunk_size,
                    "strict_mode": True,
                    "event_effective_offset_trade_days": 1,
                    "with_auto_reconnect": True,
                    "resume_enabled": resume_enabled,
                    "force_rerun": force_rerun,
                    "chunk_symbols": [f'{item["exchange_code"]}:{item["ticker"]}' for item in symbol_chunk],
                },
                "stats_json": None,
                "started_at": None,
                "finished_at": None,
            },
        )
        session.commit()

        sync_repo.mark_data_sync_run_running(session, data_sync_run)
        session.commit()

        batch = sync_repo.create_data_batch(
            session,
            {
                "data_sync_run_id": data_sync_run.id,
                "batch_no": chunk_no,
                "batch_key": f"{start_date.isoformat()}:{end_date.isoformat()}:chunk_{chunk_no}",
                "batch_type": "SYMBOL_RANGE",
                "partition_date": start_date,
                "partition_symbol": None,
                "page_no": 1,
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

        try:
            sync_repo.mark_data_batch_running(session, batch)
            session.commit()

            input_rows = 0
            raw_rows = 0
            staging_rows = 0
            core_upsert_rows = 0
            error_rows = 0

            symbols_attempted = 0
            symbols_hit = 0
            expected_trade_days_total = 0

            provider_success_counter = defaultdict(int)
            provider_empty_counter = defaultdict(int)
            provider_error_counter = defaultdict(int)
            default_seed_counter = 0
            reconnect_counter = 0
            per_symbol_stats: list[dict] = []

            raw_payloads: list[dict] = []
            stg_payloads: list[dict] = []
            core_payloads: list[dict] = []

            progress = tqdm(
                symbol_chunk,
                desc=f"strict_expand_adjust_factor chunk={chunk_no}",
                unit="symbol",
                dynamic_ncols=True,
            )

            for item in progress:
                instrument_id = item["instrument_id"]
                exchange_code = item["exchange_code"]
                ticker = item["ticker"]
                list_date = item.get("list_date") or start_date

                symbols_attempted += 1

                expected_trade_dates = _load_expected_adjust_factor_dates(
                    session,
                    instrument_id=instrument_id,
                    start_date=start_date,
                    end_date=end_date,
                )
                expected_trade_days_total += len(expected_trade_dates)

                if not expected_trade_dates:
                    per_symbol_stats.append(
                        {
                            "exchange_code": exchange_code,
                            "ticker": ticker,
                            "expected_trade_days": 0,
                            "event_rows": 0,
                            "daily_rows": 0,
                            "success": True,
                            "skipped_reason": "no_raw_daily_bar_dates",
                        }
                    )
                    continue

                try:
                    current_api_client, events, reconnects_used = _query_adjust_factor_events_with_reconnect(
                        current_api_client,
                        exchange_code=exchange_code,
                        ticker=ticker,
                        start_date=list_date,
                        end_date=end_date,
                        max_attempts=max_reconnect_attempts,
                        reconnect_sleep_seconds=reconnect_sleep_seconds,
                        log_fn=tqdm.write,
                    )
                    reconnect_counter += reconnects_used

                    if events:
                        symbols_hit += 1
                        provider_success_counter["baostock"] += len(events)
                    else:
                        provider_empty_counter["baostock"] += 1
                        default_seed_counter += 1

                    for event in events:
                        dto = _build_event_dto(
                            exchange_code=exchange_code,
                            ticker=ticker,
                            event=event,
                        )

                        raw_payload = dto_to_raw_adjust_factor_dict(dto, data_sync_run.id, batch.id)
                        raw_payloads.append(raw_payload)

                        stg_payload = dto_to_staging_adjust_factor_dict(
                            dto=dto,
                            sync_run_id=data_sync_run.id,
                            batch_id=batch.id,
                            raw_record_id=None,
                        )
                        stg_payloads.append(stg_payload)

                    expanded_daily_rows = expand_events_to_daily_factors(
                        events=events,
                        expected_trade_dates=expected_trade_dates,
                        effective_offset_trade_days=1,
                        default_forward_factor=Decimal("1"),
                        default_backward_factor=Decimal("1"),
                    )

                    input_rows += len(events)

                    for expanded_row in expanded_daily_rows:
                        core_payloads.append(
                            _build_core_daily_payload(
                                instrument_id=instrument_id,
                                trade_date=expanded_row.trade_date,
                                expanded_row=expanded_row,
                                data_version_id=data_version_id,
                            )
                        )

                    per_symbol_stats.append(
                        {
                            "exchange_code": exchange_code,
                            "ticker": ticker,
                            "list_date": list_date.isoformat() if list_date else None,
                            "expected_trade_days": len(expected_trade_dates),
                            "event_rows": len(events),
                            "daily_rows": len(expanded_daily_rows),
                            "used_default_seed": len(events) == 0,
                            "success": True,
                        }
                    )

                except Exception as exc:  # noqa: BLE001
                    error_rows += 1
                    provider_error_counter["baostock"] += 1

                    sync_repo.add_quality_issue(
                        session,
                        {
                            "data_sync_run_id": data_sync_run.id,
                            "batch_id": batch.id,
                            "theme_code": THEME_CODE,
                            "dataset_code": DATASET_CODE,
                            "layer_code": "RAW",
                            "issue_code": "PROVIDER_QUERY_FAILED",
                            "severity": "ERROR",
                            "business_key": f"{exchange_code}:{ticker}:{start_date.isoformat()}:{end_date.isoformat()}",
                            "provider_name": PROVIDER_NAME,
                            "trade_date": None,
                            "symbol": ticker,
                            "record_ref": None,
                            "issue_detail": {"error": _short_error_message(exc)},
                            "created_at": utc_now(),
                        },
                    )

                    per_symbol_stats.append(
                        {
                            "exchange_code": exchange_code,
                            "ticker": ticker,
                            "list_date": list_date.isoformat() if list_date else None,
                            "expected_trade_days": len(expected_trade_dates),
                            "event_rows": 0,
                            "daily_rows": 0,
                            "success": False,
                            "error": _short_error_message(exc),
                        }
                    )

                    tqdm.write(
                        f"[WARN] adjust_factor symbol failed after retries: "
                        f"{exchange_code}:{ticker} - {_short_error_message(exc)}"
                    )

                    if fail_fast:
                        raise

                progress.set_postfix(
                    hit=symbols_hit,
                    input=input_rows,
                    default_seed=default_seed_counter,
                    reconnect=reconnect_counter,
                    err=error_rows,
                )

            raw_rows += raw_repo.bulk_upsert_raw_adjust_factor(session, raw_payloads, chunk_size=500)
            staging_rows += stg_repo.bulk_upsert_stg_adjust_factor(session, stg_payloads, chunk_size=500)
            core_upsert_rows += core_repo.bulk_upsert_adjust_factor(session, core_payloads, chunk_size=500)

            strict_single_date_zero_result = (
                    start_date == end_date
                    and expected_trade_days_total > 0
                    and core_upsert_rows == 0
            )

            if strict_single_date_zero_result:
                raise RuntimeError(
                    "adjust_factor strict single-date backfill produced zero rows. "
                    f"trade_date={start_date.isoformat()}, "
                    f"expected_trade_days_total={expected_trade_days_total}. "
                    "Do not mark SUCCESS, otherwise resume will incorrectly skip this window."
                )

            batch_status = SyncStatus.SUCCESS.value if error_rows == 0 else SyncStatus.PARTIAL.value

            checkpoint_json = {
                "chunk_no": chunk_no,
                "symbols_attempted": symbols_attempted,
                "symbols_hit": symbols_hit,
                "provider_success_counter": dict(provider_success_counter),
                "provider_empty_counter": dict(provider_empty_counter),
                "provider_error_counter": dict(provider_error_counter),
                "default_seed_counter": default_seed_counter,
                "reconnect_counter": reconnect_counter,
                "per_symbol_stats_sample": per_symbol_stats[:100],
            }

            sync_repo.mark_data_batch_finished(
                session,
                batch,
                batch_status,
                input_rows=input_rows,
                raw_rows=raw_rows,
                staging_rows=staging_rows,
                core_upsert_rows=core_upsert_rows,
                error_rows=error_rows,
                checkpoint_json=checkpoint_json,
            )

            sync_repo.mark_data_sync_run_finished(
                session,
                data_sync_run,
                batch_status,
                {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "chunk_no": chunk_no,
                    "symbols_attempted": symbols_attempted,
                    "symbols_hit": symbols_hit,
                    "input_rows": input_rows,
                    "raw_rows": raw_rows,
                    "staging_rows": staging_rows,
                    "core_upsert_rows": core_upsert_rows,
                    "error_rows": error_rows,
                    "provider_success_counter": dict(provider_success_counter),
                    "provider_empty_counter": dict(provider_empty_counter),
                    "provider_error_counter": dict(provider_error_counter),
                    "default_seed_counter": default_seed_counter,
                    "reconnect_counter": reconnect_counter,
                },
            )
            session.commit()

        except Exception as exc:  # noqa: BLE001
            session.rollback()
            try:
                sync_repo.mark_data_batch_finished(
                    session,
                    batch,
                    SyncStatus.FAILED.value,
                    input_rows=0,
                    raw_rows=0,
                    staging_rows=0,
                    core_upsert_rows=0,
                    error_rows=1,
                    error_message=_short_error_message(exc),
                )
                sync_repo.mark_data_sync_run_finished(
                    session,
                    data_sync_run,
                    SyncStatus.FAILED.value,
                    {"error": _short_error_message(exc), "chunk_no": chunk_no},
                )
                session.commit()
            except Exception:
                session.rollback()
            raise

    _safe_logout(current_api_client)