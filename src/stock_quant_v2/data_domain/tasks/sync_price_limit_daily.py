from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select, text
from sqlalchemy.orm import Session
from tqdm import tqdm

from stock_quant_v2.data_domain.enums import SyncMode, SyncStatus
from stock_quant_v2.data_domain.repositories.core_repository import CoreRepository
from stock_quant_v2.data_domain.repositories.instrument_lookup_repository import InstrumentLookupRepository
from stock_quant_v2.data_domain.repositories.sync_run_repository import SyncRunRepository
from stock_quant_v2.data_domain.services.universe_service import load_cn_stock_universe
from stock_quant_v2.db.models.core.daily_bar import CoreDailyBar


_DECIMAL_4 = Decimal("0.0001")
_ONE = Decimal("1")
_PCT_10 = Decimal("0.10")
_PCT_20 = Decimal("0.20")
_PCT_30 = Decimal("0.30")


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _round_price(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(_DECIMAL_4, rounding=ROUND_HALF_UP)


def _to_decimal(value) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _validate_data_version_id(session: Session, data_version_id: int) -> None:
    exists = session.execute(
        text("SELECT 1 FROM meta_data_version WHERE id = :id"),
        {"id": data_version_id},
    ).scalar_one_or_none()
    if exists is None:
        raise ValueError(
            f"data_version_id={data_version_id} does not exist in meta_data_version"
        )


def _infer_limit_pct(exchange_code: str, ticker: str) -> Decimal:
    exchange_code = str(exchange_code).upper()
    ticker = str(ticker)

    if exchange_code == "SSE" and ticker.startswith(("688", "689")):
        return _PCT_20

    if exchange_code == "SZSE" and ticker.startswith(("300", "301")):
        return _PCT_20

    if exchange_code == "BSE":
        return _PCT_30

    return _PCT_10


def _is_no_limit_window(
    *,
    exchange_code: str,
    ticker: str,
    trade_date: date,
    list_date: date | None,
) -> bool:
    if list_date is None:
        return False

    exchange_code = str(exchange_code).upper()
    ticker = str(ticker)

    is_star = exchange_code == "SSE" and ticker.startswith(("688", "689"))
    is_chinext = exchange_code == "SZSE" and ticker.startswith(("300", "301"))

    if not (is_star or is_chinext):
        return False

    if trade_date < list_date:
        return False

    delta_days = (trade_date - list_date).days
    return 0 <= delta_days <= 6


def _calc_limits(pre_close: Decimal, limit_pct: Decimal) -> tuple[Decimal, Decimal]:
    up_limit = _round_price(pre_close * (_ONE + limit_pct))
    down_limit = _round_price(pre_close * (_ONE - limit_pct))
    return up_limit, down_limit


def _load_pre_close(
    session: Session,
    instrument_id: int,
    trade_date: date,
) -> Decimal | None:
    stmt = (
        select(CoreDailyBar.pre_close)
        .where(
            CoreDailyBar.instrument_id == instrument_id,
            CoreDailyBar.trade_date == trade_date,
            CoreDailyBar.price_adjust_type == "RAW",
        )
    )
    value = session.execute(stmt).scalar_one_or_none()
    return _to_decimal(value)


def run_sync_price_limit_daily(
    session: Session,
    run_id: int,
    data_version_id: int,
    trade_date: date,
) -> None:
    sync_repo = SyncRunRepository()
    core_repo = CoreRepository()
    instrument_repo = InstrumentLookupRepository()

    data_sync_run = sync_repo.create_data_sync_run(
        session,
        {
            "run_id": run_id,
            "sync_job_code": "sync_price_limit_daily",
            "theme_code": "PriceLimitDaily",
            "dataset_code": "price_limit_daily",
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
        skipped_rows = 0

        no_pre_close_counter = 0
        no_limit_window_counter = 0
        pct_counter: dict[str, int] = defaultdict(int)

        progress = tqdm(
            universe,
            desc=f"price_limit_daily {trade_date.isoformat()}",
            unit="symbol",
            dynamic_ncols=True,
        )

        for item in progress:
            instrument_id = item["instrument_id"]
            exchange_code = item["exchange_code"]
            ticker = item["ticker"]

            pre_close = _load_pre_close(
                session=session,
                instrument_id=instrument_id,
                trade_date=trade_date,
            )
            if pre_close is None:
                skipped_rows += 1
                no_pre_close_counter += 1
                sync_repo.add_quality_issue(
                    session,
                    {
                        "data_sync_run_id": data_sync_run.id,
                        "batch_id": batch.id,
                        "theme_code": "PriceLimitDaily",
                        "dataset_code": "price_limit_daily",
                        "layer_code": "CORE",
                        "issue_code": "PRE_CLOSE_NOT_FOUND",
                        "severity": "WARN",
                        "business_key": f"{ticker}:{trade_date.isoformat()}",
                        "provider_name": "derived_from_core_daily_bar",
                        "trade_date": trade_date,
                        "symbol": ticker,
                        "record_ref": None,
                        "issue_detail": {
                            "instrument_id": instrument_id,
                            "exchange_code": exchange_code,
                            "price_adjust_type": "RAW",
                        },
                        "created_at": utc_now(),
                    },
                )
                progress.set_postfix(core=core_upsert_rows, err=error_rows, skip=skipped_rows)
                continue

            lifecycle = instrument_repo.get_instrument_lifecycle(
                session=session,
                exchange_code=exchange_code,
                ticker=ticker,
            )
            list_date = lifecycle[0] if lifecycle else None

            if _is_no_limit_window(
                exchange_code=exchange_code,
                ticker=ticker,
                trade_date=trade_date,
                list_date=list_date,
            ):
                skipped_rows += 1
                no_limit_window_counter += 1
                sync_repo.add_quality_issue(
                    session,
                    {
                        "data_sync_run_id": data_sync_run.id,
                        "batch_id": batch.id,
                        "theme_code": "PriceLimitDaily",
                        "dataset_code": "price_limit_daily",
                        "layer_code": "CORE",
                        "issue_code": "NO_LIMIT_WINDOW",
                        "severity": "WARN",
                        "business_key": f"{ticker}:{trade_date.isoformat()}",
                        "provider_name": "derived_from_core_daily_bar",
                        "trade_date": trade_date,
                        "symbol": ticker,
                        "record_ref": None,
                        "issue_detail": {
                            "exchange_code": exchange_code,
                            "list_date": list_date.isoformat() if list_date else None,
                        },
                        "created_at": utc_now(),
                    },
                )
                progress.set_postfix(core=core_upsert_rows, err=error_rows, skip=skipped_rows)
                continue

            limit_pct = _infer_limit_pct(exchange_code=exchange_code, ticker=ticker)
            pct_counter[str(limit_pct)] += 1
            up_limit, down_limit = _calc_limits(pre_close=pre_close, limit_pct=limit_pct)

            try:
                with session.begin_nested():
                    core_repo.upsert_price_limit_daily(
                        session,
                        {
                            "instrument_id": instrument_id,
                            "trade_date": trade_date,
                            "up_limit": up_limit,
                            "down_limit": down_limit,
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
                        "theme_code": "PriceLimitDaily",
                        "dataset_code": "price_limit_daily",
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
                        },
                        "created_at": utc_now(),
                    },
                )

            progress.set_postfix(core=core_upsert_rows, err=error_rows, skip=skipped_rows)

        if core_upsert_rows == 0 and error_rows == 0:
            final_status = SyncStatus.SKIPPED.value
        else:
            final_status = SyncStatus.SUCCESS.value if error_rows == 0 else SyncStatus.PARTIAL.value

        checkpoint_json = {
            "trade_date": trade_date.isoformat(),
            "input_rows": input_rows,
            "core_upsert_rows": core_upsert_rows,
            "error_rows": error_rows,
            "skipped_rows": skipped_rows,
            "no_pre_close_counter": no_pre_close_counter,
            "no_limit_window_counter": no_limit_window_counter,
            "limit_pct_counter": dict(pct_counter),
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
                "skipped_rows": skipped_rows,
                "no_pre_close_counter": no_pre_close_counter,
                "no_limit_window_counter": no_limit_window_counter,
                "limit_pct_counter": dict(pct_counter),
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
                    "theme_code": "PriceLimitDaily",
                    "dataset_code": "price_limit_daily",
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