from __future__ import annotations

import json
import os
import uuid
from datetime import date
from typing import Any

from sqlalchemy import text

from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.risk_domain.dto.risk import ApplyRiskToTargetRequestDTO
from stock_quant_v2.risk_domain.services.risk_profile_seed_service import DEFAULT_PROFILE_CODE
from stock_quant_v2.risk_domain.tasks.apply_risk_to_target import apply_risk_to_target


def _env_int(name: str, default: int | None = None) -> int | None:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y"}


def _env_date(name: str, default: date | None = None) -> date | None:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return date.fromisoformat(raw)


def _run_exists(session, run_id: int) -> bool:
    return session.execute(
        text("select 1 from ops_run where id = :id"),
        {"id": run_id},
    ).scalar_one_or_none() is not None


def _create_ops_run(session, *, run_id: int | None, run_type: str, run_name: str, context: dict[str, Any]) -> int:
    cols = _get_columns(session, "ops_run")
    now_expr = "now()"

    payload: dict[str, Any] = {}
    if run_id is not None and "id" in cols:
        payload["id"] = run_id
    if "run_uid" in cols:
        payload["run_uid"] = str(uuid.uuid4())
    if "run_type" in cols:
        payload["run_type"] = run_type
    if "run_name" in cols:
        payload["run_name"] = run_name
    if "status" in cols:
        payload["status"] = "RUNNING"
    if "trigger_type" in cols:
        payload["trigger_type"] = "MANUAL"
    if "requested_at" in cols:
        payload["requested_at"] = "__NOW__"
    if "started_at" in cols:
        payload["started_at"] = "__NOW__"
    if "created_at" in cols:
        payload["created_at"] = "__NOW__"
    if "updated_at" in cols:
        payload["updated_at"] = "__NOW__"
    if "context_json" in cols:
        payload["context_json"] = json.dumps(context, ensure_ascii=False)

    insert_cols = list(payload.keys())
    values_sql = []
    params = {}
    for col in insert_cols:
        if payload[col] == "__NOW__":
            values_sql.append(now_expr)
        elif col == "context_json":
            values_sql.append("cast(:context_json as jsonb)")
            params[col] = payload[col]
        else:
            values_sql.append(f":{col}")
            params[col] = payload[col]

    col_sql = ", ".join(insert_cols)
    val_sql = ", ".join(values_sql)

    return int(
        session.execute(
            text(
                f"""
                insert into ops_run ({col_sql})
                values ({val_sql})
                returning id
                """
            ),
            params,
        ).scalar_one()
    )


def _ensure_ops_run(session, *, run_id: int | None, run_type: str, run_name: str, context: dict[str, Any]) -> int:
    if run_id is not None and _run_exists(session, run_id):
        return run_id
    return _create_ops_run(
        session,
        run_id=run_id,
        run_type=run_type,
        run_name=run_name,
        context=context,
    )


def _mark_success(session, run_id: int) -> None:
    cols = _get_columns(session, "ops_run")
    assignments = []
    if "status" in cols:
        assignments.append("status = 'SUCCESS'")
    if "ended_at" in cols:
        assignments.append("ended_at = now()")
    if "updated_at" in cols:
        assignments.append("updated_at = now()")
    if not assignments:
        return
    session.execute(
        text(f"update ops_run set {', '.join(assignments)} where id = :run_id"),
        {"run_id": run_id},
    )


def _mark_failed(session, run_id: int, exc: Exception) -> None:
    cols = _get_columns(session, "ops_run")
    assignments = []
    params = {"run_id": run_id, "error_message": str(exc)[:1000]}
    if "status" in cols:
        assignments.append("status = 'FAILED'")
    if "error_message" in cols:
        assignments.append("error_message = :error_message")
    if "ended_at" in cols:
        assignments.append("ended_at = now()")
    if "updated_at" in cols:
        assignments.append("updated_at = now()")
    if assignments:
        session.execute(
            text(f"update ops_run set {', '.join(assignments)} where id = :run_id"),
            params,
        )


def _get_columns(session, table_name: str) -> set[str]:
    rows = session.execute(
        text(
            """
            select column_name
            from information_schema.columns
            where table_schema = 'public'
              and table_name = :table_name
            """
        ),
        {"table_name": table_name},
    ).all()
    return {r[0] for r in rows}


def main() -> None:
    source_target_run_id = _env_int("M7_RISK_SOURCE_TARGET_RUN_ID", 155)
    portfolio_id = _env_int("M7_PORTFOLIO_ID", 1)
    if source_target_run_id is None or portfolio_id is None:
        raise RuntimeError("M7_RISK_SOURCE_TARGET_RUN_ID and M7_PORTFOLIO_ID are required")

    risk_profile_code = os.getenv("M7_RISK_PROFILE_CODE", DEFAULT_PROFILE_CODE)
    current_position_run_id = _env_int("M7_RISK_CURRENT_POSITION_RUN_ID", None)
    as_of_date = _env_date("M7_RISK_AS_OF_DATE")
    effective_date = _env_date("M7_RISK_EFFECTIVE_DATE")
    replace_existing = _env_bool("M7_RISK_REPLACE_EXISTING", False)

    requested_risk_run_id = _env_int("M7_RISK_RUN_ID", None)
    requested_adjusted_target_run_id = _env_int("M7_RISK_ADJUSTED_TARGET_RUN_ID", None)

    session = SessionLocal()
    risk_run_id: int | None = None
    adjusted_target_run_id: int | None = None

    try:
        context = {
            "module": "M7-Risk",
            "stage": "M7-Risk.1",
            "source_target_run_id": source_target_run_id,
            "portfolio_id": portfolio_id,
            "risk_profile_code": risk_profile_code,
            "current_position_run_id": current_position_run_id,
        }

        risk_run_id = _ensure_ops_run(
            session,
            run_id=requested_risk_run_id,
            run_type="PAPER_RISK",
            run_name="M7 Risk Apply To Target",
            context=context,
        )

        adjusted_target_run_id = _ensure_ops_run(
            session,
            run_id=requested_adjusted_target_run_id,
            run_type="RISK_ADJ_TARGET",
            run_name="M7 Risk Adjusted Target Position",
            context=context,
        )

        result = apply_risk_to_target(
            session=session,
            request=ApplyRiskToTargetRequestDTO(
                source_target_run_id=source_target_run_id,
                adjusted_target_run_id=adjusted_target_run_id,
                risk_run_id=risk_run_id,
                portfolio_id=portfolio_id,
                risk_profile_code=risk_profile_code,
                as_of_date=as_of_date,
                effective_date=effective_date,
                current_position_run_id=current_position_run_id,
                replace_existing=replace_existing,
            ),
        )
        _mark_success(session, risk_run_id)
        _mark_success(session, adjusted_target_run_id)
        session.commit()

        print(json.dumps(result.__dict__, ensure_ascii=False, indent=2, default=str))

    except Exception as exc:
        session.rollback()
        if risk_run_id is not None:
            try:
                _mark_failed(session, risk_run_id, exc)
                session.commit()
            except Exception:
                session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
