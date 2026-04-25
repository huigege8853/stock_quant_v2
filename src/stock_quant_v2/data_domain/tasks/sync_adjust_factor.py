from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session
from tqdm import tqdm

from stock_quant_v2.config.settings import settings
from stock_quant_v2.data_domain.dto.adjust_factor import AdjustFactorDTO
from stock_quant_v2.data_domain.enums import SyncMode, SyncStatus
from stock_quant_v2.data_domain.mappers.adjust_factor_mapper import (
    dto_to_raw_adjust_factor_dict,
    dto_to_staging_adjust_factor_dict,
    staging_to_core_adjust_factor_dict,
)
from stock_quant_v2.data_domain.provider_priority import ADJUST_FACTOR_PROVIDER_PRIORITY
from stock_quant_v2.data_domain.repositories.core_repository import CoreRepository
from stock_quant_v2.data_domain.repositories.instrument_lookup_repository import InstrumentLookupRepository
from stock_quant_v2.data_domain.repositories.raw_repository import RawRepository
from stock_quant_v2.data_domain.repositories.staging_repository import StagingRepository
from stock_quant_v2.data_domain.repositories.sync_run_repository import SyncRunRepository
from stock_quant_v2.data_domain.services.provider_fallback_service import ProviderFallbackService
from stock_quant_v2.data_domain.services.universe_service import load_cn_stock_universe


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _load_adjust_factor_universe(session: Session, trade_date: date) -> list[dict]:
    return load_cn_stock_universe(session, trade_date)


def _provider_priority() -> list[str]:
    configured = settings.get_adjust_factor_provider_priority()
    if configured:
        return configured
    if isinstance(ADJUST_FACTOR_PROVIDER_PRIORITY, (list, tuple)):
        return list(ADJUST_FACTOR_PROVIDER_PRIORITY)
    return ["baostock", "akshare", "tushare", "paid", "skip"]


def _build_skipped_providers() -> dict[str, str]:
    skipped: dict[str, str] = {}
    if not settings.tushare_enabled:
        skipped["tushare"] = "disabled_by_config"
    return skipped


def _normalize_adjust_factor_row(
    provider_name: str,
    exchange_code: str,
    ticker: str,
    trade_date: date,
    row: dict,
) -> AdjustFactorDTO:
    factor = row.get("adjust_factor")
    if factor is None:
        factor = row.get("adj_factor")
    if factor is not None and not isinstance(factor, Decimal):
        factor = Decimal(str(factor))

    return AdjustFactorDTO(
        provider_name=provider_name,
        market_code="CN",
        exchange_code=exchange_code,
        ticker=ticker,
        vendor_symbol=row.get("vendor_symbol"),
        trade_date=trade_date,
        adjust_factor=factor,
        provider_record_key=(
            row.get("provider_record_key")
            or f"{provider_name}:{exchange_code}:{ticker}:{trade_date.isoformat()}"
        ),
        raw_payload=row,
    )


def _fetch_baostock_adjust_factor(
    _api_client,
    exchange_code: str,
    ticker: str,
    trade_date: date,
) -> list[AdjustFactorDTO]:
    from stock_quant_v2.data_domain.providers.baostock.client import BaoStockClient

    if _api_client is None:
        return []

    client = BaoStockClient(api_client=_api_client)
    rows = client.fetch_adjust_factor_by_symbol(
        exchange_code=exchange_code,
        ticker=ticker,
        trade_date=trade_date,
    )

    return [
        _normalize_adjust_factor_row(
            provider_name="baostock",
            exchange_code=exchange_code,
            ticker=ticker,
            trade_date=trade_date,
            row=row,
        )
        for row in rows
    ]


def _fetch_sina_adjust_factor(
    _api_client,
    exchange_code: str,
    ticker: str,
    trade_date: date,
) -> list[AdjustFactorDTO]:
    _ = _api_client, exchange_code, ticker, trade_date
    return []


def _fetch_akshare_adjust_factor(
    _api_client,
    exchange_code: str,
    ticker: str,
    trade_date: date,
) -> list[AdjustFactorDTO]:
    from stock_quant_v2.data_domain.providers.akshare.client import AkshareClient

    if _api_client is None:
        return []

    client = AkshareClient(api_client=_api_client)
    rows = client.fetch_adjust_factor_by_symbol(
        exchange_code=exchange_code,
        ticker=ticker,
        trade_date=trade_date,
    )

    return [
        _normalize_adjust_factor_row(
            provider_name="akshare",
            exchange_code=exchange_code,
            ticker=ticker,
            trade_date=trade_date,
            row=row,
        )
        for row in rows
    ]


def _fetch_pytdx_adjust_factor(
    _api_client,
    exchange_code: str,
    ticker: str,
    trade_date: date,
) -> list[AdjustFactorDTO]:
    _ = _api_client, exchange_code, ticker, trade_date
    return []


def _fetch_tushare_adjust_factor(
    _api_client,
    exchange_code: str,
    ticker: str,
    trade_date: date,
) -> list[AdjustFactorDTO]:
    from stock_quant_v2.data_domain.providers.tushare.client import TushareClient

    if _api_client is None:
        return []

    client = TushareClient(api_client=_api_client)
    rows = client.fetch_adjust_factor_by_symbol(
        exchange_code=exchange_code,
        ticker=ticker,
        trade_date=trade_date,
    )

    return [
        _normalize_adjust_factor_row(
            provider_name="tushare",
            exchange_code=exchange_code,
            ticker=ticker,
            trade_date=trade_date,
            row=row,
        )
        for row in rows
    ]


def _fetch_paid_adjust_factor(
    _api_client,
    exchange_code: str,
    ticker: str,
    trade_date: date,
) -> list[AdjustFactorDTO]:
    _ = _api_client, exchange_code, ticker, trade_date
    return []


def _build_attempts(
    baostock_api_client,
    sina_api_client,
    akshare_api_client,
    pytdx_api_client,
    tushare_api_client,
    paid_api_client,
    exchange_code: str,
    ticker: str,
    trade_date: date,
) -> list[tuple[str, Callable[[], list[AdjustFactorDTO]]]]:
    handlers: dict[str, Callable[[], list[AdjustFactorDTO]]] = {
        "baostock": lambda: _fetch_baostock_adjust_factor(
            baostock_api_client,
            exchange_code,
            ticker,
            trade_date,
        ),
        "sina": lambda: _fetch_sina_adjust_factor(
            sina_api_client,
            exchange_code,
            ticker,
            trade_date,
        ),
        "akshare": lambda: _fetch_akshare_adjust_factor(
            akshare_api_client,
            exchange_code,
            ticker,
            trade_date,
        ),
        "pytdx": lambda: _fetch_pytdx_adjust_factor(
            pytdx_api_client,
            exchange_code,
            ticker,
            trade_date,
        ),
        "tushare": lambda: _fetch_tushare_adjust_factor(
            tushare_api_client,
            exchange_code,
            ticker,
            trade_date,
        ),
        "paid": lambda: _fetch_paid_adjust_factor(
            paid_api_client,
            exchange_code,
            ticker,
            trade_date,
        ),
    }

    attempts: list[tuple[str, Callable[[], list[AdjustFactorDTO]]]] = []
    for provider_name in _provider_priority():
        if provider_name == "skip":
            continue
        handler = handlers.get(provider_name)
        if handler is not None:
            attempts.append((provider_name, handler))
    return attempts


def run_sync_adjust_factor(
    session: Session,
    baostock_api_client,
    sina_api_client,
    akshare_api_client,
    pytdx_api_client,
    tushare_api_client,
    paid_api_client,
    run_id: int,
    data_version_id: int,
    trade_date: date,
) -> None:
    sync_repo = SyncRunRepository()
    raw_repo = RawRepository()
    stg_repo = StagingRepository()
    core_repo = CoreRepository()
    instrument_repo = InstrumentLookupRepository()
    fallback_service = ProviderFallbackService()

    data_sync_run = sync_repo.create_data_sync_run(
        session,
        {
            "run_id": run_id,
            "sync_job_code": "sync_adjust_factor",
            "theme_code": "AdjustFactor",
            "dataset_code": "adjust_factor",
            "provider_name": "fallback",
            "sync_mode": SyncMode.INCREMENTAL.value,
            "sync_granularity": "DATE",
            "partition_from": trade_date,
            "partition_to": trade_date,
            "status": SyncStatus.PENDING.value,
            "cursor_json": None,
            "request_params": {
                "trade_date": trade_date.isoformat(),
                "providers": _provider_priority(),
                "debug_mode": bool(getattr(settings, "daily_bar_debug_mode", False)),
                "debug_limit_symbols": getattr(settings, "daily_bar_debug_limit_symbols", None),
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
            "batch_no": 1,
            "batch_key": trade_date.isoformat(),
            "batch_type": "DATE",
            "partition_date": trade_date,
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

        universe = _load_adjust_factor_universe(session, trade_date)

        if bool(getattr(settings, "daily_bar_debug_mode", False)):
            limit_symbols = getattr(settings, "daily_bar_debug_limit_symbols", None)
            if limit_symbols:
                universe = universe[:limit_symbols]

        input_rows = 0
        raw_rows = 0
        staging_rows = 0
        core_upsert_rows = 0
        error_rows = 0

        symbols_attempted = 0
        symbols_hit = 0

        provider_success_counter = defaultdict(int)
        provider_empty_counter = defaultdict(int)
        provider_error_counter = defaultdict(int)

        progress = tqdm(
            universe,
            desc=f"adjust_factor {trade_date.isoformat()}",
            unit="symbol",
            dynamic_ncols=True,
        )

        for item in progress:
            exchange_code = item["exchange_code"]
            ticker = item["ticker"]

            symbols_attempted += 1

            provider_attempts = _build_attempts(
                baostock_api_client=baostock_api_client,
                sina_api_client=sina_api_client,
                akshare_api_client=akshare_api_client,
                pytdx_api_client=pytdx_api_client,
                tushare_api_client=tushare_api_client,
                paid_api_client=paid_api_client,
                exchange_code=exchange_code,
                ticker=ticker,
                trade_date=trade_date,
            )
            result = fallback_service.try_providers(
                provider_attempts,
                skipped_providers=_build_skipped_providers(),
            )

            if result.success and (result.data or []):
                provider_success_counter[result.provider_name] += len(result.data or [])
            else:
                if result.provider_name:
                    if result.error:
                        provider_error_counter[result.provider_name] += 1
                    else:
                        provider_empty_counter[result.provider_name] += 1

            if not result.success:
                sync_repo.add_quality_issue(
                    session,
                    {
                        "data_sync_run_id": data_sync_run.id,
                        "batch_id": batch.id,
                        "theme_code": "AdjustFactor",
                        "dataset_code": "adjust_factor",
                        "layer_code": "RAW",
                        "issue_code": "ALL_PROVIDERS_UNAVAILABLE",
                        "severity": "WARN",
                        "business_key": f"{exchange_code}:{ticker}:{trade_date.isoformat()}",
                        "provider_name": None,
                        "trade_date": trade_date,
                        "symbol": ticker,
                        "record_ref": None,
                        "issue_detail": {"error": result.error},
                        "created_at": utc_now(),
                    },
                )
                progress.set_postfix(
                    hit=symbols_hit,
                    raw=raw_rows,
                    stg=staging_rows,
                    core=core_upsert_rows,
                    err=error_rows,
                )
                continue

            rows = result.data or []

            if rows:
                symbols_hit += 1

            input_rows += len(rows)

            for dto in rows:
                raw_payload = dto_to_raw_adjust_factor_dict(dto, data_sync_run.id, batch.id)
                raw_obj = raw_repo.upsert_raw_adjust_factor(session, raw_payload)
                raw_rows += 1

                stg_payload = dto_to_staging_adjust_factor_dict(
                    dto=dto,
                    sync_run_id=data_sync_run.id,
                    batch_id=batch.id,
                    raw_record_id=raw_obj.id,
                )
                stg_obj = stg_repo.upsert_stg_adjust_factor(session, stg_payload)
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
                            "theme_code": "AdjustFactor",
                            "dataset_code": "adjust_factor",
                            "layer_code": "CORE",
                            "issue_code": "INSTRUMENT_NOT_FOUND",
                            "severity": "ERROR",
                            "business_key": f'{stg_payload["ticker"]}:{stg_payload["trade_date"]}',
                            "provider_name": stg_payload["provider_name"],
                            "trade_date": stg_payload["trade_date"],
                            "symbol": stg_payload["ticker"],
                            "record_ref": {"stg_id": stg_obj.id},
                            "issue_detail": {"exchange_code": stg_payload["exchange_code"]},
                            "created_at": utc_now(),
                        },
                    )
                    continue

                core_payload = staging_to_core_adjust_factor_dict(
                    stg_row=stg_payload,
                    instrument_id=instrument_id,
                    data_version_id=data_version_id,
                )
                core_repo.upsert_adjust_factor(session, core_payload)
                core_upsert_rows += 1

            progress.set_postfix(
                hit=symbols_hit,
                raw=raw_rows,
                stg=staging_rows,
                core=core_upsert_rows,
                err=error_rows,
            )

        batch_status = SyncStatus.SUCCESS.value if error_rows == 0 else SyncStatus.PARTIAL.value

        checkpoint_json = {
            "trade_date": trade_date.isoformat(),
            "symbols_attempted": symbols_attempted,
            "symbols_hit": symbols_hit,
            "provider_success_counter": dict(provider_success_counter),
            "provider_empty_counter": dict(provider_empty_counter),
            "provider_error_counter": dict(provider_error_counter),
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
                "trade_date": trade_date.isoformat(),
                "symbols_attempted": symbols_attempted,
                "symbols_hit": symbols_hit,
                "input_rows": input_rows,
                "raw_rows": raw_rows,
                "staging_rows": staging_rows,
                "core_upsert_rows": core_upsert_rows,
                "error_rows": error_rows,
            },
        )
        session.commit()

    except Exception as exc:  # noqa: BLE001
        session.rollback()
        try:
            sync_repo.add_quality_issue(
                session,
                {
                    "data_sync_run_id": data_sync_run.id,
                    "batch_id": batch.id,
                    "theme_code": "AdjustFactor",
                    "dataset_code": "adjust_factor",
                    "layer_code": "STAGING",
                    "issue_code": "UNHANDLED_EXCEPTION",
                    "severity": "ERROR",
                    "business_key": trade_date.isoformat(),
                    "provider_name": None,
                    "trade_date": trade_date,
                    "symbol": None,
                    "record_ref": None,
                    "issue_detail": {"error": str(exc)},
                    "created_at": utc_now(),
                },
            )
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