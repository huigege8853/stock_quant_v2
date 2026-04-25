from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_quant_v2.config.settings import settings
from stock_quant_v2.data_domain.enums import SyncMode, SyncStatus
from stock_quant_v2.data_domain.provider_priority import TRADING_CALENDAR_PROVIDER_PRIORITY
from stock_quant_v2.data_domain.providers.baostock.client import BaoStockClient
from stock_quant_v2.data_domain.providers.tushare.client import TushareClient
from stock_quant_v2.data_domain.repositories.sync_run_repository import SyncRunRepository
from stock_quant_v2.data_domain.services.provider_fallback_service import ProviderFallbackService
from stock_quant_v2.db.models.meta.exchange import MetaExchange
from stock_quant_v2.db.models.meta.trading_calendar import MetaTradingCalendar


def _get_exchange_id(session: Session, exchange_code: str) -> int | None:
    stmt = select(MetaExchange.id).where(MetaExchange.exchange_code == exchange_code)
    return session.execute(stmt).scalar_one_or_none()


def _upsert_trading_calendar(session: Session, row: dict) -> MetaTradingCalendar:
    exchange_id = _get_exchange_id(session, row["exchange_code"])
    if exchange_id is None:
        raise ValueError(f"exchange_code not found: {row['exchange_code']}")

    stmt = select(MetaTradingCalendar).where(
        MetaTradingCalendar.exchange_id == exchange_id,
        MetaTradingCalendar.trade_date == row["trade_date"],
    )
    existing = session.execute(stmt).scalar_one_or_none()

    payload = {
        "exchange_id": exchange_id,
        "trade_date": row["trade_date"],
        "is_open": row["is_open"],
        "previous_trade_date": row.get("previous_trade_date"),
        "next_trade_date": row.get("next_trade_date"),
        "updated_at": datetime.utcnow(),
    }

    if existing is not None:
        for key, value in payload.items():
            if hasattr(existing, key):
                setattr(existing, key, value)
        session.flush()
        return existing

    obj = MetaTradingCalendar(**payload, created_at=datetime.utcnow())
    session.add(obj)
    session.flush()
    return obj


def _provider_priority() -> list[str]:
    configured = settings.get_trading_calendar_provider_priority()
    if configured:
        return configured
    if isinstance(TRADING_CALENDAR_PROVIDER_PRIORITY, (list, tuple)):
        return list(TRADING_CALENDAR_PROVIDER_PRIORITY)
    return ["baostock", "tushare", "akshare", "paid", "skip"]


def _build_trading_calendar_provider_attempts(
    baostock_api_client,
    tushare_api_client,
    akshare_api_client,
    exchange_code: str,
    start_date: date,
    end_date: date,
) -> list[tuple[str, callable]]:
    _ = akshare_api_client

    handlers = {
        "baostock": lambda: BaoStockClient(api_client=baostock_api_client).fetch_trading_calendar(
            exchange_code=exchange_code,
            start_date=start_date,
            end_date=end_date,
        ),
        "tushare": lambda: TushareClient(api_client=tushare_api_client).fetch_trading_calendar(
            exchange_code=exchange_code,
            start_date=start_date,
            end_date=end_date,
        ),
        "akshare": lambda: [],
        "paid": lambda: [],
    }

    attempts: list[tuple[str, callable]] = []
    for provider_name in _provider_priority():
        if provider_name == "skip":
            continue
        handler = handlers.get(provider_name)
        if handler is not None:
            attempts.append((provider_name, handler))
    return attempts


def _build_skipped_providers() -> dict[str, str]:
    skipped: dict[str, str] = {}
    if not settings.tushare_enabled:
        skipped["tushare"] = "disabled_by_config"
    return skipped


def run_sync_trading_calendar(
    session: Session,
    baostock_api_client,
    tushare_api_client,
    akshare_api_client,
    run_id: int,
    start_date: date,
    end_date: date,
    exchanges: tuple[str, ...] = ("SSE", "SZSE", "BSE"),
) -> None:
    sync_repo = SyncRunRepository()
    fallback_service = ProviderFallbackService()

    data_sync_run = sync_repo.create_data_sync_run(
        session,
        {
            "run_id": run_id,
            "sync_job_code": "sync_trading_calendar",
            "theme_code": "TradingCalendar",
            "dataset_code": "trading_calendar",
            "provider_name": "fallback",
            "sync_mode": SyncMode.FULL.value,
            "sync_granularity": "EXCHANGE",
            "partition_from": start_date,
            "partition_to": end_date,
            "status": SyncStatus.PENDING.value,
            "cursor_json": None,
            "request_params": {
                "providers": _provider_priority(),
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "exchanges": list(exchanges),
            },
            "stats_json": None,
            "started_at": None,
            "finished_at": None,
        },
    )
    session.commit()

    sync_repo.mark_data_sync_run_running(session, data_sync_run)
    session.commit()

    total_input_rows = 0
    total_upsert_rows = 0
    total_error_rows = 0
    skipped_batches = 0
    batch_no = 0

    try:
        for exchange_code in exchanges:
            batch_no += 1
            batch = sync_repo.create_data_batch(
                session,
                {
                    "data_sync_run_id": data_sync_run.id,
                    "batch_no": batch_no,
                    "batch_key": f"{exchange_code}:{start_date.isoformat()}:{end_date.isoformat()}",
                    "batch_type": "EXCHANGE",
                    "partition_date": None,
                    "partition_symbol": exchange_code,
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

            try:
                sync_repo.mark_data_batch_running(session, batch)
                session.commit()

                provider_attempts = _build_trading_calendar_provider_attempts(
                    baostock_api_client=baostock_api_client,
                    tushare_api_client=tushare_api_client,
                    akshare_api_client=akshare_api_client,
                    exchange_code=exchange_code,
                    start_date=start_date,
                    end_date=end_date,
                )

                result = fallback_service.try_providers(
                    provider_attempts,
                    skipped_providers=_build_skipped_providers(),
                )

                if not result.success:
                    skipped_batches += 1
                    sync_repo.add_quality_issue(
                        session,
                        {
                            "data_sync_run_id": data_sync_run.id,
                            "batch_id": batch.id,
                            "theme_code": "TradingCalendar",
                            "dataset_code": "trading_calendar",
                            "layer_code": "RAW",
                            "issue_code": "ALL_PROVIDERS_UNAVAILABLE",
                            "severity": "WARN",
                            "business_key": f"{exchange_code}:{start_date}:{end_date}",
                            "provider_name": None,
                            "trade_date": None,
                            "symbol": exchange_code,
                            "record_ref": None,
                            "issue_detail": {"error": result.error},
                            "created_at": datetime.utcnow(),
                        },
                    )
                    sync_repo.mark_data_batch_finished(
                        session,
                        batch,
                        SyncStatus.SKIPPED.value,
                        input_rows=0,
                        raw_rows=0,
                        staging_rows=0,
                        core_upsert_rows=0,
                        error_rows=0,
                    )
                    session.commit()
                    continue

                rows = result.data or []
                input_rows = len(rows)
                upsert_rows = 0
                error_rows = 0

                for row in rows:
                    try:
                        _upsert_trading_calendar(session, row)
                        upsert_rows += 1
                    except Exception as exc:  # noqa: BLE001
                        error_rows += 1
                        sync_repo.add_quality_issue(
                            session,
                            {
                                "data_sync_run_id": data_sync_run.id,
                                "batch_id": batch.id,
                                "theme_code": "TradingCalendar",
                                "dataset_code": "trading_calendar",
                                "layer_code": "CORE",
                                "issue_code": "TRADING_CALENDAR_UPSERT_FAILED",
                                "severity": "ERROR",
                                "business_key": f'{row.get("exchange_code")}:{row.get("trade_date")}',
                                "provider_name": result.provider_name,
                                "trade_date": row.get("trade_date"),
                                "symbol": row.get("exchange_code"),
                                "record_ref": None,
                                "issue_detail": {"error": str(exc), "row": row},
                                "created_at": datetime.utcnow(),
                            },
                        )

                session.commit()

                batch_status = SyncStatus.SUCCESS.value if error_rows == 0 else SyncStatus.PARTIAL.value
                sync_repo.mark_data_batch_finished(
                    session,
                    batch,
                    batch_status,
                    input_rows=input_rows,
                    raw_rows=0,
                    staging_rows=0,
                    core_upsert_rows=upsert_rows,
                    error_rows=error_rows,
                )
                session.commit()

                total_input_rows += input_rows
                total_upsert_rows += upsert_rows
                total_error_rows += error_rows

            except Exception as exc:  # noqa: BLE001
                batch.error_message = str(exc)
                sync_repo.mark_data_batch_finished(
                    session,
                    batch,
                    SyncStatus.FAILED.value,
                    input_rows=0,
                    raw_rows=0,
                    staging_rows=0,
                    core_upsert_rows=0,
                    error_rows=1,
                )
                session.commit()
                total_error_rows += 1

        if total_upsert_rows == 0 and skipped_batches == len(exchanges):
            final_status = SyncStatus.SKIPPED.value
        else:
            final_status = SyncStatus.SUCCESS.value if total_error_rows == 0 else SyncStatus.PARTIAL.value

        sync_repo.mark_data_sync_run_finished(
            session,
            data_sync_run,
            final_status,
            {
                "input_rows": total_input_rows,
                "core_upsert_rows": total_upsert_rows,
                "error_rows": total_error_rows,
                "skipped_batches": skipped_batches,
            },
        )
        session.commit()

    except Exception as exc:  # noqa: BLE001
        sync_repo.mark_data_sync_run_finished(
            session,
            data_sync_run,
            SyncStatus.FAILED.value,
            {"error": str(exc)},
        )
        session.commit()