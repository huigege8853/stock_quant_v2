from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.orm import Session
from tqdm import tqdm

from stock_quant_v2.data_domain.enums import SyncMode, SyncStatus
from stock_quant_v2.data_domain.repositories.sync_run_repository import SyncRunRepository
from stock_quant_v2.data_domain.repositories.tag_repository import TagRepository
from stock_quant_v2.data_domain.services.universe_service import load_cn_stock_universe
from stock_quant_v2.db.models.core.instrument_status_daily import CoreInstrumentStatusDaily


def _board_tag_code(exchange_code: str, ticker: str) -> tuple[str, str]:
    exchange_code = str(exchange_code).upper()
    ticker = str(ticker)

    if exchange_code == "SSE" and ticker.startswith(("688", "689")):
        return "BOARD", "STAR"
    if exchange_code == "SZSE" and ticker.startswith(("300", "301")):
        return "BOARD", "CHINEXT"
    if exchange_code == "BSE":
        return "BOARD", "BSE"
    return "BOARD", "MAIN"


def _price_limit_tag_code(exchange_code: str, ticker: str) -> tuple[str, str]:
    exchange_code = str(exchange_code).upper()
    ticker = str(ticker)

    if exchange_code == "SSE" and ticker.startswith(("688", "689")):
        return "PRICE_LIMIT", "PCT_20"
    if exchange_code == "SZSE" and ticker.startswith(("300", "301")):
        return "PRICE_LIMIT", "PCT_20"
    if exchange_code == "BSE":
        return "PRICE_LIMIT", "PCT_30"
    return "PRICE_LIMIT", "PCT_10"


def _load_trading_status_tag_code(
    session: Session,
    instrument_id: int,
    trade_date: date,
) -> tuple[str, str]:
    stmt = (
        select(CoreInstrumentStatusDaily.trading_status)
        .where(
            CoreInstrumentStatusDaily.instrument_id == instrument_id,
            CoreInstrumentStatusDaily.trade_date == trade_date,
        )
    )
    trading_status = session.execute(stmt).scalar_one_or_none()

    if trading_status == "TRADING":
        return "TRADING_STATUS", "TRADING"
    if trading_status == "SUSPENDED":
        return "TRADING_STATUS", "SUSPENDED"
    return "TRADING_STATUS", "NO_BAR"


def _validate_data_version_id(session: Session, data_version_id: int) -> None:
    exists = session.execute(
        text("SELECT 1 FROM meta_data_version WHERE id = :id"),
        {"id": data_version_id},
    ).scalar_one_or_none()
    if exists is None:
        raise ValueError(
            f"data_version_id={data_version_id} does not exist in meta_data_version"
        )


def run_sync_instrument_tag(
    session: Session,
    run_id: int,
    data_version_id: int,
    trade_date: date,
) -> None:
    sync_repo = SyncRunRepository()
    tag_repo = TagRepository()

    data_sync_run = sync_repo.create_data_sync_run(
        session,
        {
            "run_id": run_id,
            "sync_job_code": "sync_instrument_tag",
            "theme_code": "InstrumentTag",
            "dataset_code": "instrument_tag",
            "provider_name": "derived_from_core",
            "sync_mode": SyncMode.INCREMENTAL.value,
            "sync_granularity": "DATE",
            "partition_from": trade_date,
            "partition_to": trade_date,
            "status": SyncStatus.PENDING.value,
            "cursor_json": None,
            "request_params": {
                "trade_date": trade_date.isoformat(),
                "rule_version": "v1",
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

        required_pairs = [
            ("BOARD", "MAIN"),
            ("BOARD", "STAR"),
            ("BOARD", "CHINEXT"),
            ("BOARD", "BSE"),
            ("PRICE_LIMIT", "PCT_10"),
            ("PRICE_LIMIT", "PCT_20"),
            ("PRICE_LIMIT", "PCT_30"),
            ("TRADING_STATUS", "TRADING"),
            ("TRADING_STATUS", "NO_BAR"),
            ("TRADING_STATUS", "SUSPENDED"),
        ]

        tag_id_map: dict[tuple[str, str], int] = {}
        for tag_type, tag_code in required_pairs:
            tag_id = tag_repo.get_tag_id(session, tag_type, tag_code)
            if tag_id is None:
                raise ValueError(f"tag not found: {tag_type}:{tag_code}")
            tag_id_map[(tag_type, tag_code)] = tag_id

        universe = load_cn_stock_universe(session, trade_date)

        input_rows = len(universe)
        core_upsert_rows = 0
        error_rows = 0
        source_provider_counter: dict[str, int] = defaultdict(int)

        progress = tqdm(
            universe,
            desc=f"instrument_tag {trade_date.isoformat()}",
            unit="symbol",
            dynamic_ncols=True,
        )

        for item in progress:
            instrument_id = item["instrument_id"]
            exchange_code = item["exchange_code"]
            ticker = item["ticker"]

            tag_pairs = [
                _board_tag_code(exchange_code=exchange_code, ticker=ticker),
                _price_limit_tag_code(exchange_code=exchange_code, ticker=ticker),
                _load_trading_status_tag_code(
                    session=session,
                    instrument_id=instrument_id,
                    trade_date=trade_date,
                ),
            ]

            try:
                with session.begin_nested():
                    for tag_type, tag_code in tag_pairs:
                        payload = {
                            "instrument_id": instrument_id,
                            "tag_id": tag_id_map[(tag_type, tag_code)],
                            "effective_from": trade_date,
                            "effective_to": None,
                            "source_provider": "derived_from_core",
                            "confidence": Decimal("1.0000"),
                        }
                        tag_repo.upsert_instrument_tag(session, payload)
                        core_upsert_rows += 1
                        source_provider_counter["derived_from_core"] += 1

            except Exception as exc:  # noqa: BLE001
                error_rows += 1
                sync_repo.add_quality_issue(
                    session,
                    {
                        "data_sync_run_id": data_sync_run.id,
                        "batch_id": batch.id,
                        "theme_code": "InstrumentTag",
                        "dataset_code": "instrument_tag",
                        "layer_code": "CORE",
                        "issue_code": "UNHANDLED_EXCEPTION",
                        "severity": "ERROR",
                        "business_key": f"{ticker}:{trade_date.isoformat()}",
                        "provider_name": "derived_from_core",
                        "trade_date": trade_date,
                        "symbol": ticker,
                        "record_ref": None,
                        "issue_detail": {
                            "error": str(exc),
                            "exchange_code": exchange_code,
                            "instrument_id": instrument_id,
                        },
                        "created_at": datetime.utcnow(),
                    },
                )

            progress.set_postfix(core=core_upsert_rows, err=error_rows)

        final_status = SyncStatus.SUCCESS.value if error_rows == 0 else SyncStatus.PARTIAL.value

        checkpoint_json = {
            "trade_date": trade_date.isoformat(),
            "input_rows": input_rows,
            "core_upsert_rows": core_upsert_rows,
            "error_rows": error_rows,
            "source_provider_counter": dict(source_provider_counter),
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
            checkpoint_json,
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