from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_quant_v2.config.settings import settings
from stock_quant_v2.data_domain.enums import SyncMode, SyncStatus
from stock_quant_v2.data_domain.repositories.sync_run_repository import SyncRunRepository
from stock_quant_v2.data_domain.services.instrument_classification_service import classify_cn_instrument
from stock_quant_v2.data_domain.services.provider_fallback_service import ProviderFallbackService
from stock_quant_v2.db.models.meta.exchange import MetaExchange
from stock_quant_v2.db.models.meta.instrument import MetaInstrument
from stock_quant_v2.db.models.meta.market import MetaMarket


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _normalize_instrument_row(row: dict, provider_name: str) -> dict:
    exchange_code = str(row.get("exchange_code") or "").strip().upper()
    ticker = str(row.get("ticker") or "").strip()
    display_name = str(
        row.get("display_name")
        or row.get("full_name")
        or row.get("name")
        or ""
    ).strip()
    provider_instrument_type = row.get("instrument_type")

    instrument_type = classify_cn_instrument(
        exchange_code=exchange_code,
        ticker=ticker,
        display_name=display_name,
        provider_instrument_type=provider_instrument_type,
    )

    return {
        "market_code": row.get("market_code") or "CN_A",
        "exchange_code": exchange_code,
        "ticker": ticker,
        "instrument_code": row.get("instrument_code") or f"{ticker}.{exchange_code}",
        "display_name": display_name,
        "instrument_type": instrument_type,
        "currency": row.get("currency") or "CNY",
        "list_date": row.get("list_date"),
        "delist_date": row.get("delist_date"),
        "is_active": bool(row.get("is_active", True)),
        "provider_name": provider_name,
    }


def _get_market_id(session: Session, market_code: str) -> int:
    stmt = select(MetaMarket.id).where(MetaMarket.market_code == market_code)
    market_id = session.execute(stmt).scalar_one_or_none()
    if market_id is None:
        raise ValueError(f"market not found: {market_code}")
    return market_id


def _get_exchange_id(session: Session, exchange_code: str) -> int:
    stmt = select(MetaExchange.id).where(MetaExchange.exchange_code == exchange_code)
    exchange_id = session.execute(stmt).scalar_one_or_none()
    if exchange_id is None:
        raise ValueError(f"exchange not found: {exchange_code}")
    return exchange_id


def _upsert_instrument(session: Session, row: dict) -> None:
    market_id = _get_market_id(session, row["market_code"])
    exchange_id = _get_exchange_id(session, row["exchange_code"])

    stmt = (
        select(MetaInstrument)
        .where(
            MetaInstrument.market_id == market_id,
            MetaInstrument.exchange_id == exchange_id,
            MetaInstrument.symbol == row["ticker"],
        )
    )
    obj = session.execute(stmt).scalar_one_or_none()

    if obj is None:
        obj = MetaInstrument(
            market_id=market_id,
            exchange_id=exchange_id,
            symbol=row["ticker"],
            instrument_code=row["instrument_code"],
            display_name=row["display_name"],
            instrument_type=row.get("instrument_type", "UNKNOWN"),
            currency=row["currency"],
            list_date=row.get("list_date"),
            delist_date=row.get("delist_date"),
            is_active=row.get("is_active", True),
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(obj)
    else:
        obj.instrument_code = row["instrument_code"]
        obj.display_name = row["display_name"]
        obj.instrument_type = row.get("instrument_type", "UNKNOWN")
        obj.currency = row["currency"]

        incoming_list_date = row.get("list_date")
        incoming_delist_date = row.get("delist_date")

        if incoming_list_date is not None:
            obj.list_date = incoming_list_date

        if incoming_delist_date is not None:
            obj.delist_date = incoming_delist_date

        obj.is_active = row.get("is_active", True)
        obj.updated_at = utc_now()


def _fetch_provider_rows(provider_name: str, raw_api_client) -> list[dict]:
    """
    这里传入的是“原始 api client / adapter”，不是包装 provider client。
    所以这里必须显式包一层，再调用 fetch_instruments()。
    """
    if raw_api_client is None:
        return []

    if provider_name == "akshare":
        from stock_quant_v2.data_domain.providers.akshare.client import AkshareClient

        client = AkshareClient(api_client=raw_api_client)
        rows = client.fetch_instruments()
    elif provider_name == "tushare":
        from stock_quant_v2.data_domain.providers.tushare.client import TushareClient

        client = TushareClient(api_client=raw_api_client)
        rows = client.fetch_instruments()
    elif provider_name == "baostock":
        from stock_quant_v2.data_domain.providers.baostock.client import BaoStockClient

        client = BaoStockClient(api_client=raw_api_client)
        rows = client.fetch_instruments()
    else:
        return []

    if not rows:
        return []

    return [
        _normalize_instrument_row(row, provider_name)
        for row in rows
        if row.get("ticker") and row.get("exchange_code")
    ]


def _merge_instrument_rows(
    base_rows: list[dict],
    enrich_rows: list[dict],
) -> list[dict]:
    enrich_map: dict[tuple[str, str], dict] = {}
    for row in enrich_rows:
        enrich_map[(row["exchange_code"], row["ticker"])] = row

    merged: list[dict] = []
    for row in base_rows:
        enrich = enrich_map.get((row["exchange_code"], row["ticker"]))

        if enrich is not None:
            if row.get("list_date") is None and enrich.get("list_date") is not None:
                row["list_date"] = enrich.get("list_date")

            if row.get("delist_date") is None and enrich.get("delist_date") is not None:
                row["delist_date"] = enrich.get("delist_date")

            if not row.get("display_name") and enrich.get("display_name"):
                row["display_name"] = enrich.get("display_name")

            if enrich.get("delist_date") is not None:
                row["is_active"] = enrich.get("is_active", row.get("is_active", True))

        merged.append(row)

    return merged


def run_sync_instrument(
    session: Session,
    baostock_api_client,
    tushare_api_client,
    akshare_api_client,
    run_id: int,
) -> None:
    sync_repo = SyncRunRepository()
    fallback_service = ProviderFallbackService()

    data_sync_run = sync_repo.create_data_sync_run(
        session,
        {
            "run_id": run_id,
            "sync_job_code": "sync_instrument",
            "theme_code": "Instrument",
            "dataset_code": "instrument",
            "provider_name": "base_plus_enrich",
            "sync_mode": SyncMode.FULL.value,
            "sync_granularity": "ALL",
            "partition_from": None,
            "partition_to": None,
            "status": SyncStatus.PENDING.value,
            "cursor_json": None,
            "request_params": {
                "base_providers": ["akshare", "tushare", "baostock"],
                "enrich_provider": "tushare",
                "tushare_enabled": bool(settings.tushare_enabled),
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
            "batch_key": "ALL",
            "batch_type": "FULL",
            "partition_date": None,
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

        base_attempts = [
            ("akshare", lambda: _fetch_provider_rows("akshare", akshare_api_client)),
            ("tushare", lambda: _fetch_provider_rows("tushare", tushare_api_client)),
            ("baostock", lambda: _fetch_provider_rows("baostock", baostock_api_client)),
        ]

        base_result = fallback_service.try_providers(
            base_attempts,
            skipped_providers=(
                {"tushare": "disabled_by_config"} if not settings.tushare_enabled else {}
            ),
        )

        if not base_result.success or not (base_result.data or []):
            sync_repo.add_quality_issue(
                session,
                {
                    "data_sync_run_id": data_sync_run.id,
                    "batch_id": batch.id,
                    "theme_code": "Instrument",
                    "dataset_code": "instrument",
                    "layer_code": "CORE",
                    "issue_code": "ALL_PROVIDERS_UNAVAILABLE",
                    "severity": "ERROR",
                    "business_key": "instrument_full_sync",
                    "provider_name": None,
                    "trade_date": None,
                    "symbol": None,
                    "record_ref": None,
                    "issue_detail": {"error": base_result.error},
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
                checkpoint_json=None,
                error_message=base_result.error,
            )
            sync_repo.mark_data_sync_run_finished(
                session,
                data_sync_run,
                SyncStatus.FAILED.value,
                {"error": base_result.error},
            )
            session.commit()
            return

        base_rows = list(base_result.data or [])
        enrich_rows: list[dict] = []
        enrich_provider_used: str | None = None

        if settings.tushare_enabled and tushare_api_client is not None:
            try:
                enrich_rows = _fetch_provider_rows("tushare", tushare_api_client)
                if enrich_rows:
                    enrich_provider_used = "tushare"
            except Exception as exc:  # noqa: BLE001
                sync_repo.add_quality_issue(
                    session,
                    {
                        "data_sync_run_id": data_sync_run.id,
                        "batch_id": batch.id,
                        "theme_code": "Instrument",
                        "dataset_code": "instrument",
                        "layer_code": "CORE",
                        "issue_code": "ENRICH_PROVIDER_FAILED",
                        "severity": "WARN",
                        "business_key": "instrument_enrich_tushare",
                        "provider_name": "tushare",
                        "trade_date": None,
                        "symbol": None,
                        "record_ref": None,
                        "issue_detail": {"error": str(exc)},
                        "created_at": utc_now(),
                    },
                )

        merged_rows = _merge_instrument_rows(base_rows, enrich_rows)

        lifecycle_missing_count = 0
        error_rows = 0

        for row in merged_rows:
            try:
                _upsert_instrument(session, row)
                if row.get("list_date") is None:
                    lifecycle_missing_count += 1
            except Exception as exc:  # noqa: BLE001
                error_rows += 1
                sync_repo.add_quality_issue(
                    session,
                    {
                        "data_sync_run_id": data_sync_run.id,
                        "batch_id": batch.id,
                        "theme_code": "Instrument",
                        "dataset_code": "instrument",
                        "layer_code": "CORE",
                        "issue_code": "UNHANDLED_EXCEPTION",
                        "severity": "ERROR",
                        "business_key": f'{row["exchange_code"]}:{row["ticker"]}',
                        "provider_name": row.get("provider_name"),
                        "trade_date": None,
                        "symbol": row["ticker"],
                        "record_ref": None,
                        "issue_detail": {"row": row, "error": str(exc)},
                        "created_at": utc_now(),
                    },
                )

        session.flush()

        batch_status = SyncStatus.SUCCESS.value if error_rows == 0 else SyncStatus.PARTIAL.value
        input_rows = len(merged_rows)

        sync_repo.mark_data_batch_finished(
            session,
            batch,
            batch_status,
            input_rows=input_rows,
            raw_rows=0,
            staging_rows=0,
            core_upsert_rows=input_rows - error_rows,
            error_rows=error_rows,
            checkpoint_json={
                "selected_base_provider": base_result.provider_name,
                "enrich_provider_used": enrich_provider_used,
                "base_row_count": len(base_rows),
                "enrich_row_count": len(enrich_rows),
                "merged_row_count": len(merged_rows),
                "lifecycle_missing_count": lifecycle_missing_count,
            },
        )

        sync_repo.mark_data_sync_run_finished(
            session,
            data_sync_run,
            batch_status,
            {
                "input_rows": input_rows,
                "core_upsert_rows": input_rows - error_rows,
                "error_rows": error_rows,
                "selected_base_provider": base_result.provider_name,
                "enrich_provider_used": enrich_provider_used,
                "lifecycle_missing_count": lifecycle_missing_count,
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
                checkpoint_json=None,
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