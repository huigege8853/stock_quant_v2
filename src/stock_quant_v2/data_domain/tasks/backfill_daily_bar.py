from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
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
from stock_quant_v2.data_domain.repositories.raw_repository import RawRepository
from stock_quant_v2.data_domain.repositories.staging_repository import StagingRepository
from stock_quant_v2.data_domain.repositories.sync_run_repository import SyncRunRepository
from stock_quant_v2.data_domain.services.backfill_calendar_service import load_open_trade_dates
from stock_quant_v2.data_domain.services.instrument_map_service import (
    load_instrument_id_map,
    lookup_instrument_id,
)
from stock_quant_v2.data_domain.services.provider_backfill_service import (
    BackfillFetchResult,
    run_concurrent_symbol_fetch,
)
from stock_quant_v2.data_domain.services.provider_fallback_service import ProviderFallbackService
from stock_quant_v2.data_domain.services.universe_service import load_cn_stock_universe


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


def _fetch_symbol_daily_bar(
    *,
    fallback_service: ProviderFallbackService,
    baostock_api_client,
    sina_api_client,
    akshare_api_client,
    tushare_api_client,
    trade_date: date,
    item: dict,
) -> BackfillFetchResult:
    exchange_code = item["exchange_code"]
    ticker = item["ticker"]

    provider_attempts = []
    for provider_name in _provider_priority():
        if provider_name == "skip":
            continue

        if provider_name == "baostock":
            provider_attempts.append(
                ("baostock", lambda: _fetch_baostock_daily_bar(baostock_api_client, exchange_code, ticker, trade_date))
            )
        elif provider_name == "sina":
            provider_attempts.append(
                ("sina", lambda: _fetch_sina_daily_bar(sina_api_client, exchange_code, ticker, trade_date))
            )
        elif provider_name == "akshare":
            provider_attempts.append(
                ("akshare", lambda: _fetch_akshare_daily_bar(akshare_api_client, exchange_code, ticker, trade_date))
            )
        elif provider_name == "tushare":
            provider_attempts.append(
                ("tushare", lambda: _fetch_tushare_daily_bar(tushare_api_client, exchange_code, ticker, trade_date))
            )
        elif provider_name == "pytdx":
            provider_attempts.append(("pytdx", lambda: []))
        elif provider_name == "paid":
            provider_attempts.append(("paid", lambda: []))

    result = fallback_service.try_providers(
        provider_attempts,
        skipped_providers=_build_skipped_providers(),
    )

    return BackfillFetchResult(
        exchange_code=exchange_code,
        ticker=ticker,
        provider_name=result.provider_name,
        success=result.success,
        rows=[dto.__dict__ for dto in (result.data or [])],
        error=result.error,
    )


def _date_range_chunks(open_dates: list[date], chunk_days: int) -> list[list[date]]:
    chunk_days = max(int(chunk_days), 1)
    return [open_dates[i:i + chunk_days] for i in range(0, len(open_dates), chunk_days)]


def run_backfill_daily_bar(
    session: Session,
    baostock_api_client,
    tushare_api_client,
    sina_api_client,
    akshare_api_client,
    run_id: int,
    data_version_id: int,
    start_date: date,
    end_date: date,
    chunk_days: int = 5,
    max_workers: int = 12,
) -> None:
    sync_repo = SyncRunRepository()
    raw_repo = RawRepository()
    stg_repo = StagingRepository()
    core_repo = CoreRepository()
    fallback_service = ProviderFallbackService()

    open_dates = load_open_trade_dates(
        session,
        start_date=start_date,
        end_date=end_date,
        exchange_codes=("SSE", "SZSE", "BSE"),
    )
    if not open_dates:
        return

    instrument_id_map = load_instrument_id_map(session, market_code="CN_A")
    date_chunks = _date_range_chunks(open_dates, chunk_days)

    for chunk_no, chunk_dates in enumerate(date_chunks, start=1):
        chunk_start = chunk_dates[0]
        chunk_end = chunk_dates[-1]

        data_sync_run = sync_repo.create_data_sync_run(
            session,
            {
                "run_id": run_id,
                "sync_job_code": "backfill_daily_bar",
                "theme_code": "DailyBar",
                "dataset_code": "daily_bar",
                "provider_name": "fallback",
                "sync_mode": SyncMode.FULL.value,
                "sync_granularity": "DATE_RANGE",
                "partition_from": chunk_start,
                "partition_to": chunk_end,
                "status": SyncStatus.PENDING.value,
                "cursor_json": {
                    "chunk_no": chunk_no,
                    "chunk_start": chunk_start.isoformat(),
                    "chunk_end": chunk_end.isoformat(),
                },
                "request_params": {
                    "start_date": chunk_start.isoformat(),
                    "end_date": chunk_end.isoformat(),
                    "execution_mode": "BACKFILL",
                    "providers": _provider_priority(),
                    "chunk_days": chunk_days,
                    "max_workers": max_workers,
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
                "batch_key": f"{chunk_start.isoformat()}:{chunk_end.isoformat()}",
                "batch_type": "DATE_RANGE",
                "partition_date": chunk_start,
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

            provider_success_counter: dict[str, int] = defaultdict(int)
            provider_empty_counter: dict[str, int] = defaultdict(int)
            provider_error_counter: dict[str, int] = defaultdict(int)
            per_day_stats: list[dict] = []

            progress = tqdm(
                chunk_dates,
                desc=f"backfill_daily_bar {chunk_start.isoformat()}~{chunk_end.isoformat()}",
                unit="day",
                dynamic_ncols=True,
            )

            for trade_date in progress:
                universe = load_cn_stock_universe(session, trade_date)

                def _worker(item: dict) -> BackfillFetchResult:
                    return _fetch_symbol_daily_bar(
                        fallback_service=fallback_service,
                        baostock_api_client=baostock_api_client,
                        sina_api_client=sina_api_client,
                        akshare_api_client=akshare_api_client,
                        tushare_api_client=tushare_api_client,
                        trade_date=trade_date,
                        item=item,
                    )

                results, day_success, day_empty, day_error = run_concurrent_symbol_fetch(
                    items=universe,
                    worker_fn=_worker,
                    max_workers=max_workers,
                )

                for k, v in day_success.items():
                    provider_success_counter[k] += v
                for k, v in day_empty.items():
                    provider_empty_counter[k] += v
                for k, v in day_error.items():
                    provider_error_counter[k] += v

                raw_payloads: list[dict] = []
                stg_payloads: list[dict] = []
                core_payloads: list[dict] = []

                day_input_rows = 0
                day_hit_symbols = 0
                day_error_rows = 0

                for result in results:
                    if not result.rows:
                        continue

                    day_hit_symbols += 1
                    day_input_rows += len(result.rows)

                    for row in result.rows:
                        dto = DailyBarDTO(
                            provider_name=str(row["provider_name"]),
                            market_code=str(row["market_code"]),
                            exchange_code=str(row["exchange_code"]),
                            ticker=str(row["ticker"]),
                            vendor_symbol=row.get("vendor_symbol"),
                            trade_date=row["trade_date"],
                            price_adjust_type=str(row["price_adjust_type"]),
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
                            provider_record_key=str(row["provider_record_key"]),
                            raw_payload=row,
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

                        instrument_id = lookup_instrument_id(
                            instrument_id_map,
                            exchange_code=stg_payload["exchange_code"],
                            ticker=stg_payload["ticker"],
                        )
                        if instrument_id is None:
                            day_error_rows += 1
                            continue

                        core_payload = staging_to_core_daily_bar_dict(
                            stg_row=stg_payload,
                            instrument_id=instrument_id,
                            data_version_id=data_version_id,
                        )
                        core_payloads.append(core_payload)

                raw_rows += raw_repo.bulk_upsert_raw_daily_bar(session, raw_payloads, chunk_size=500)
                staging_rows += stg_repo.bulk_upsert_stg_daily_bar(session, stg_payloads, chunk_size=200)
                core_upsert_rows += core_repo.bulk_upsert_daily_bar(session, core_payloads, chunk_size=500)

                input_rows += day_input_rows
                error_rows += day_error_rows

                per_day_stats.append(
                    {
                        "trade_date": trade_date.isoformat(),
                        "universe_size": len(universe),
                        "hit_symbols": day_hit_symbols,
                        "input_rows": day_input_rows,
                        "raw_rows": len(raw_payloads),
                        "staging_rows": len(stg_payloads),
                        "core_rows": len(core_payloads),
                        "error_rows": day_error_rows,
                    }
                )

                progress.set_postfix(
                    input=input_rows,
                    raw=raw_rows,
                    stg=staging_rows,
                    core=core_upsert_rows,
                    err=error_rows,
                )

            batch_status = SyncStatus.SUCCESS.value if error_rows == 0 else SyncStatus.PARTIAL.value

            checkpoint_json = {
                "chunk_no": chunk_no,
                "chunk_start": chunk_start.isoformat(),
                "chunk_end": chunk_end.isoformat(),
                "provider_success_counter": dict(provider_success_counter),
                "provider_empty_counter": dict(provider_empty_counter),
                "provider_error_counter": dict(provider_error_counter),
                "per_day_stats": per_day_stats,
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
                    "chunk_no": chunk_no,
                    "start_date": chunk_start.isoformat(),
                    "end_date": chunk_end.isoformat(),
                    "input_rows": input_rows,
                    "raw_rows": raw_rows,
                    "staging_rows": staging_rows,
                    "core_upsert_rows": core_upsert_rows,
                    "error_rows": error_rows,
                    "provider_success_counter": dict(provider_success_counter),
                    "provider_empty_counter": dict(provider_empty_counter),
                    "provider_error_counter": dict(provider_error_counter),
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
                    {"error": str(exc), "chunk_no": chunk_no},
                )
                session.commit()
            except Exception:
                session.rollback()
            raise