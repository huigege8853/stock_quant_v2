from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from stock_quant_v2.data_domain.enums import SyncStatus
from stock_quant_v2.db.models.ops.data_batch import DataBatch
from stock_quant_v2.db.models.ops.data_lineage import DataLineage
from stock_quant_v2.db.models.ops.data_quality_issue import DataQualityIssue
from stock_quant_v2.db.models.ops.data_sync_run import DataSyncRun


class SyncRunRepository:
    def create_data_sync_run(self, session: Session, payload: dict) -> DataSyncRun:
        obj = DataSyncRun(**payload)
        session.add(obj)
        session.flush()
        return obj

    def mark_data_sync_run_running(self, session: Session, obj: DataSyncRun) -> None:
        obj.status = SyncStatus.RUNNING.value
        obj.started_at = datetime.utcnow()
        session.flush()

    def mark_data_sync_run_finished(self, session: Session, obj: DataSyncRun, status: str, stats_json: dict | None) -> None:
        obj.status = status
        obj.stats_json = stats_json
        obj.finished_at = datetime.utcnow()
        session.flush()

    def create_data_batch(self, session: Session, payload: dict) -> DataBatch:
        obj = DataBatch(**payload)
        session.add(obj)
        session.flush()
        return obj

    def mark_data_batch_running(self, session: Session, obj: DataBatch) -> None:
        obj.status = SyncStatus.RUNNING.value
        obj.started_at = datetime.utcnow()
        session.flush()

    def mark_data_batch_finished(self, session: Session, obj: DataBatch, status: str, **stats) -> None:
        obj.status = status
        obj.finished_at = datetime.utcnow()
        for key, value in stats.items():
            setattr(obj, key, value)
        session.flush()

    def add_quality_issue(self, session: Session, payload: dict) -> DataQualityIssue:
        obj = DataQualityIssue(**payload)
        session.add(obj)
        session.flush()
        return obj

    def add_lineage(self, session: Session, payload: dict) -> DataLineage:
        obj = DataLineage(**payload)
        session.add(obj)
        session.flush()
        return obj

    def find_latest_successful_batch_no(
        self,
        session: Session,
        *,
        sync_job_code: str,
        theme_code: str,
        dataset_code: str,
        provider_name: str,
        partition_from: date,
        partition_to: date,
        sync_granularity: str,
        symbol_chunk_size: int,
        execution_mode: str,
    ) -> int:
        stmt = (
            select(
                DataBatch.batch_no,
                DataSyncRun.request_params,
            )
            .join(DataSyncRun, DataBatch.data_sync_run_id == DataSyncRun.id)
            .where(
                DataSyncRun.sync_job_code == sync_job_code,
                DataSyncRun.theme_code == theme_code,
                DataSyncRun.dataset_code == dataset_code,
                DataSyncRun.provider_name == provider_name,
                DataSyncRun.partition_from == partition_from,
                DataSyncRun.partition_to == partition_to,
                DataSyncRun.sync_granularity == sync_granularity,
                DataSyncRun.status == SyncStatus.SUCCESS.value,
                DataSyncRun.finished_at.is_not(None),
                DataBatch.status == SyncStatus.SUCCESS.value,
                DataBatch.finished_at.is_not(None),
            )
            .order_by(DataBatch.batch_no.desc(), DataBatch.id.desc())
        )

        for batch_no, request_params in session.execute(stmt).all():
            params = request_params or {}
            if str(params.get("execution_mode")) != execution_mode:
                continue

            try:
                chunk_size = int(params.get("symbol_chunk_size"))
            except (TypeError, ValueError):
                continue

            if chunk_size != symbol_chunk_size:
                continue

            return int(batch_no)

        return 0

    def find_running_batches(
            self,
            session: Session,
            *,
            sync_job_code: str,
            theme_code: str,
            dataset_code: str,
            provider_name: str,
            partition_from: date,
            partition_to: date,
            sync_granularity: str,
            symbol_chunk_size: int,
            execution_mode: str,
    ) -> list[dict]:
        stmt = (
            select(
                DataBatch.id,
                DataBatch.data_sync_run_id,
                DataBatch.batch_no,
                DataBatch.batch_key,
                DataBatch.status,
                DataBatch.started_at,
                DataSyncRun.request_params,
            )
            .join(DataSyncRun, DataBatch.data_sync_run_id == DataSyncRun.id)
            .where(
                DataSyncRun.sync_job_code == sync_job_code,
                DataSyncRun.theme_code == theme_code,
                DataSyncRun.dataset_code == dataset_code,
                DataSyncRun.provider_name == provider_name,
                DataSyncRun.partition_from == partition_from,
                DataSyncRun.partition_to == partition_to,
                DataSyncRun.sync_granularity == sync_granularity,
                DataBatch.status == SyncStatus.RUNNING.value,
            )
            .order_by(DataBatch.started_at.desc(), DataBatch.id.desc())
        )

        result: list[dict] = []

        for row in session.execute(stmt).all():
            (
                batch_id,
                data_sync_run_id,
                batch_no,
                batch_key,
                status,
                started_at,
                request_params,
            ) = row

            params = request_params or {}

            if str(params.get("execution_mode")) != execution_mode:
                continue

            try:
                chunk_size = int(params.get("symbol_chunk_size"))
            except (TypeError, ValueError):
                continue

            if chunk_size != symbol_chunk_size:
                continue

            result.append(
                {
                    "batch_id": int(batch_id),
                    "data_sync_run_id": int(data_sync_run_id),
                    "batch_no": int(batch_no),
                    "batch_key": str(batch_key),
                    "status": str(status),
                    "started_at": started_at,
                }
            )

        return result

    def mark_running_batches_failed_by_ids(
            self,
            session: Session,
            *,
            batch_ids: list[int],
            data_sync_run_ids: list[int],
            reason: str,
    ) -> None:
        now = datetime.utcnow()

        if batch_ids:
            session.execute(
                update(DataBatch)
                .where(
                    DataBatch.id.in_(batch_ids),
                    DataBatch.status == SyncStatus.RUNNING.value,
                )
                .values(
                    status=SyncStatus.FAILED.value,
                    error_message=reason,
                    finished_at=now,
                )
            )

        if data_sync_run_ids:
            session.execute(
                update(DataSyncRun)
                .where(
                    DataSyncRun.id.in_(data_sync_run_ids),
                    DataSyncRun.status == SyncStatus.RUNNING.value,
                )
                .values(
                    status=SyncStatus.FAILED.value,
                    stats_json={
                        "manual_fix": True,
                        "reason": reason,
                    },
                    finished_at=now,
                )
            )

        session.flush()