import os
import uuid
from contextlib import contextmanager
from datetime import date
from importlib import import_module
from typing import Iterator

from sqlalchemy import text
from sqlalchemy.orm import Session

from stock_quant_v2.trading_domain.tasks.generate_paper_orders import (
    GeneratePaperOrdersTaskRequest,
    generate_paper_orders,
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


def _get_env_date(name: str, default: str) -> date:
    value = os.getenv(name, default)
    return date.fromisoformat(value)


def _resolve_portfolio_id(session: Session) -> int:
    env_id = _get_env_int("M6_PAPER_PORTFOLIO_ID")
    if env_id is not None:
        exists = session.execute(
            text("select 1 from trading_paper_portfolio where id = :id"),
            {"id": env_id},
        ).scalar_one_or_none()
        if exists is None:
            raise ValueError(
                f"M6_PAPER_PORTFOLIO_ID={env_id} does not exist. "
                "Run bootstrap_m6_paper_account first or use M6_PAPER_PORTFOLIO_CODE."
            )
        return env_id

    portfolio_code = os.getenv(
        "M6_PAPER_PORTFOLIO_CODE",
        "paper_alpha_selection_v1_default",
    )

    portfolio_id = session.execute(
        text(
            """
            select id
            from trading_paper_portfolio
            where portfolio_code = :portfolio_code
            order by id desc
            limit 1
            """
        ),
        {"portfolio_code": portfolio_code},
    ).scalar_one_or_none()

    if portfolio_id is None:
        raise ValueError(
            f"portfolio_code={portfolio_code} not found. "
            "Run bootstrap_m6_paper_account first."
        )

    return int(portfolio_id)


def _resolve_target_run_id(session: Session, portfolio_id: int) -> int:
    env_id = _get_env_int("M6_TARGET_RUN_ID")
    if env_id is not None:
        exists = session.execute(
            text(
                """
                select 1
                from trading_paper_target_position
                where run_id = :run_id
                  and portfolio_id = :portfolio_id
                limit 1
                """
            ),
            {
                "run_id": env_id,
                "portfolio_id": portfolio_id,
            },
        ).scalar_one_or_none()
        if exists is None:
            raise ValueError(
                f"M6_TARGET_RUN_ID={env_id} has no target positions "
                f"for portfolio_id={portfolio_id}."
            )
        return env_id

    target_run_id = session.execute(
        text(
            """
            select run_id
            from trading_paper_target_position
            where portfolio_id = :portfolio_id
            group by run_id
            order by run_id desc
            limit 1
            """
        ),
        {"portfolio_id": portfolio_id},
    ).scalar_one_or_none()

    if target_run_id is None:
        raise ValueError(
            "cannot resolve target_run_id. "
            "Run bootstrap_m6_target_position_chain first or set M6_TARGET_RUN_ID."
        )

    return int(target_run_id)


def _create_ops_run(
    session: Session,
    target_run_id: int,
    portfolio_id: int,
    effective_date: date,
) -> int:
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
        f'"chain":"paper_order",'
        f'"portfolio_id":{portfolio_id},'
        f'"target_run_id":{target_run_id},'
        f'"effective_date":"{effective_date.isoformat()}"'
        "}"
    )

    return int(
        session.execute(
            sql,
            {
                "run_uid": str(uuid.uuid4()),
                "run_type": "paper_order",
                "run_name": "M6 Paper Order First Chain",
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
    effective_date = _get_env_date("M6_EFFECTIVE_DATE", "2026-04-20")

    with _open_session() as session:
        portfolio_id = _resolve_portfolio_id(session)
        target_run_id = _resolve_target_run_id(session, portfolio_id=portfolio_id)

        order_run_id = _create_ops_run(
            session=session,
            target_run_id=target_run_id,
            portfolio_id=portfolio_id,
            effective_date=effective_date,
        )

        request = GeneratePaperOrdersTaskRequest(
            order_run_id=order_run_id,
            target_run_id=target_run_id,
            portfolio_id=portfolio_id,
            effective_date=effective_date,
        )

        result = generate_paper_orders(session=session, request=request)
        _mark_ops_run_success(session=session, run_id=order_run_id)

    print(
        {
            "order_run_id": result.order_run_id,
            "target_run_id": result.target_run_id,
            "portfolio_id": result.portfolio_id,
            "effective_date": result.effective_date.isoformat(),
            "order_count": result.order_count,
            "status": result.status,
        }
    )


if __name__ == "__main__":
    main()