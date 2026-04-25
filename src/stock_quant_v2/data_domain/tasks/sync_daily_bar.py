from __future__ import annotations

import time
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal

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
from stock_quant_v2.data_domain.provider_priority import DAILY_BAR_PROVIDER_PRIORITY
from stock_quant_v2.data_domain.providers.akshare.client import AkshareClient
from stock_quant_v2.data_domain.providers.baostock.client import BaoStockClient
from stock_quant_v2.data_domain.providers.sina.client import SinaClient
from stock_quant_v2.data_domain.providers.tushare.client import TushareClient
from stock_quant_v2.data_domain.repositories.core_repository import CoreRepository
from stock_quant_v2.data_domain.repositories.instrument_lookup_repository import InstrumentLookupRepository
from stock_quant_v2.data_domain.repositories.raw_repository import RawRepository
from stock_quant_v2.data_domain.repositories.staging_repository import StagingRepository
from stock_quant_v2.data_domain.repositories.sync_run_repository import SyncRunRepository
from stock_quant_v2.data_domain.services.provider_fallback_service import ProviderFallbackService
from stock_quant_v2.data_domain.services.universe_service import load_cn_stock_universe


def _serialize_attempt_detail_list(attempts) -> list[dict]:
    rows: list[dict] = []
    for attempt in attempts or []:
        rows.append(
            {
                "provider_name": getattr(attempt, "provider_name", None),
                "success": getattr(attempt, "success", None),
                "row_count": getattr(attempt, "row_count", None),
                "error": getattr(attempt, "error", None),
                "skipped": getattr(attempt, "skipped", False),
                "skipped_reason": getattr(attempt, "skipped_reason", None),
            }
        )
    return rows


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _provider_priority() -> list[str]:
    configured = settings.get_daily_bar_provider_priority()
    if configured:
        return configured
    if isinstance(DAILY_BAR_PROVIDER_PRIORITY, (list, tuple)):
        return list(DAILY_BAR_PROVIDER_PRIORITY)
    return ["baostock", "sina", "akshare", "pytdx", "tushare", "paid", "skip"]


def _build_skipped_providers() -> dict[str, str]:
    skipped: dict[str, str] = {}
    if not settings.tushare_enabled:
        skipped["tushare"] = "disabled_by_config"
    return skipped


def _is_reconnectable_provider_error(message: str | None) -> bool:
    if not message:
        return False

    text = str(message).lower()
    keywords = [
        "10054",
        "接收数据异常",
        "远程主机强迫关闭了一个现有的连接",
        "forcibly closed",
        "connection aborted",
        "connection reset",
        "broken pipe",
        "socket",
        "please reconnect",
        "query_history_k_data_plus failed",
    ]
    return any(keyword.lower() in text for keyword in keywords)


def _normalize_daily_bar_row(
    provider_name: str,
    exchange_code: str,
    ticker: str,
    trade_date: date,
    row: dict,
) -> DailyBarDTO:
    return DailyBarDTO(
        provider_name=provider_name,
        market_code="CN_A",
        exchange_code=exchange_code,
        ticker=ticker,
        vendor_symbol=row.get("vendor_symbol") or row.get("ts_code"),
        trade_date=trade_date,
        price_adjust_type="RAW",
        open=Decimal(str(row["open"])) if row.get("open") is not None else None,
        high=Decimal(str(row["high"])) if row.get("high") is not None else None,
        low=Decimal(str(row["low"])) if row.get("low") is not None else None,
        close=Decimal(str(row["close"])) if row.get("close") is not None else None,
        pre_close=Decimal(str(row["pre_close"])) if row.get("pre_close") is not None else None,
        volume=Decimal(str(row["volume"])) if row.get("volume") is not None else None,
        turnover=Decimal(str(row["turnover"])) if row.get("turnover") is not None else None,
        amplitude=Decimal(str(row["amplitude"])) if row.get("amplitude") is not None else None,
        pct_change=Decimal(str(row["pct_change"])) if row.get("pct_change") is not None else None,
        price_change=Decimal(str(row["price_change"])) if row.get("price_change") is not None else None,
        turnover_rate=Decimal(str(row["turnover_rate"])) if row.get("turnover_rate") is not None else None,
        suspended_flag=bool(row.get("suspended_flag", False)),
        provider_record_key=row.get("provider_record_key") or f"{ticker}:{trade_date.isoformat()}:RAW",
        raw_payload=row,
    )


def _fetch_baostock_daily_bar(api_client, exchange_code: str, ticker: str, trade_date: date) -> list[DailyBarDTO]:
    if api_client is None:
        return []
    client = BaoStockClient(api_client=api_client)
    rows = client.fetch_daily_bar_by_symbol(
        exchange_code=exchange_code,
        ticker=ticker,
        trade_date=trade_date,
    )
    return [
        _normalize_daily_bar_row(
            provider_name="baostock",
            exchange_code=exchange_code,
            ticker=ticker,
            trade_date=trade_date,
            row=row,
        )
        for row in rows
    ]


def _fetch_sina_daily_bar(api_client, exchange_code: str, ticker: str, trade_date: date) -> list[DailyBarDTO]:
    if api_client is None:
        return []
    client = SinaClient(api_client=api_client)
    rows = client.fetch_daily_bar_by_symbol(
        exchange_code=exchange_code,
        ticker=ticker,
        trade_date=trade_date,
    )
    return [
        _normalize_daily_bar_row(
            provider_name="sina",
            exchange_code=exchange_code,
            ticker=ticker,
            trade_date=trade_date,
            row=row,
        )
        for row in rows
    ]


def _fetch_akshare_daily_bar(api_client, exchange_code: str, ticker: str, trade_date: date) -> list[DailyBarDTO]:
    if api_client is None:
        return []
    client = AkshareClient(api_client=api_client)
    rows = client.fetch_daily_bar_by_symbol(
        exchange_code=exchange_code,
        ticker=ticker,
        trade_date=trade_date,
    )
    return [
        _normalize_daily_bar_row(
            provider_name="akshare",
            exchange_code=exchange_code,
            ticker=ticker,
            trade_date=trade_date,
            row=row,
        )
        for row in rows
    ]


def _fetch_tushare_daily_bar(api_client, exchange_code: str, ticker: str, trade_date: date) -> list[DailyBarDTO]:
    if api_client is None:
        return []
    client = TushareClient(api_client=api_client)
    rows = client.fetch_daily_bar_by_symbol(
        exchange_code=exchange_code,
        ticker=ticker,
        trade_date=trade_date,
    )
    return [
        _normalize_daily_bar_row(
            provider_name="tushare",
            exchange_code=exchange_code,
            ticker=ticker,
            trade_date=trade_date,
            row=row,
        )
        for row in rows
    ]


def _build_daily_bar_provider_attempts(
    baostock_api_client,
    sina_api_client,
    akshare_api_client,
    pytdx_api_client,
    tushare_api_client,
    paid_api_client,
    exchange_code: str,
    ticker: str,
    trade_date: date,
):
    _ = pytdx_api_client, paid_api_client

    handlers = {
        "baostock": lambda: _fetch_baostock_daily_bar(baostock_api_client, exchange_code, ticker, trade_date),
        "sina": lambda: _fetch_sina_daily_bar(sina_api_client, exchange_code, ticker, trade_date),
        "akshare": lambda: _fetch_akshare_daily_bar(akshare_api_client, exchange_code, ticker, trade_date),
        "pytdx": lambda: [],
        "tushare": lambda: _fetch_tushare_daily_bar(tushare_api_client, exchange_code, ticker, trade_date),
        "paid": lambda: [],
    }

    attempts = []
    for provider_name in _provider_priority():
        if provider_name == "skip":
            continue
        handler = handlers.get(provider_name)
        if handler is not None:
            attempts.append((provider_name, handler))
    return attempts


def _fetch_daily_bar_with_retry(
    *,
    fallback_service: ProviderFallbackService,
    baostock_api_client,
    sina_api_client,
    akshare_api_client,
    tushare_api_client,
    exchange_code: str,
    ticker: str,
    trade_date: date,
    max_attempts: int = 3,
    request_sleep_seconds: float = 0.05,
    retry_sleep_seconds: float = 0.3,
):
    last_result = None

    for attempt in range(1, max_attempts + 1):
        provider_attempts = _build_daily_bar_provider_attempts(
            baostock_api_client=baostock_api_client,
            sina_api_client=sina_api_client,
            akshare_api_client=akshare_api_client,
            pytdx_api_client=None,
            tushare_api_client=tushare_api_client,
            paid_api_client=None,
            exchange_code=exchange_code,
            ticker=ticker,
            trade_date=trade_date,
        )

        result = fallback_service.try_providers(
            provider_attempts,
            skipped_providers=_build_skipped_providers(),
        )
        last_result = result

        time.sleep(request_sleep_seconds)

        if result.success:
            return result

        if not _is_reconnectable_provider_error(result.error):
            return result

        if attempt < max_attempts:
            time.sleep(retry_sleep_seconds)

    return last_result


def run_sync_daily_bar(
    session: Session,
    baostock_api_client,
    tushare_api_client,
    sina_api_client,
    akshare_api_client,
    run_id: int,
    data_version_id: int,
    start_date: date,
    end_date: date,
    _provider_name: str = "fallback",
) -> None:
    sync_repo = SyncRunRepository()
    raw_repo = RawRepository()
    stg_repo = StagingRepository()
    core_repo = CoreRepository()
    instrument_repo = InstrumentLookupRepository()
    fallback_service = ProviderFallbackService()

    current_date = start_date
    batch_no = 0

    while current_date <= end_date:
        batch_no += 1

        data_sync_run = sync_repo.create_data_sync_run(
            session,
            {
                "run_id": run_id,
                "sync_job_code": "sync_daily_bar",
                "theme_code": "DailyBar",
                "dataset_code": "daily_bar",
                "provider_name": _provider_name,
                "sync_mode": SyncMode.INCREMENTAL.value,
                "sync_granularity": "DATE",
                "partition_from": current_date,
                "partition_to": current_date,
                "status": SyncStatus.PENDING.value,
                "cursor_json": None,
                "request_params": {
                    "trade_date": current_date.isoformat(),
                    "providers": _provider_priority(),
                    "debug_mode": bool(getattr(settings, "daily_bar_debug_mode", False)),
                    "debug_limit_symbols": getattr(settings, "daily_bar_debug_limit_symbols", None),
                    "symbol_retry_max_attempts": 3,
                    "request_sleep_seconds": 0.05,
                    "retry_sleep_seconds": 0.3,
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
                "batch_no": batch_no,
                "batch_key": current_date.isoformat(),
                "batch_type": "DATE",
                "partition_date": current_date,
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

            universe = load_cn_stock_universe(session, current_date)

            if bool(getattr(settings, "daily_bar_debug_mode", False)):
                limit_symbols = getattr(settings, "daily_bar_debug_limit_symbols", None)
                if limit_symbols:
                    universe = universe[:limit_symbols]

            input_rows = 0
            raw_rows = 0
            staging_rows = 0
            core_upsert_rows = 0
            error_rows = 0
            skipped_batches = 0

            provider_success_counter = defaultdict(int)
            provider_empty_counter = defaultdict(int)
            provider_error_counter = defaultdict(int)

            attempt_log_sample: list[dict] = []

            progress = tqdm(
                universe,
                desc=f"daily_bar {current_date.isoformat()}",
                unit="symbol",
                dynamic_ncols=True,
            )

            for item in progress:
                exchange_code = item["exchange_code"]
                ticker = item["ticker"]

                result = _fetch_daily_bar_with_retry(
                    fallback_service=fallback_service,
                    baostock_api_client=baostock_api_client,
                    sina_api_client=sina_api_client,
                    akshare_api_client=akshare_api_client,
                    tushare_api_client=tushare_api_client,
                    exchange_code=exchange_code,
                    ticker=ticker,
                    trade_date=current_date,
                    max_attempts=3,
                    request_sleep_seconds=0.05,
                    retry_sleep_seconds=0.3,
                )

                if result.success and (result.data or []):
                    provider_success_counter[result.provider_name] += len(result.data or [])
                else:
                    if result.provider_name:
                        if result.error:
                            provider_error_counter[result.provider_name] += 1
                        else:
                            provider_empty_counter[result.provider_name] += 1

                if len(attempt_log_sample) < 100:
                    attempt_log_sample.append(
                        {
                            "exchange_code": exchange_code,
                            "ticker": ticker,
                            "selected_provider": result.provider_name,
                            "success": result.success,
                            "row_count": len(result.data or []),
                            "attempts": _serialize_attempt_detail_list(result.attempts),
                            "error": result.error,
                        }
                    )

                rows = result.data or []
                if not rows:
                    progress.set_postfix(
                        success=sum(provider_success_counter.values()),
                        empty=sum(provider_empty_counter.values()),
                        failed=sum(provider_error_counter.values()),
                    )
                    continue

                input_rows += len(rows)

                for dto in rows:
                    try:
                        raw_payload = dto_to_raw_daily_bar_dict(dto, data_sync_run.id, batch.id)
                        raw_obj = raw_repo.upsert_raw_daily_bar(session, raw_payload)
                        raw_rows += 1

                        stg_payload = dto_to_staging_daily_bar_dict(
                            dto=dto,
                            sync_run_id=data_sync_run.id,
                            batch_id=batch.id,
                            raw_record_id=raw_obj.id,
                        )
                        stg_obj = stg_repo.upsert_stg_daily_bar(session, stg_payload)
                        staging_rows += 1

                        instrument_id = instrument_repo.get_instrument_id(
                            session=session,
                            market_code=stg_payload["market_code"],
                            exchange_code=stg_payload["exchange_code"],
                            ticker=stg_payload["ticker"],
                        )
                        if instrument_id is None:
                            error_rows += 1
                            sync_repo.add_quality_issue(
                                session,
                                {
                                    "data_sync_run_id": data_sync_run.id,
                                    "batch_id": batch.id,
                                    "theme_code": "DailyBar",
                                    "dataset_code": "daily_bar",
                                    "layer_code": "CORE",
                                    "issue_code": "INSTRUMENT_NOT_FOUND",
                                    "severity": "ERROR",
                                    "business_key": f'{stg_payload["ticker"]}:{stg_payload["trade_date"]}:{stg_payload["price_adjust_type"]}',
                                    "provider_name": stg_payload["provider_name"],
                                    "trade_date": stg_payload["trade_date"],
                                    "symbol": stg_payload["ticker"],
                                    "record_ref": {"stg_id": stg_obj.id},
                                    "issue_detail": {"exchange_code": stg_payload["exchange_code"]},
                                    "created_at": utc_now(),
                                },
                            )
                            continue

                        core_payload = staging_to_core_daily_bar_dict(
                            stg_row=stg_payload,
                            instrument_id=instrument_id,
                            data_version_id=data_version_id,
                        )
                        core_repo.upsert_daily_bar(session, core_payload)
                        core_upsert_rows += 1

                    except Exception as exc:  # noqa: BLE001
                        error_rows += 1
                        sync_repo.add_quality_issue(
                            session,
                            {
                                "data_sync_run_id": data_sync_run.id,
                                "batch_id": batch.id,
                                "theme_code": "DailyBar",
                                "dataset_code": "daily_bar",
                                "layer_code": "STAGING",
                                "issue_code": "UNHANDLED_EXCEPTION",
                                "severity": "ERROR",
                                "business_key": f"{exchange_code}:{ticker}:{current_date.isoformat()}",
                                "provider_name": result.provider_name,
                                "trade_date": current_date,
                                "symbol": ticker,
                                "record_ref": None,
                                "issue_detail": {"error": str(exc)},
                                "created_at": utc_now(),
                            },
                        )

                progress.set_postfix(
                    success=sum(provider_success_counter.values()),
                    empty=sum(provider_empty_counter.values()),
                    failed=sum(provider_error_counter.values()),
                )

            batch_status = SyncStatus.SUCCESS.value if error_rows == 0 else SyncStatus.PARTIAL.value

            checkpoint_json = {
                "provider_success_counter": dict(provider_success_counter),
                "provider_empty_counter": dict(provider_empty_counter),
                "provider_error_counter": dict(provider_error_counter),
                "attempt_log_sample": attempt_log_sample,
                "attempt_log_total": len(attempt_log_sample),
                "universe_size": len(universe),
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
                    "input_rows": input_rows,
                    "raw_rows": raw_rows,
                    "staging_rows": staging_rows,
                    "core_upsert_rows": core_upsert_rows,
                    "error_rows": error_rows,
                    "skipped_batches": skipped_batches,
                    "provider_success_counter": dict(provider_success_counter),
                    "provider_empty_counter": dict(provider_empty_counter),
                    "provider_error_counter": dict(provider_error_counter),
                    "tushare_cache_dates": [],
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
                    error_message=str(exc),
                )
                sync_repo.mark_data_sync_run_finished(
                    session,
                    data_sync_run,
                    SyncStatus.FAILED.value,
                    {"error": str(exc)},
                )
                session.commit()
            except Exception:
                session.rollback()
            raise

        current_date = date.fromordinal(current_date.toordinal() + 1)