from __future__ import annotations

import json
import os
from datetime import date
from typing import Any

from stock_quant_v2.data_domain.repositories.run_repository import RunRepository
from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.trading_domain.tasks.generate_rebalance_orders import (
    run_generate_rebalance_orders,
)


def _env_int(name: str, default: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        if default is None:
            raise RuntimeError(f"缺少环境变量: {name}")
        return default
    return int(raw)


def _env_optional_int(name: str, default: int | None = None) -> int | None:
    raw = os.getenv(name)
    if raw is None or raw == "":
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


def _env_str(name: str, default: str) -> str:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip()


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
    current_position_run_id = _env_int("M7_CURRENT_POSITION_RUN_ID", 116)
    target_position_run_id = _env_int("M7_TARGET_POSITION_RUN_ID")
    portfolio_id = _env_int("M7_PORTFOLIO_ID", 1)

    effective_date = _env_date("M7_EFFECTIVE_DATE", "2026-04-21")
    as_of_date = _env_optional_date("M7_AS_OF_DATE", effective_date.isoformat())

    template_order_run_id = _env_optional_int("M7_TEMPLATE_ORDER_RUN_ID", None)
    target_quantity_source = _env_str("M7_TARGET_QUANTITY_SOURCE", "AUTO").upper()

    replace_existing = _env_bool("M7_REPLACE_EXISTING", False)
    write_hold_orders = _env_bool("M7_WRITE_HOLD_ORDERS", False)

    session = SessionLocal()
    run_repo = RunRepository()
    root_run = None

    try:
        root_run = run_repo.create_run(
            session=session,
            run_type="PAPER_TRADING",
            run_name="bootstrap_m7_paper_rebalance_order_chain",
            trigger_type="MANUAL",
            context_json={
                "module": "M7",
                "stage": "M7.2",
                "purpose": "paper_rebalance_order_generation",
                "current_position_run_id": current_position_run_id,
                "target_position_run_id": target_position_run_id,
                "portfolio_id": portfolio_id,
                "effective_date": effective_date.isoformat(),
                "as_of_date": as_of_date.isoformat() if as_of_date else None,
                "template_order_run_id": template_order_run_id,
                "target_quantity_source": target_quantity_source,
                "replace_existing": replace_existing,
                "write_hold_orders": write_hold_orders,
            },
        )
        session.commit()

        _safe_mark_running(run_repo, session, root_run)
        session.commit()

        result = run_generate_rebalance_orders(
            session=session,
            order_run_id=root_run.id,
            portfolio_id=portfolio_id,
            current_position_run_id=current_position_run_id,
            target_position_run_id=target_position_run_id,
            effective_date=effective_date,
            as_of_date=as_of_date,
            template_order_run_id=template_order_run_id,
            target_quantity_source=target_quantity_source,
            replace_existing=replace_existing,
            write_hold_orders=write_hold_orders,
        )

        _safe_mark_success(run_repo, session, root_run)
        session.commit()

        output = {
            "m7_rebalance_order_run_id": root_run.id,
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