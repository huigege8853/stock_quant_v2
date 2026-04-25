from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session
from tqdm import tqdm

from stock_quant_v2.data_domain.enums import SyncMode, SyncStatus
from stock_quant_v2.data_domain.repositories.core_repository import CoreRepository
from stock_quant_v2.data_domain.repositories.sync_run_repository import SyncRunRepository
from stock_quant_v2.data_domain.services.universe_service import load_cn_stock_universe
from stock_quant_v2.db.models.core.daily_bar import CoreDailyBar


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _validate_data_version_id(session: Session, data_version_id: int) -> None:
    exists = session.execute(
        text("SELECT 1 FROM meta_data_version WHERE id = :id"),
        {"id": data_version_id},
    ).scalar_one_or_none()
    if exists is None:
        raise ValueError(
            f"data_version_id={data_version_id} does not exist in meta_data_version"
        )


def _load_daily_bar_status(
    session: Session,
    instrument_id: int,
    trade_date: date,
) -> tuple[bool, bool | None]:
    """
    返回:
    - has_bar
    - is_suspended
    """
    stmt = (
        select(CoreDailyBar.is_suspended)
        .where(
            CoreDailyBar.instrument_id == instrument_id,
            CoreDailyBar.trade_date == trade_date,
            CoreDailyBar.price_adjust_type == "RAW",
        )
    )
    value = session.execute(stmt).scalar_one_or_none()
    if value is None:
        return False, None
    return True, bool(value)


def _derive_trading_status(
    *,
    has_bar: bool,
    is_suspended: bool | None,
) -> str:
    if not has_bar:
        return "NO_BAR"
    if bool(is_suspended):
        return "SUSPENDED"
    return "TRADING"


def run_sync_instrument_status_daily(
    session: Session,
    run_id: int,
    data_version_id: int,
    trade_date: date,
) -> None:
    sync_repo = SyncRunRepository()
    core_repo = CoreRepository()

    data_sync_run = sync_repo.create_data_sync_run(
        session,
        {
            "run_id": run_id,
            "sync_job_code": "sync_instrument_status_daily",
            "theme_code": "InstrumentStatusDaily",
            "dataset_code": "instrument_status_daily",
            "provider_name": "derived_from_core_daily_bar",
            "sync_mode": SyncMode.INCREMENTAL.value,
            "sync_granularity": "DATE",
            "partition_from": trade_date,
            "partition_to": trade_date,
            "status": SyncStatus.PENDING.value,
            "cursor_json": None,
            "request_params": {
                "trade_date": trade_date.isoformat(),
                "source_dataset": "core_daily_bar",
                "price_adjust_type": "RAW",
                "rule_version": "v1_minimal",
                "data_version_id": data_version_id,
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

        _validate_data_version_id(session=session, data_version_id=data_version_id)

        universe = load_cn_stock_universe(session, trade_date)

        input_rows = len(universe)
        core_upsert_rows = 0
        error_rows = 0

        status_counter: dict[str, int] = defaultdict(int)
        no_bar_counter = 0
        suspended_counter = 0
        trading_counter = 0

        progress = tqdm(
            universe,
            desc=f"instrument_status_daily {trade_date.isoformat()}",
            unit="symbol",
            dynamic_ncols=True,
        )

        for item in progress:
            instrument_id = item["instrument_id"]
            exchange_code = item["exchange_code"]
            ticker = item["ticker"]

            has_bar, is_suspended = _load_daily_bar_status(
                session=session,
                instrument_id=instrument_id,
                trade_date=trade_date,
            )

            trading_status = _derive_trading_status(
                has_bar=has_bar,
                is_suspended=is_suspended,
            )
            status_counter[trading_status] += 1

            if trading_status == "NO_BAR":
                no_bar_counter += 1
            elif trading_status == "SUSPENDED":
                suspended_counter += 1
            elif trading_status == "TRADING":
                trading_counter += 1

            try:
                with session.begin_nested():
                    core_repo.upsert_instrument_status_daily(
                        session,
                        {
                            "instrument_id": instrument_id,
                            "trade_date": trade_date,
                            "trading_status": trading_status,
                            "is_st": False,
                            "is_suspended": bool(is_suspended) if has_bar else False,
                            "data_version_id": data_version_id,
                        },
                    )
                core_upsert_rows += 1

            except Exception as exc:  # noqa: BLE001
                error_rows += 1
                sync_repo.add_quality_issue(
                    session,
                    {
                        "data_sync_run_id": data_sync_run.id,
                        "batch_id": batch.id,
                        "theme_code": "InstrumentStatusDaily",
                        "dataset_code": "instrument_status_daily",
                        "layer_code": "CORE",
                        "issue_code": "UNHANDLED_EXCEPTION",
                        "severity": "ERROR",
                        "business_key": f"{ticker}:{trade_date.isoformat()}",
                        "provider_name": "derived_from_core_daily_bar",
                        "trade_date": trade_date,
                        "symbol": ticker,
                        "record_ref": None,
                        "issue_detail": {
                            "error": str(exc),
                            "exchange_code": exchange_code,
                            "instrument_id": instrument_id,
                            "trading_status": trading_status,
                        },
                        "created_at": utc_now(),
                    },
                )

            progress.set_postfix(core=core_upsert_rows, err=error_rows)

        if core_upsert_rows == 0 and error_rows == 0:
            final_status = SyncStatus.SKIPPED.value
        else:
            final_status = SyncStatus.SUCCESS.value if error_rows == 0 else SyncStatus.PARTIAL.value

        checkpoint_json = {
            "trade_date": trade_date.isoformat(),
            "input_rows": input_rows,
            "core_upsert_rows": core_upsert_rows,
            "error_rows": error_rows,
            "status_counter": dict(status_counter),
            "no_bar_counter": no_bar_counter,
            "suspended_counter": suspended_counter,
            "trading_counter": trading_counter,
        }

        sync_repo.mark_data_batch_finished(
            session,
            batch,
            final_status,
            input_rows=input_rows,
            raw_rows=0,
            staging_rows=0,
            core_upsert_rows=core_upsert_rows,
            error_rows=error_rows,
            checkpoint_json=checkpoint_json,
        )

        sync_repo.mark_data_sync_run_finished(
            session,
            data_sync_run,
            final_status,
            {
                "trade_date": trade_date.isoformat(),
                "input_rows": input_rows,
                "core_upsert_rows": core_upsert_rows,
                "error_rows": error_rows,
                "status_counter": dict(status_counter),
                "no_bar_counter": no_bar_counter,
                "suspended_counter": suspended_counter,
                "trading_counter": trading_counter,
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
                    "theme_code": "InstrumentStatusDaily",
                    "dataset_code": "instrument_status_daily",
                    "layer_code": "CORE",
                    "issue_code": "UNHANDLED_EXCEPTION",
                    "severity": "ERROR",
                    "business_key": trade_date.isoformat(),
                    "provider_name": "derived_from_core_daily_bar",
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