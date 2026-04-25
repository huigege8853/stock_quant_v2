import os
from contextlib import contextmanager
from importlib import import_module
from typing import Iterator

from sqlalchemy import text
from sqlalchemy.orm import Session

from stock_quant_v2.trading_domain.services.paper_run_result_service import (
    PaperRunResultService,
)


@contextmanager
def _open_session() -> Iterator[Session]:
    db_session_module = import_module("stock_quant_v2.db.session")

    if hasattr(db_session_module, "SessionLocal"):
        session = db_session_module.SessionLocal()
    elif hasattr(db_session_module, "get_session"):
        maybe_session = db_session_module.get_session()
        if hasattr(maybe_session, "__enter__"):
            with maybe_session as session:
                yield session
                return
        session = maybe_session
    else:
        raise RuntimeError(
            "Cannot find SessionLocal or get_session in stock_quant_v2.db.session"
        )

    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _get_env_int(name: str, default: int | None = None) -> int | None:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def _get_context_int(session: Session, run_id: int, key: str) -> int | None:
    value = session.execute(
        text(
            """
            select context_json ->> :key
            from ops_run
            where id = :run_id
            """
        ),
        {
            "run_id": run_id,
            "key": key,
        },
    ).scalar_one_or_none()

    if value is None or value == "":
        return None

    return int(value)


def _resolve_latest_snapshot_run_id(session: Session) -> int:
    run_id = session.execute(
        text(
            """
            select run_id
            from trading_paper_portfolio_snapshot
            order by run_id desc
            limit 1
            """
        )
    ).scalar_one_or_none()

    if run_id is None:
        raise ValueError("Cannot resolve latest position snapshot run_id.")

    return int(run_id)


def _resolve_chain(session: Session) -> dict[str, int | None]:
    position_snapshot_run_id = _get_env_int("M6_POSITION_SNAPSHOT_RUN_ID")
    if position_snapshot_run_id is None:
        position_snapshot_run_id = _resolve_latest_snapshot_run_id(session)

    fill_run_id = _get_env_int("M6_FILL_RUN_ID")
    if fill_run_id is None:
        fill_run_id = _get_context_int(
            session=session,
            run_id=position_snapshot_run_id,
            key="fill_run_id",
        )

    if fill_run_id is None:
        raise ValueError("Cannot resolve fill_run_id.")

    order_run_id = _get_env_int("M6_ORDER_RUN_ID")
    if order_run_id is None:
        order_run_id = _get_context_int(
            session=session,
            run_id=fill_run_id,
            key="order_run_id",
        )

    if order_run_id is None:
        raise ValueError("Cannot resolve order_run_id.")

    target_run_id = _get_env_int("M6_TARGET_RUN_ID")
    if target_run_id is None:
        target_run_id = _get_context_int(
            session=session,
            run_id=order_run_id,
            key="target_run_id",
        )

    if target_run_id is None:
        raise ValueError("Cannot resolve target_run_id.")

    portfolio_id = _get_env_int("M6_PAPER_PORTFOLIO_ID")
    if portfolio_id is None:
        portfolio_id = _get_context_int(
            session=session,
            run_id=position_snapshot_run_id,
            key="portfolio_id",
        )

    if portfolio_id is None:
        portfolio_id = session.execute(
            text(
                """
                select portfolio_id
                from trading_paper_portfolio_snapshot
                where run_id = :run_id
                limit 1
                """
            ),
            {"run_id": position_snapshot_run_id},
        ).scalar_one()

    ledger_run_id = _get_env_int("M6_LEDGER_RUN_ID")
    if ledger_run_id is None:
        ledger_run_id = session.execute(
            text(
                """
                select id
                from ops_run
                where run_type = 'paper_trade_ledger'
                  and context_json ->> 'position_snapshot_run_id' = :position_snapshot_run_id
                order by id desc
                limit 1
                """
            ),
            {"position_snapshot_run_id": str(position_snapshot_run_id)},
        ).scalar_one_or_none()

    return {
        "result_run_id": int(position_snapshot_run_id),
        "target_run_id": int(target_run_id),
        "order_run_id": int(order_run_id),
        "fill_run_id": int(fill_run_id),
        "position_snapshot_run_id": int(position_snapshot_run_id),
        "portfolio_id": int(portfolio_id),
        "ledger_run_id": int(ledger_run_id) if ledger_run_id is not None else None,
    }


def main() -> None:
    with _open_session() as session:
        chain = _resolve_chain(session)

        service = PaperRunResultService(session)
        result = service.write_results_for_chain(
            result_run_id=chain["result_run_id"],
            portfolio_id=chain["portfolio_id"],
            target_run_id=chain["target_run_id"],
            order_run_id=chain["order_run_id"],
            fill_run_id=chain["fill_run_id"],
            position_snapshot_run_id=chain["position_snapshot_run_id"],
            ledger_run_id=chain["ledger_run_id"],
        )

    print(
        {
            "result_run_id": result["result_run_id"],
            "portfolio_id": result["portfolio_id"],
            "snapshot_date": result["snapshot_date"],
            "target_run_id": chain["target_run_id"],
            "order_run_id": chain["order_run_id"],
            "fill_run_id": chain["fill_run_id"],
            "position_snapshot_run_id": chain["position_snapshot_run_id"],
            "ledger_run_id": chain["ledger_run_id"],
            "metric_written": result["metric_written"],
            "series_written": result["series_written"],
            "status": "SUCCESS",
        }
    )


if __name__ == "__main__":
    main()