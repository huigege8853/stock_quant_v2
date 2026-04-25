from __future__ import annotations

from datetime import date

from stock_quant_v2.data_domain.enums import SyncMode
from stock_quant_v2.data_domain.repositories.data_version_repository import DataVersionRepository
from stock_quant_v2.data_domain.repositories.run_repository import RunRepository
from stock_quant_v2.data_domain.tasks.sync_daily_bar import run_sync_daily_bar
from stock_quant_v2.db.session import SessionLocal


def build_tushare_api_client():
    # TODO: 用 settings / env 初始化真实 tushare client
    return None


def resolve_data_version_id(session, dataset_code: str = "daily_bar", vendor_code: str = "tushare") -> int:
    repo = DataVersionRepository()
    version_id = repo.get_latest_published_version_id(
        session,
        dataset_code=dataset_code,
        vendor_code=vendor_code,
    )
    if version_id is None:
        raise ValueError(
            f"No published data version found for dataset_code={dataset_code}, vendor_code={vendor_code}"
        )
    return version_id


def main() -> None:
    session = SessionLocal()
    run_repo = RunRepository()
    root_run = None

    try:
        tushare_api_client = build_tushare_api_client()

        root_run = run_repo.create_run(
            session=session,
            run_type="DATA_REPAIR",
            run_name="repair_missing_daily_bar",
            trigger_type="MANUAL",
            context_json={
                "start_date": "2024-01-08",
                "end_date": "2024-01-12",
                "provider": "tushare",
                "mode": "REPAIR",
            },
        )
        session.commit()

        run_repo.mark_run_running(session, root_run)
        session.commit()

        data_version_id = resolve_data_version_id(
            session,
            dataset_code="daily_bar",
            vendor_code="tushare",
        )

        run_sync_daily_bar(
            session=session,
            tushare_api_client=tushare_api_client,
            run_id=root_run.id,
            data_version_id=data_version_id,
            start_date=date(2024, 1, 8),
            end_date=date(2024, 1, 12),
            provider_name="tushare",
            sync_mode=SyncMode.REPAIR.value,
        )

        run_repo.mark_run_finished(session, root_run, status="SUCCESS")
        session.commit()

    except Exception as exc:  # noqa: BLE001
        session.rollback()
        try:
            if root_run is not None:
                run_repo.mark_run_finished(session, root_run, status="FAILED", error_message=str(exc))
                session.commit()
        except Exception:
            session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()