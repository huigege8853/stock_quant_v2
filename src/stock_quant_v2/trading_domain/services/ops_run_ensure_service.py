from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class EnsuredRun:
    run_id: int
    existed: bool
    inserted: bool
    run_role: str


class OpsRunEnsureService:
    """Ensure ops_run placeholder rows exist for explicitly supplied run ids."""

    TABLE_NAME = "ops_run"

    def __init__(self, session: Session):
        self.session = session

    def ensure_many(
        self,
        *,
        run_ids_by_role: dict[str, int | None],
        portfolio_id: int,
        effective_date: date,
        as_of_date: date | None = None,
        module_code: str = "M7",
        run_prefix: str = "m7_6_paper_trading",
    ) -> list[EnsuredRun]:
        results: list[EnsuredRun] = []
        for role, run_id in run_ids_by_role.items():
            if run_id is None or int(run_id) <= 0:
                continue
            results.append(
                self.ensure_one(
                    run_id=int(run_id),
                    run_role=role,
                    portfolio_id=portfolio_id,
                    effective_date=effective_date,
                    as_of_date=as_of_date,
                    module_code=module_code,
                    run_prefix=run_prefix,
                )
            )
        return results

    def ensure_one(
        self,
        *,
        run_id: int,
        run_role: str,
        portfolio_id: int,
        effective_date: date,
        as_of_date: date | None = None,
        module_code: str = "M7",
        run_prefix: str = "m7_6_paper_trading",
    ) -> EnsuredRun:
        if self._exists(run_id):
            return EnsuredRun(run_id=run_id, existed=True, inserted=False, run_role=run_role)

        columns = self._get_column_meta()
        if "id" not in columns:
            raise RuntimeError("ops_run 缺少 id 字段，无法创建 run 占位记录")

        now = datetime.utcnow()
        payload: dict[str, Any] = {}

        for column, meta in columns.items():
            if column == "id":
                payload[column] = run_id
                continue

            if meta.get("column_default") is not None and column not in {
                "run_code",
                "run_name",
                "run_type",
                "module_code",
                "status",
                "trigger_type",
                "started_at",
                "start_time",
                "created_at",
                "updated_at",
            }:
                continue

            value = self._semantic_value(
                column=column,
                meta=meta,
                run_id=run_id,
                run_role=run_role,
                portfolio_id=portfolio_id,
                effective_date=effective_date,
                as_of_date=as_of_date or effective_date,
                module_code=module_code,
                run_prefix=run_prefix,
                now=now,
            )

            if value is None and meta.get("is_nullable") == "YES":
                continue

            if value is None:
                value = self._default_for_type(meta=meta, effective_date=effective_date, now=now)

            payload[column] = value

        self._insert(payload)
        self._repair_sequence()
        return EnsuredRun(run_id=run_id, existed=False, inserted=True, run_role=run_role)

    def _exists(self, run_id: int) -> bool:
        row = self.session.execute(
            text("select 1 from ops_run where id = :run_id limit 1"),
            {"run_id": run_id},
        ).first()
        return row is not None

    def _get_column_meta(self) -> dict[str, dict[str, Any]]:
        rows = self.session.execute(
            text(
                """
                select column_name, data_type, is_nullable, column_default, udt_name
                from information_schema.columns
                where table_schema = 'public'
                  and table_name = :table_name
                order by ordinal_position
                """
            ),
            {"table_name": self.TABLE_NAME},
        ).mappings().all()
        if not rows:
            raise RuntimeError("找不到 ops_run 表")
        return {row["column_name"]: dict(row) for row in rows}

    def _insert(self, payload: dict[str, Any]) -> None:
        columns = list(payload.keys())
        column_sql = ", ".join([f'"{col}"' for col in columns])
        value_sql = ", ".join([f":{col}" for col in columns])
        self.session.execute(
            text(
                f"""
                insert into ops_run ({column_sql})
                values ({value_sql})
                """
            ),
            payload,
        )

    def _repair_sequence(self) -> None:
        self.session.execute(
            text(
                """
                do $$
                declare seq_name text;
                begin
                    select pg_get_serial_sequence('ops_run', 'id') into seq_name;
                    if seq_name is not null then
                        execute format(
                            'select setval(%L, greatest((select coalesce(max(id), 1) from ops_run), 1), true)',
                            seq_name
                        );
                    end if;
                end $$;
                """
            )
        )

    def _semantic_value(
        self,
        *,
        column: str,
        meta: dict[str, Any],
        run_id: int,
        run_role: str,
        portfolio_id: int,
        effective_date: date,
        as_of_date: date,
        module_code: str,
        run_prefix: str,
        now: datetime,
    ) -> Any:
        role = run_role.upper()
        code = f"{run_prefix}_{role.lower()}_{run_id}"

        if column in {"run_uid", "uid", "uuid", "run_uuid", "request_id", "trace_id"}:
            return str(uuid4())
        if self._is_uuid_type(meta):
            return str(uuid4())

        if column in {"run_code", "code", "name", "run_name", "task_name"}:
            return code
        if column in {"run_type", "type", "task_type"}:
            return "PAPER_TRADING"
        if column in {"module", "module_code", "domain_code"}:
            return module_code
        if column in {"status", "run_status"}:
            return "RUNNING"
        if column in {"trigger_type", "trigger", "source_type", "invocation_type"}:
            return "MANUAL"
        if column in {"portfolio_id"}:
            return portfolio_id
        if column in {"business_date", "effective_date", "trade_date", "run_date", "as_of_date"}:
            return effective_date if column != "as_of_date" else as_of_date
        if column in {"started_at", "start_time", "created_at", "updated_at", "created_time", "updated_time"}:
            return now
        if column in {"finished_at", "ended_at", "end_time"}:
            return None
        if column in {"parameters_json", "params_json", "config_json", "payload_json", "context_json", "metadata_json"}:
            return {
                "auto_created_by": "M7.6",
                "run_role": role,
                "portfolio_id": portfolio_id,
                "effective_date": effective_date.isoformat(),
            }
        if column in {"error_message", "error", "message", "remark", "remarks"}:
            return None
        return None

    def _default_for_type(self, *, meta: dict[str, Any], effective_date: date, now: datetime) -> Any:
        data_type = str(meta.get("data_type") or "").lower()
        if self._is_uuid_type(meta):
            return str(uuid4())
        if "int" in data_type:
            return 0
        if "numeric" in data_type or "double" in data_type or "real" in data_type:
            return Decimal("0")
        if data_type == "date":
            return effective_date
        if "timestamp" in data_type:
            return now
        if "bool" in data_type:
            return False
        if "json" in data_type:
            return {}
        return "UNKNOWN"

    @staticmethod
    def _is_uuid_type(meta: dict[str, Any]) -> bool:
        data_type = str(meta.get("data_type") or "").lower()
        udt_name = str(meta.get("udt_name") or "").lower()
        return data_type == "uuid" or udt_name == "uuid"
