from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_quant_v2.data_domain.enums import SyncMode, SyncStatus
from stock_quant_v2.data_domain.repositories.core_repository import CoreRepository
from stock_quant_v2.data_domain.repositories.sync_run_repository import SyncRunRepository
from stock_quant_v2.data_domain.services.universe_service import load_cn_stock_universe
from stock_quant_v2.db.models.core.daily_bar import CoreDailyBar


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _to_decimal_or_none(value) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def run_sync_market_breadth(
    session: Session,
    run_id: int,
    trade_date: date,
    market_scope: str,
    exchange_codes: tuple[str, ...],
    data_version_id: int,
) -> None:
    """
    Phase 1 market breadth definition:
    - universe_count: stock universe size from load_cn_stock_universe()
    - bar_count: count of core_daily_bar RAW rows for the trade date
    - suspended_count: universe_count - bar_count
    """
    sync_repo = SyncRunRepository()
    core_repo = CoreRepository()

    data_sync_run = sync_repo.create_data_sync_run(
        session,
        {
            "run_id": run_id,
            "sync_job_code": "sync_market_breadth",
            "theme_code": "MarketBreadth",
            "dataset_code": "market_breadth",
            "provider_name": "derived",
            "sync_mode": SyncMode.INCREMENTAL.value,
            "sync_granularity": "DATE",
            "partition_from": trade_date,
            "partition_to": trade_date,
            "status": SyncStatus.PENDING.value,
            "cursor_json": None,
            "request_params": {
                "trade_date": trade_date.isoformat(),
                "market_scope": market_scope,
                "exchange_codes": list(exchange_codes),
                "universe_source": "load_cn_stock_universe",
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
            "batch_key": f"{market_scope}:{trade_date.isoformat()}",
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

        universe = load_cn_stock_universe(session, trade_date)
        universe = [x for x in universe if x["exchange_code"] in exchange_codes]

        universe_count = len(universe)
        instrument_ids = [row["instrument_id"] for row in universe]

        advancers = 0
        decliners = 0
        unchanged = 0
        bar_count = 0

        total_turnover_amount_cny = Decimal("0")
        returns: list[Decimal] = []

        if instrument_ids:
            stmt = (
                select(
                    CoreDailyBar.instrument_id,
                    CoreDailyBar.close,
                    CoreDailyBar.pre_close,
                    CoreDailyBar.amount,
                    CoreDailyBar.is_suspended,
                )
                .where(
                    CoreDailyBar.trade_date == trade_date,
                    CoreDailyBar.price_adjust_type == "RAW",
                    CoreDailyBar.instrument_id.in_(instrument_ids),
                )
            )

            rows = session.execute(stmt).all()

            for _, close, pre_close, amount, is_suspended in rows:
                if is_suspended:
                    continue

                close_dec = _to_decimal_or_none(close)
                pre_close_dec = _to_decimal_or_none(pre_close)
                amount_dec = _to_decimal_or_none(amount) or Decimal("0")

                bar_count += 1
                total_turnover_amount_cny += amount_dec

                if close_dec is not None and pre_close_dec is not None and pre_close_dec != 0:
                    ret = (close_dec - pre_close_dec) / pre_close_dec
                    returns.append(ret)

                    if ret > 0:
                        advancers += 1
                    elif ret < 0:
                        decliners += 1
                    else:
                        unchanged += 1
                elif close_dec is not None and pre_close_dec is not None:
                    delta = close_dec - pre_close_dec
                    if delta > 0:
                        advancers += 1
                    elif delta < 0:
                        decliners += 1
                    else:
                        unchanged += 1
                else:
                    unchanged += 1

        suspended_count = max(universe_count - bar_count, 0)

        mean_return = None
        median_return = None
        if returns:
            returns_sorted = sorted(returns)
            mean_return = sum(returns_sorted) / Decimal(len(returns_sorted))

            mid = len(returns_sorted) // 2
            if len(returns_sorted) % 2 == 1:
                median_return = returns_sorted[mid]
            else:
                median_return = (returns_sorted[mid - 1] + returns_sorted[mid]) / Decimal("2")

        core_payload = {
            "market_scope": market_scope,
            "trade_date": trade_date,
            "universe_count": universe_count,
            "bar_count": bar_count,
            "advancers": advancers,
            "decliners": decliners,
            "unchanged": unchanged,
            "suspended_count": suspended_count,
            "total_turnover_amount_cny": total_turnover_amount_cny,
            "mean_return": mean_return,
            "median_return": median_return,
            "data_version_id": data_version_id,
        }
        core_repo.upsert_market_breadth(session, core_payload)

        stats_json = {
            "market_scope": market_scope,
            "trade_date": trade_date.isoformat(),
            "exchange_codes": list(exchange_codes),
            "universe_source": "load_cn_stock_universe",
            "universe_count": universe_count,
            "bar_count": bar_count,
            "advancers": advancers,
            "decliners": decliners,
            "unchanged": unchanged,
            "suspended_count": suspended_count,
        }

        sync_repo.mark_data_batch_finished(
            session,
            batch,
            SyncStatus.SUCCESS.value,
            input_rows=universe_count,
            raw_rows=0,
            staging_rows=0,
            core_upsert_rows=1,
            error_rows=0,
            checkpoint_json=stats_json,
        )
        sync_repo.mark_data_sync_run_finished(
            session,
            data_sync_run,
            SyncStatus.SUCCESS.value,
            stats_json,
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
                    "theme_code": "MarketBreadth",
                    "dataset_code": "market_breadth",
                    "layer_code": "CORE",
                    "issue_code": "UNHANDLED_EXCEPTION",
                    "severity": "ERROR",
                    "business_key": f"{market_scope}:{trade_date.isoformat()}",
                    "provider_name": "derived",
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