from __future__ import annotations

import json
import os
from datetime import date
from typing import Any

from stock_quant_v2.data_domain.repositories.run_repository import RunRepository
from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.trading_domain.tasks.carry_forward_positions import (
    run_carry_forward_positions,
)


def _env_int(name: str, default: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        if default is None:
            raise RuntimeError(f"缺少环境变量: {name}")
        return default
    return int(raw)


def _env_date(name: str, default: str | None = None) -> date:
    raw = os.getenv(name) or default
    if not raw:
        raise RuntimeError(f"缺少环境变量: {name}")
    return date.fromisoformat(raw)


def _env_optional_date(name: str, default: str | None = None) -> date | None:
    raw = os.getenv(name) or default
    if not raw:
        return None
    return date.fromisoformat(raw)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _safe_mark_running(run_repo: RunRepository, session: Any, run: Any) -> None:
    fn = getattr(run_repo, "mark_run_running", None)
    if fn is not None:
        fn(session, run)


def _safe_mark_success(run_repo: RunRepository, session: Any, run: Any) -> None:
    for name in ("mark_run_success", "mark_run_succeeded", "mark_success"):
        fn = getattr(run_repo, name, None)
        if fn is not None:
            fn(session, run)
            return


def _safe_mark_failed(run_repo: RunRepository, session: Any, run: Any, error: Exception) -> None:
    for name in ("mark_run_failed", "mark_failed", "mark_run_error"):
        fn = getattr(run_repo, name, None)
        if fn is not None:
            try:
                fn(session, run, error_message=str(error))
            except TypeError:
                try:
                    fn(session, run, str(error))
                except TypeError:
                    fn(session, run)
            return


def main() -> None:
    source_position_run_id = _env_int("M7_SOURCE_POSITION_RUN_ID", 114)
    portfolio_id = _env_int("M7_PORTFOLIO_ID", 1)

    source_effective_date = _env_optional_date(
        "M7_SOURCE_EFFECTIVE_DATE",
        "2026-04-20",
    )
    target_effective_date = _env_date(
        "M7_TARGET_EFFECTIVE_DATE",
        "2026-04-21",
    )
    target_as_of_date = _env_optional_date(
        "M7_TARGET_AS_OF_DATE",
        target_effective_date.isoformat(),
    )
    replace_existing = _env_bool("M7_REPLACE_EXISTING", False)

    session = SessionLocal()
    run_repo = RunRepository()
    root_run = None

    try:
        root_run = run_repo.create_run(
            session=session,
            run_type="PAPER_TRADING",
            run_name="bootstrap_m7_paper_position_carry_chain",
            trigger_type="MANUAL",
            context_json={
                "module": "M7",
                "stage": "M7.1",
                "purpose": "paper_position_carry_forward_t_plus_1",
                "source_position_run_id": source_position_run_id,
                "portfolio_id": portfolio_id,
                "source_effective_date": source_effective_date.isoformat()
                if source_effective_date
                else None,
                "target_effective_date": target_effective_date.isoformat(),
                "target_as_of_date": target_as_of_date.isoformat()
                if target_as_of_date
                else None,
                "replace_existing": replace_existing,
            },
        )
        session.commit()

        _safe_mark_running(run_repo, session, root_run)
        session.commit()

        result = run_carry_forward_positions(
            session=session,
            source_position_run_id=source_position_run_id,
            target_position_run_id=root_run.id,
            portfolio_id=portfolio_id,
            source_effective_date=source_effective_date,
            target_effective_date=target_effective_date,
            target_as_of_date=target_as_of_date,
            replace_existing=replace_existing,
        )

        _safe_mark_success(run_repo, session, root_run)
        session.commit()

        output = {
            "m7_position_carry_run_id": root_run.id,
            **result,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2, default=str))

    except Exception as exc:
        session.rollback()
        if root_run is not None:
            try:
                _safe_mark_failed(run_repo, session, root_run, exc)
                session.commit()
            except Exception:
                session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()