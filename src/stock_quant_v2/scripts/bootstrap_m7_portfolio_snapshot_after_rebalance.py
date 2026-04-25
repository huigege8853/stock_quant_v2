from __future__ import annotations

import json
import os
from datetime import date
from typing import Any

from stock_quant_v2.data_domain.repositories.run_repository import RunRepository
from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.trading_domain.tasks.build_portfolio_snapshot_m7 import (
    run_build_portfolio_snapshot_m7,
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
    previous_snapshot_run_id = _env_int("M7_PREVIOUS_SNAPSHOT_RUN_ID", 114)
    position_run_id = _env_int("M7_POSITION_RUN_ID", 131)
    fill_run_id = _env_int("M7_FILL_RUN_ID", 126)
    portfolio_id = _env_int("M7_PORTFOLIO_ID", 1)
    snapshot_date = _env_date("M7_SNAPSHOT_DATE", "2026-04-21")
    replace_existing = _env_bool("M7_REPLACE_EXISTING", False)

    session = SessionLocal()
    run_repo = RunRepository()
    root_run = None

    try:
        root_run = run_repo.create_run(
            session=session,
            run_type="PAPER_TRADING",
            run_name="bootstrap_m7_portfolio_snapshot_after_rebalance",
            trigger_type="MANUAL",
            context_json={
                "module": "M7",
                "stage": "M7.3-C",
                "purpose": "portfolio_snapshot_after_rebalance",
                "previous_snapshot_run_id": previous_snapshot_run_id,
                "position_run_id": position_run_id,
                "fill_run_id": fill_run_id,
                "portfolio_id": portfolio_id,
                "snapshot_date": snapshot_date.isoformat(),
                "replace_existing": replace_existing,
            },
        )
        session.commit()

        _safe_mark_running(run_repo, session, root_run)
        session.commit()

        result = run_build_portfolio_snapshot_m7(
            session=session,
            snapshot_run_id=root_run.id,
            previous_snapshot_run_id=previous_snapshot_run_id,
            position_run_id=position_run_id,
            fill_run_id=fill_run_id,
            portfolio_id=portfolio_id,
            snapshot_date=snapshot_date,
            replace_existing=replace_existing,
        )

        _safe_mark_success(run_repo, session, root_run)
        session.commit()

        output = {
            "m7_portfolio_snapshot_run_id": root_run.id,
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