import os
import uuid
from contextlib import contextmanager
from importlib import import_module
from typing import Iterator

from sqlalchemy import text
from sqlalchemy.orm import Session

from stock_quant_v2.trading_domain.tasks.build_trade_ledger import (
    BuildTradeLedgerTaskRequest,
    build_trade_ledger,
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


def _resolve_chain(session: Session) -> dict[str, int]:
    position_snapshot_run_id = _get_env_int("M6_POSITION_SNAPSHOT_RUN_ID")
    if position_snapshot_run_id is None:
        position_snapshot_run_id = session.execute(
            text(
                """
                select run_id
                from trading_paper_portfolio_snapshot
                order by run_id desc
                limit 1
                """
            )
        ).scalar_one_or_none()

    if position_snapshot_run_id is None:
        raise ValueError("Cannot resolve M6_POSITION_SNAPSHOT_RUN_ID.")

    fill_run_id = _get_env_int("M6_FILL_RUN_ID") or _get_context_int(
        session=session,
        run_id=position_snapshot_run_id,
        key="fill_run_id",
    )
    if fill_run_id is None:
        raise ValueError("Cannot resolve fill_run_id.")

    order_run_id = _get_env_int("M6_ORDER_RUN_ID") or _get_context_int(
        session=session,
        run_id=fill_run_id,
        key="order_run_id",
    )
    if order_run_id is None:
        raise ValueError("Cannot resolve order_run_id.")

    target_run_id = _get_env_int("M6_TARGET_RUN_ID") or _get_context_int(
        session=session,
        run_id=order_run_id,
        key="target_run_id",
    )
    if target_run_id is None:
        raise ValueError("Cannot resolve target_run_id.")

    portfolio_id = _get_env_int("M6_PAPER_PORTFOLIO_ID") or _get_context_int(
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

    return {
        "target_run_id": int(target_run_id),
        "order_run_id": int(order_run_id),
        "fill_run_id": int(fill_run_id),
        "position_snapshot_run_id": int(position_snapshot_run_id),
        "portfolio_id": int(portfolio_id),
    }


def _create_ops_run(session: Session, chain: dict[str, int]) -> int:
    sql = text(
        """
        insert into ops_run (
            run_uid,
            run_type,
            run_name,
            status,
            trigger_type,
            requested_at,
            started_at,
            context_json
        )
        values (
            :run_uid,
            :run_type,
            :run_name,
            :status,
            :trigger_type,
            now(),
            now(),
            cast(:context_json as jsonb)
        )
        returning id
        """
    )

    context_json = (
        "{"
        f'"module":"M6",'
        f'"chain":"trade_ledger",'
        f'"portfolio_id":{chain["portfolio_id"]},'
        f'"target_run_id":{chain["target_run_id"]},'
        f'"order_run_id":{chain["order_run_id"]},'
        f'"fill_run_id":{chain["fill_run_id"]},'
        f'"position_snapshot_run_id":{chain["position_snapshot_run_id"]}'
        "}"
    )

    return int(
        session.execute(
            sql,
            {
                "run_uid": str(uuid.uuid4()),
                "run_type": "paper_trade_ledger",
                "run_name": "M6 Paper Trade Ledger First Chain",
                "status": "RUNNING",
                "trigger_type": "MANUAL",
                "context_json": context_json,
            },
        ).scalar_one()
    )


def _mark_ops_run_success(session: Session, run_id: int) -> None:
    session.execute(
        text(
            """
            update ops_run
            set status = 'SUCCESS',
                ended_at = now(),
                updated_at = now()
            where id = :run_id
            """
        ),
        {"run_id": run_id},
    )


def main() -> None:
    with _open_session() as session:
        chain = _resolve_chain(session)
        ledger_run_id = _create_ops_run(session=session, chain=chain)

        result = build_trade_ledger(
            session=session,
            request=BuildTradeLedgerTaskRequest(
                ledger_run_id=ledger_run_id,
                portfolio_id=chain["portfolio_id"],
                target_run_id=chain["target_run_id"],
                order_run_id=chain["order_run_id"],
                fill_run_id=chain["fill_run_id"],
                position_snapshot_run_id=chain["position_snapshot_run_id"],
            ),
        )

        _mark_ops_run_success(session=session, run_id=ledger_run_id)

    print(
        {
            "ledger_run_id": result.ledger_run_id,
            "portfolio_id": result.portfolio_id,
            "target_run_id": result.target_run_id,
            "order_run_id": result.order_run_id,
            "fill_run_id": result.fill_run_id,
            "position_snapshot_run_id": result.position_snapshot_run_id,
            "ledger_count": result.ledger_count,
            "status": result.status,
        }
    )


if __name__ == "__main__":
    main()