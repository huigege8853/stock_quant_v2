from __future__ import annotations

from sqlalchemy.orm import Session

from stock_quant_v2.data_domain.enums import SyncMode, SyncStatus
from stock_quant_v2.data_domain.repositories.sync_run_repository import SyncRunRepository
from stock_quant_v2.data_domain.repositories.tag_repository import TagRepository


def _build_seed_tags() -> list[dict]:
    return [
        {"tag_type": "BOARD", "tag_code": "MAIN", "tag_name": "主板", "taxonomy_source": "SYSTEM_V1", "is_active": True},
        {"tag_type": "BOARD", "tag_code": "STAR", "tag_name": "科创板", "taxonomy_source": "SYSTEM_V1", "is_active": True},
        {"tag_type": "BOARD", "tag_code": "CHINEXT", "tag_name": "创业板", "taxonomy_source": "SYSTEM_V1", "is_active": True},
        {"tag_type": "BOARD", "tag_code": "BSE", "tag_name": "北交所", "taxonomy_source": "SYSTEM_V1", "is_active": True},
        {"tag_type": "PRICE_LIMIT", "tag_code": "PCT_10", "tag_name": "10%涨跌幅", "taxonomy_source": "SYSTEM_V1", "is_active": True},
        {"tag_type": "PRICE_LIMIT", "tag_code": "PCT_20", "tag_name": "20%涨跌幅", "taxonomy_source": "SYSTEM_V1", "is_active": True},
        {"tag_type": "PRICE_LIMIT", "tag_code": "PCT_30", "tag_name": "30%涨跌幅", "taxonomy_source": "SYSTEM_V1", "is_active": True},
        {"tag_type": "TRADING_STATUS", "tag_code": "TRADING", "tag_name": "正常交易", "taxonomy_source": "SYSTEM_V1", "is_active": True},
        {"tag_type": "TRADING_STATUS", "tag_code": "NO_BAR", "tag_name": "无行情", "taxonomy_source": "SYSTEM_V1", "is_active": True},
        {"tag_type": "TRADING_STATUS", "tag_code": "SUSPENDED", "tag_name": "停牌", "taxonomy_source": "SYSTEM_V1", "is_active": True},
    ]


def run_sync_tag(
    session: Session,
    run_id: int,
) -> None:
    sync_repo = SyncRunRepository()
    tag_repo = TagRepository()

    data_sync_run = sync_repo.create_data_sync_run(
        session,
        {
            "run_id": run_id,
            "sync_job_code": "sync_tag",
            "theme_code": "Tag",
            "dataset_code": "tag",
            "provider_name": "system_seed",
            "sync_mode": SyncMode.FULL.value,
            "sync_granularity": "DATE",
            "partition_from": None,
            "partition_to": None,
            "status": SyncStatus.PENDING.value,
            "cursor_json": None,
            "request_params": {"seed_version": "v1"},
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
            "batch_type": "DATE",
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

        rows = _build_seed_tags()
        upsert_rows = 0

        for row in rows:
            tag_repo.upsert_tag(session, row)
            upsert_rows += 1

        checkpoint_json = {
            "seed_count": len(rows),
            "core_upsert_rows": upsert_rows,
            "error_rows": 0,
        }

        sync_repo.mark_data_batch_finished(
            session,
            batch,
            SyncStatus.SUCCESS.value,
            input_rows=len(rows),
            raw_rows=0,
            staging_rows=0,
            core_upsert_rows=upsert_rows,
            error_rows=0,
            checkpoint_json=checkpoint_json,
        )

        sync_repo.mark_data_sync_run_finished(
            session,
            data_sync_run,
            SyncStatus.SUCCESS.value,
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