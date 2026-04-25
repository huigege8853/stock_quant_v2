from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


class OpsRunRepository:
    """Research domain 内部使用的最小 ops_run 写入器。

    这里使用动态列检测，避免强依赖 ops_run 当前字段版本。
    如果 ops_run 存在未覆盖的 NOT NULL 字段，会明确抛错。
    """

    def __init__(self, session: Session):
        self.session = session

    def _columns(self) -> dict[str, dict[str, Any]]:
        rows = self.session.execute(
            text(
                """
                select
                    column_name,
                    is_nullable,
                    column_default,
                    data_type
                from information_schema.columns
                where table_schema = 'public'
                  and table_name = 'ops_run'
                """
            )
        ).mappings().all()

        if not rows:
            raise RuntimeError("ops_run table not found")

        return {row["column_name"]: dict(row) for row in rows}

    @staticmethod
    def _json_dumps(value: Any) -> str:
        return json.dumps(value or {}, ensure_ascii=False, default=str)

    def create_run(
        self,
        *,
        run_type: str,
        run_name: str,
        payload: dict[str, Any] | None = None,
    ) -> int:
        columns = self._columns()
        now = datetime.now(timezone.utc)
        payload = payload or {}

        run_uid = str(uuid.uuid4())
        run_code = f"m5-{run_type}-{now.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

        values: dict[str, Any] = {}

        candidates: dict[str, Any] = {
            "run_uid": run_uid,
            "run_type": run_type,
            "type": run_type,
            "run_category": "research",
            "category": "research",
            "module_code": "M5",
            "module": "M5",
            "task_code": run_type,
            "task_name": run_name,
            "run_name": run_name,
            "name": run_name,
            "run_code": run_code,
            "status": "RUNNING",
            "run_status": "RUNNING",
            "trigger_type": "MANUAL",
            "triggered_by": "manual",
            "created_by": "system",
            "started_at": now,
            "start_time": now,
            "created_at": now,
            "updated_at": now,
        }

        json_candidates = {
            "params": payload,
            "parameters": payload,
            "config_payload": payload,
            "request_payload": payload,
            "run_payload": payload,
            "metadata": payload,
            "meta": payload,
        }

        for col, value in candidates.items():
            if col in columns:
                values[col] = value

        for col, value in json_candidates.items():
            if col in columns:
                values[col] = value

        missing_required = []
        for col, meta in columns.items():
            if col == "id":
                continue

            has_default = meta["column_default"] is not None
            is_nullable = meta["is_nullable"] == "YES"

            if not is_nullable and not has_default and col not in values:
                missing_required.append(col)

        if missing_required:
            raise RuntimeError(
                "ops_run has required columns not handled by M5 OpsRunRepository: "
                + ", ".join(missing_required)
            )

        insert_cols = []
        insert_exprs = []
        params: dict[str, Any] = {}

        for col, value in values.items():
            insert_cols.append(col)

            data_type = columns[col]["data_type"]
            if data_type in {"json", "jsonb"}:
                insert_exprs.append(f"cast(:{col} as jsonb)")
                params[col] = self._json_dumps(value)
            else:
                insert_exprs.append(f":{col}")
                params[col] = value

        sql = f"""
            insert into ops_run ({", ".join(insert_cols)})
            values ({", ".join(insert_exprs)})
            returning id
        """

        run_id = self.session.execute(text(sql), params).scalar_one()
        return int(run_id)

    def mark_success(self, run_id: int) -> None:
        self._mark_done(run_id, status="SUCCESS", error_message=None)

    def mark_failed(self, run_id: int, error_message: str) -> None:
        self._mark_done(run_id, status="FAILED", error_message=error_message)

    def _mark_done(
        self,
        run_id: int,
        *,
        status: str,
        error_message: str | None,
    ) -> None:
        columns = self._columns()
        now = datetime.now(timezone.utc)

        set_values: dict[str, Any] = {}

        if "status" in columns:
            set_values["status"] = status
        if "run_status" in columns:
            set_values["run_status"] = status
        if "completed_at" in columns:
            set_values["completed_at"] = now
        if "end_time" in columns:
            set_values["end_time"] = now
        if "updated_at" in columns:
            set_values["updated_at"] = now
        if error_message and "error_message" in columns:
            set_values["error_message"] = error_message

        if not set_values:
            return

        assignments = ", ".join([f"{col} = :{col}" for col in set_values])
        params = dict(set_values)
        params["run_id"] = run_id

        self.session.execute(
            text(f"update ops_run set {assignments} where id = :run_id"),
            params,
        )