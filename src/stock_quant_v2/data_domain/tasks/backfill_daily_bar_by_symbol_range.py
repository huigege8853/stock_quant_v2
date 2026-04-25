from __future__ import annotations

import io
import time
from collections import defaultdict
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy.orm import Session
from tqdm import tqdm

from stock_quant_v2.config.settings import settings
from stock_quant_v2.data_domain.dto.daily_bar import DailyBarDTO
from stock_quant_v2.data_domain.enums import SyncMode, SyncStatus
from stock_quant_v2.data_domain.mappers.daily_bar_mapper import (
    dto_to_raw_daily_bar_dict,
    dto_to_staging_daily_bar_dict,
    staging_to_core_daily_bar_dict,
)
from stock_quant_v2.data_domain.repositories._batching import iter_chunks
from stock_quant_v2.data_domain.repositories.core_repository import CoreRepository
from stock_quant_v2.data_domain.repositories.raw_repository import RawRepository
from stock_quant_v2.data_domain.repositories.staging_repository import StagingRepository
from stock_quant_v2.data_domain.repositories.sync_run_repository import SyncRunRepository
from stock_quant_v2.data_domain.services.backfill_universe_service import (
    load_cn_stock_backfill_universe,
)
from stock_quant_v2.data_domain.services.strict_expected_date_service import (
    build_expected_trade_date_plan,
    classify_missing_daily_bar_issue,
)
from stock_quant_v2.data_domain.services.strict_trade_date_service import (
    load_open_trade_dates_by_exchange,
)

import socket


SYNC_JOB_CODE = "backfill_daily_bar_by_symbol_range"
THEME_CODE = "DailyBar"
DATASET_CODE = "daily_bar"
PROVIDER_NAME = "baostock"
SYNC_GRANULARITY = "SYMBOL_RANGE"
EXECUTION_MODE = "STRICT_BACKFILL_BY_SYMBOL_RANGE"


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _to_decimal(value: Any) -> Decimal | None:
    if value in (None, "", "null", "-", "--"):
        return None
    return Decimal(str(value))


def _to_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _vendor_symbol(exchange_code: str, ticker: str) -> str:
    if exchange_code == "SSE":
        return f"sh.{ticker}"
    if exchange_code == "SZSE":
        return f"sz.{ticker}"
    if exchange_code == "BSE":
        return f"bj.{ticker}"
    return ticker


def _baostock_code(exchange_code: str, ticker: str) -> str:
    if exchange_code == "SSE":
        return f"sh.{ticker}"
    if exchange_code == "SZSE":
        return f"sz.{ticker}"
    if exchange_code == "BSE":
        return f"bj.{ticker}"
    return ticker


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
        "超时",
        "timeout",
        "timed out",
        "connection timed out",
        "远程主机强迫关闭了一个现有的连接",
        "forcibly closed",
        "connection aborted",
        "connection reset",
        "connection refused",
        "broken pipe",
        "socket",
        "please reconnect",
        "query_history_k_data_plus failed",
    ]
    return any(keyword.lower() in text for keyword in keywords)


def _short_error_message(exc: Exception | str | None, max_len: int = 160) -> str:
    if exc is None:
        return ""
    text = str(exc).strip().replace("\r", " ").replace("\n", " ")
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


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


def _query_history_k_data_plus_rows_once(
    api_client,
    *,
    exchange_code: str,
    ticker: str,
    start_date: date,
    end_date: date,
) -> list[dict]:
    if api_client is None:
        return []

    bs_code = _baostock_code(exchange_code, ticker)

    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        rs = api_client.query_history_k_data_plus(
            bs_code,
            "date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,pctChg,isST",
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            frequency="d",
            adjustflag="3",
        )

        error_code = getattr(rs, "error_code", "0")
        error_msg = getattr(rs, "error_msg", None)

        if error_code != "0":
            raise RuntimeError(
                f"baostock query_history_k_data_plus failed: code={bs_code}, "
                f"error_code={error_code}, error_msg={error_msg}"
            )

        rows: list[dict] = []
        fields = list(getattr(rs, "fields", []) or [])

        while rs.next():
            row_data = rs.get_row_data()
            row = dict(zip(fields, row_data))

            trade_date = _to_date(row.get("date"))
            if trade_date is None:
                continue

            rows.append(
                {
                    "ticker": ticker,
                    "exchange_code": exchange_code,
                    "vendor_symbol": row.get("code") or _vendor_symbol(exchange_code, ticker),
                    "trade_date": trade_date,
                    "open": _to_decimal(row.get("open")),
                    "high": _to_decimal(row.get("high")),
                    "low": _to_decimal(row.get("low")),
                    "close": _to_decimal(row.get("close")),
                    "pre_close": _to_decimal(row.get("preclose")),
                    "volume": _to_decimal(row.get("volume")),
                    "turnover": _to_decimal(row.get("amount")),
                    "amplitude": None,
                    "pct_change": _to_decimal(row.get("pctChg")),
                    "price_change": None,
                    "turnover_rate": _to_decimal(row.get("turn")),
                    "suspended_flag": False,
                    "provider_record_key": f"baostock:{exchange_code}:{ticker}:{trade_date.isoformat()}:RAW",
                    "provider_fetched_at": utc_now().isoformat(),
                }
            )

    return rows


def _query_history_k_data_plus_rows_with_reconnect(
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
            rows = _query_history_k_data_plus_rows_once(
                current_client,
                exchange_code=exchange_code,
                ticker=ticker,
                start_date=start_date,
                end_date=end_date,
            )
            return current_client, rows, reconnects_used

        except Exception as exc:  # noqa: BLE001
            last_error = exc

            if not _is_reconnectable_provider_error(str(exc)):
                raise

            if attempt >= max_attempts:
                raise

            if log_fn is not None:
                log_fn(
                    f"[WARN] baostock reconnect {attempt}/{max_attempts - 1}: "
                    f"{exchange_code}:{ticker}"
                )

            _safe_logout(current_client)
            sleep_seconds = reconnect_sleep_seconds * attempt
            time.sleep(sleep_seconds)
            current_client = _rebuild_baostock_api_client()
            reconnects_used += 1

    if last_error is not None:
        raise last_error

    return current_client, [], reconnects_used


def _normalize_daily_bar_row(
    exchange_code: str,
    ticker: str,
    row: dict,
) -> DailyBarDTO:
    trade_date = row["trade_date"]

    return DailyBarDTO(
        provider_name="baostock",
        market_code="CN_A",
        exchange_code=exchange_code,
        ticker=ticker,
        vendor_symbol=row.get("vendor_symbol"),
        trade_date=trade_date,
        price_adjust_type="RAW",
        open=row.get("open"),
        high=row.get("high"),
        low=row.get("low"),
        close=row.get("close"),
        pre_close=row.get("pre_close"),
        volume=row.get("volume"),
        turnover=row.get("turnover"),
        amplitude=row.get("amplitude"),
        pct_change=row.get("pct_change"),
        price_change=row.get("price_change"),
        turnover_rate=row.get("turnover_rate"),
        suspended_flag=bool(row.get("suspended_flag", False)),
        provider_record_key=row.get("provider_record_key"),
        raw_payload=row,
    )


def _add_quality_issue(
    sync_repo: SyncRunRepository,
    session: Session,
    *,
    data_sync_run_id: int,
    batch_id: int,
    theme_code: str,
    dataset_code: str,
    layer_code: str,
    issue_code: str,
    severity: str,
    business_key: str,
    provider_name: str | None,
    trade_date: date | None,
    symbol: str | None,
    issue_detail: dict,
) -> None:
    sync_repo.add_quality_issue(
        session,
        {
            "data_sync_run_id": data_sync_run_id,
            "batch_id": batch_id,
            "theme_code": theme_code,
            "dataset_code": dataset_code,
            "layer_code": layer_code,
            "issue_code": issue_code,
            "severity": severity,
            "business_key": business_key,
            "provider_name": provider_name,
            "trade_date": trade_date,
            "symbol": symbol,
            "record_ref": None,
            "issue_detail": issue_detail,
            "created_at": utc_now(),
        },
    )


def _flush_daily_bar_payloads(
    *,
    session: Session,
    raw_repo: RawRepository,
    stg_repo: StagingRepository,
    core_repo: CoreRepository,
    chunk_no: int,
    raw_payloads: list[dict],
    stg_payloads: list[dict],
    core_payloads: list[dict],
    raw_rows: int,
    staging_rows: int,
    core_upsert_rows: int,
) -> tuple[int, int, int]:
    pending_raw = len(raw_payloads)
    pending_stg = len(stg_payloads)
    pending_core = len(core_payloads)

    if pending_raw == 0 and pending_stg == 0 and pending_core == 0:
        return raw_rows, staging_rows, core_upsert_rows

    tqdm.write(
        f"[INFO] chunk={chunk_no} db flush start: "
        f"raw={pending_raw}, stg={pending_stg}, core={pending_core}"
    )

    raw_rows += raw_repo.bulk_upsert_raw_daily_bar(
        session,
        raw_payloads,
        chunk_size=500,
    )
    raw_payloads.clear()
    tqdm.write(f"[INFO] chunk={chunk_no} raw flush done: total_raw={raw_rows}")

    staging_rows += stg_repo.bulk_upsert_stg_daily_bar(
        session,
        stg_payloads,
        chunk_size=500,
    )
    stg_payloads.clear()
    tqdm.write(f"[INFO] chunk={chunk_no} staging flush done: total_stg={staging_rows}")

    core_upsert_rows += core_repo.bulk_upsert_daily_bar(
        session,
        core_payloads,
        chunk_size=500,
    )
    core_payloads.clear()
    tqdm.write(f"[INFO] chunk={chunk_no} core flush done: total_core={core_upsert_rows}")

    session.flush()

    return raw_rows, staging_rows, core_upsert_rows


def _guard_against_duplicate_running_batches(
    *,
    session: Session,
    sync_repo: SyncRunRepository,
    start_date: date,
    end_date: date,
    symbol_chunk_size: int,
) -> None:
    if not settings.daily_bar_running_guard_enabled:
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
    stale_threshold = timedelta(minutes=settings.daily_bar_stale_running_minutes)

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

    if settings.daily_bar_auto_fail_stale_running and stale_batches:
        batch_ids = [int(item["batch_id"]) for item in stale_batches]
        data_sync_run_ids = [int(item["data_sync_run_id"]) for item in stale_batches]

        reason = (
            "auto marked failed: stale RUNNING batch before resume; "
            f"threshold_minutes={settings.daily_bar_stale_running_minutes}"
        )

        sync_repo.mark_running_batches_failed_by_ids(
            session,
            batch_ids=batch_ids,
            data_sync_run_ids=data_sync_run_ids,
            reason=reason,
        )
        session.commit()

        tqdm.write(
            "[INFO] auto failed stale RUNNING batches: "
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
            "检测到同一区间仍有 RUNNING batch。为避免重复跑同一 chunk，本次启动已停止。"
            f" 请等待任务结束，或手工确认后标记 FAILED。active_batches=[{detail}]"
        )


def run_backfill_daily_bar_by_symbol_range(
    session: Session,
    baostock_api_client,
    run_id: int,
    data_version_id: int,
    start_date: date,
    end_date: date,
    symbol_chunk_size: int = 100,
    *,
    resume_enabled: bool = True,
    max_reconnect_attempts: int = 5,
    reconnect_sleep_seconds: float = 2.0,
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

    exchange_trade_dates_map = load_open_trade_dates_by_exchange(
        session,
        start_date=start_date,
        end_date=end_date,
        exchange_codes=("SSE", "SZSE", "BSE"),
    )

    current_api_client = baostock_api_client

    last_successful_chunk_no = 0
    if resume_enabled:
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

    start_chunk_no = last_successful_chunk_no + 1 if resume_enabled else 1

    if start_chunk_no > len(all_chunks):
        tqdm.write(
            f"[INFO] daily_bar strict backfill already completed. "
            f"last_successful_chunk_no={last_successful_chunk_no}, total_chunks={len(all_chunks)}"
        )
        _safe_logout(current_api_client)
        return

    if resume_enabled and last_successful_chunk_no > 0:
        tqdm.write(
            f"[INFO] resume enabled: skip finished chunks 1..{last_successful_chunk_no}, "
            f"continue from chunk={start_chunk_no}"
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
                    "with_auto_reconnect": True,
                    "resume_enabled": resume_enabled,
                    "flush_every_symbols": settings.daily_bar_flush_every_symbols,
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
                "batch_type": SYNC_GRANULARITY,
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
            symbols_since_last_flush = 0
            flush_every_symbols = settings.daily_bar_flush_every_symbols
            expected_trade_days_total = 0
            missing_trade_days_total = 0

            provider_success_counter = defaultdict(int)
            provider_empty_counter = defaultdict(int)
            provider_error_counter = defaultdict(int)
            missing_issue_counter = defaultdict(int)
            reconnect_counter = 0
            per_symbol_stats: list[dict] = []

            raw_payloads: list[dict] = []
            stg_payloads: list[dict] = []
            core_payloads: list[dict] = []

            progress = tqdm(
                symbol_chunk,
                desc=f"strict_backfill_daily_bar chunk={chunk_no}",
                unit="symbol",
                dynamic_ncols=True,
            )

            for item in progress:
                instrument_id = item["instrument_id"]
                exchange_code = item["exchange_code"]
                ticker = item["ticker"]
                list_date = item.get("list_date")
                delist_date = item.get("delist_date")

                current_symbol = f"{exchange_code}:{ticker}"

                progress.set_postfix(
                    current=current_symbol,
                    hit=symbols_hit,
                    input=input_rows,
                    raw=raw_rows,
                    stg=staging_rows,
                    core=core_upsert_rows,
                    warn_missing=sum(missing_issue_counter.values()),
                    reconnect=reconnect_counter,
                    err=error_rows,
                )

                symbols_attempted += 1

                expected_plan = build_expected_trade_date_plan(
                    exchange_trade_dates=exchange_trade_dates_map.get(exchange_code, []),
                    start_date=start_date,
                    end_date=end_date,
                    list_date=list_date,
                    delist_date=delist_date,
                )
                expected_trade_days_total += len(expected_plan.expected_trade_dates)


                try:
                    current_api_client, rows, reconnects_used = _query_history_k_data_plus_rows_with_reconnect(
                        current_api_client,
                        exchange_code=exchange_code,
                        ticker=ticker,
                        start_date=start_date,
                        end_date=end_date,
                        max_attempts=max_reconnect_attempts,
                        reconnect_sleep_seconds=reconnect_sleep_seconds,
                        log_fn=tqdm.write,
                    )

                    reconnect_counter += reconnects_used

                    actual_trade_dates = {row["trade_date"] for row in rows}
                    missing_trade_dates = sorted(
                        set(expected_plan.expected_trade_dates) - actual_trade_dates
                    )
                    missing_trade_days_total += len(missing_trade_dates)

                    if rows:
                        symbols_hit += 1
                        provider_success_counter["baostock"] += len(rows)
                    else:
                        provider_empty_counter["baostock"] += 1

                    if expected_plan.metadata_issue_code is not None:
                        missing_issue_counter[expected_plan.metadata_issue_code] += 1
                        _add_quality_issue(
                            sync_repo,
                            session,
                            data_sync_run_id=data_sync_run.id,
                            batch_id=batch.id,
                            theme_code=THEME_CODE,
                            dataset_code=DATASET_CODE,
                            layer_code="META",
                            issue_code=expected_plan.metadata_issue_code,
                            severity="WARN",
                            business_key=f"{exchange_code}:{ticker}:LIST_DATE",
                            provider_name=None,
                            trade_date=None,
                            symbol=ticker,
                            issue_detail={
                                **(expected_plan.metadata_issue_detail or {}),
                                "exchange_code": exchange_code,
                                "ticker": ticker,
                                "actual_trade_days": len(rows),
                            },
                        )

                    for missing_trade_date in missing_trade_dates:
                        issue_code = classify_missing_daily_bar_issue(
                            expected_trade_date=missing_trade_date,
                        )
                        missing_issue_counter[issue_code] += 1

                        _add_quality_issue(
                            sync_repo,
                            session,
                            data_sync_run_id=data_sync_run.id,
                            batch_id=batch.id,
                            theme_code=THEME_CODE,
                            dataset_code=DATASET_CODE,
                            layer_code="RAW",
                            issue_code=issue_code,
                            severity="WARN",
                            business_key=f"{exchange_code}:{ticker}:{missing_trade_date.isoformat()}",
                            provider_name=PROVIDER_NAME,
                            trade_date=missing_trade_date,
                            symbol=ticker,
                            issue_detail={
                                "expected_trade_date": missing_trade_date.isoformat(),
                                "reason": "expected_trade_date_missing_from_provider_result",
                            },
                        )

                    per_symbol_stats.append(
                        {
                            "exchange_code": exchange_code,
                            "ticker": ticker,
                            "list_date": list_date.isoformat() if list_date else None,
                            "delist_date": delist_date.isoformat() if delist_date else None,
                            "expected_trade_days": len(expected_plan.expected_trade_dates),
                            "actual_trade_days": len(rows),
                            "missing_trade_days": len(missing_trade_dates),
                            "metadata_issue_code": expected_plan.metadata_issue_code,
                            "success": True,
                        }
                    )

                    input_rows += len(rows)

                    for row in rows:
                        dto = _normalize_daily_bar_row(
                            exchange_code=exchange_code,
                            ticker=ticker,
                            row=row,
                        )

                        raw_payload = dto_to_raw_daily_bar_dict(dto, data_sync_run.id, batch.id)
                        raw_payloads.append(raw_payload)

                        stg_payload = dto_to_staging_daily_bar_dict(
                            dto=dto,
                            sync_run_id=data_sync_run.id,
                            batch_id=batch.id,
                            raw_record_id=None,
                        )
                        stg_payloads.append(stg_payload)

                        core_payload = staging_to_core_daily_bar_dict(
                            stg_row=stg_payload,
                            instrument_id=instrument_id,
                            data_version_id=data_version_id,
                        )
                        core_payloads.append(core_payload)

                except Exception as exc:  # noqa: BLE001
                    error_rows += 1
                    provider_error_counter["baostock"] += 1

                    _add_quality_issue(
                        sync_repo,
                        session,
                        data_sync_run_id=data_sync_run.id,
                        batch_id=batch.id,
                        theme_code=THEME_CODE,
                        dataset_code=DATASET_CODE,
                        layer_code="RAW",
                        issue_code="PROVIDER_QUERY_FAILED",
                        severity="ERROR",
                        business_key=f"{exchange_code}:{ticker}:{start_date.isoformat()}:{end_date.isoformat()}",
                        provider_name=PROVIDER_NAME,
                        trade_date=None,
                        symbol=ticker,
                        issue_detail={"error": _short_error_message(exc)},
                    )

                    per_symbol_stats.append(
                        {
                            "exchange_code": exchange_code,
                            "ticker": ticker,
                            "list_date": list_date.isoformat() if list_date else None,
                            "delist_date": delist_date.isoformat() if delist_date else None,
                            "expected_trade_days": len(expected_plan.expected_trade_dates),
                            "actual_trade_days": 0,
                            "missing_trade_days": len(expected_plan.expected_trade_dates),
                            "metadata_issue_code": expected_plan.metadata_issue_code,
                            "success": False,
                            "error": _short_error_message(exc),
                        }
                    )

                    tqdm.write(
                        f"[WARN] symbol failed after retries: {exchange_code}:{ticker} "
                        f"- {_short_error_message(exc)}"
                    )

                    if fail_fast:
                        raise

                symbols_since_last_flush += 1

                if symbols_since_last_flush >= flush_every_symbols:
                    raw_rows, staging_rows, core_upsert_rows = _flush_daily_bar_payloads(
                        session=session,
                        raw_repo=raw_repo,
                        stg_repo=stg_repo,
                        core_repo=core_repo,
                        chunk_no=chunk_no,
                        raw_payloads=raw_payloads,
                        stg_payloads=stg_payloads,
                        core_payloads=core_payloads,
                        raw_rows=raw_rows,
                        staging_rows=staging_rows,
                        core_upsert_rows=core_upsert_rows,
                    )
                    symbols_since_last_flush = 0

                progress.set_postfix(
                    current=current_symbol,
                    hit=symbols_hit,
                    input=input_rows,
                    raw=raw_rows,
                    stg=staging_rows,
                    core=core_upsert_rows,
                    warn_missing=sum(missing_issue_counter.values()),
                    reconnect=reconnect_counter,
                    err=error_rows,
                )

            tqdm.write(
                f"[INFO] chunk={chunk_no} fetch loop done, final db flush: "
                f"raw={len(raw_payloads)}, stg={len(stg_payloads)}, core={len(core_payloads)}"
            )

            raw_rows, staging_rows, core_upsert_rows = _flush_daily_bar_payloads(
                session=session,
                raw_repo=raw_repo,
                stg_repo=stg_repo,
                core_repo=core_repo,
                chunk_no=chunk_no,
                raw_payloads=raw_payloads,
                stg_payloads=stg_payloads,
                core_payloads=core_payloads,
                raw_rows=raw_rows,
                staging_rows=staging_rows,
                core_upsert_rows=core_upsert_rows,
            )

            strict_single_date_zero_result = (
                    start_date == end_date
                    and expected_trade_days_total > 0
                    and input_rows == 0
                    and core_upsert_rows == 0
            )

            if strict_single_date_zero_result:
                raise RuntimeError(
                    "daily_bar strict single-date backfill produced zero rows. "
                    f"trade_date={start_date.isoformat()}, "
                    f"expected_trade_days_total={expected_trade_days_total}, "
                    f"missing_trade_days_total={missing_trade_days_total}. "
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
                "missing_issue_counter": dict(missing_issue_counter),
                "reconnect_counter": reconnect_counter,
                "flush_every_symbols": flush_every_symbols,
                "per_symbol_stats_sample": per_symbol_stats[:100],
                "expected_trade_days_total": expected_trade_days_total,
                "missing_trade_days_total": missing_trade_days_total,
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
                    "missing_issue_counter": dict(missing_issue_counter),
                    "reconnect_counter": reconnect_counter,
                    "flush_every_symbols": flush_every_symbols,
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