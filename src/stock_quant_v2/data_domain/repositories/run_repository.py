from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from stock_quant_v2.db.models.ops.run import OpsRun


class RunRepository:
    def create_run(
        self,
        session: Session,
        run_type: str,
        run_name: str,
        trigger_type: str,
        parent_run_id: int | None = None,
        context_json: dict | None = None,
    ) -> OpsRun:
        obj = OpsRun(
            run_type=run_type,
            run_name=run_name,
            status="PENDING",
            trigger_type=trigger_type,
            parent_run_id=parent_run_id,
            requested_at=datetime.now(timezone.utc),
            context_json=context_json or {},
        )
        session.add(obj)
        session.flush()
        return obj

    def mark_run_running(self, session: Session, run: OpsRun) -> None:
        run.status = "RUNNING"
        run.started_at = datetime.now(timezone.utc)
        session.flush()

    def mark_run_finished(self, session: Session, run: OpsRun, status: str, error_message: str | None = None) -> None:
        run.status = status
        run.ended_at = datetime.now(timezone.utc)
        run.error_message = error_message
        session.flush()