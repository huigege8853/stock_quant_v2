import json
import os
import uuid
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from importlib import import_module
from typing import Iterator

from sqlalchemy import text
from sqlalchemy.orm import Session

from stock_quant_v2.trading_domain.constants import (
    DEFAULT_PORTFOLIO_CONSTRUCTION_MODE,
    DEFAULT_TARGET_COUNT,
)
from stock_quant_v2.trading_domain.tasks.build_target_positions import (
    BuildTargetPositionsTaskRequest,
    build_target_positions,
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


def _get_env_decimal(name: str, default: str | None = None) -> Decimal | None:
    value = os.getenv(name)
    if value is None or value == "":
        if default is None:
            return None
        value = default
    return Decimal(str(value))


def _get_env_date(name: str, default: str) -> date:
    value = os.getenv(name, default)
    return date.fromisoformat(value)


def _create_ops_run(
    session: Session,
    source_signal_run_id: int,
    source_screen_request_id: int | None,
    as_of_date: date,
    effective_date: date,
    portfolio_id: int,
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

    context_json = json.dumps(
        {
            "module": "M6",
            "chain": "target_position",
            "stage": "M7.7_COMPAT_SIZING_ENABLED",
            "portfolio_id": portfolio_id,
            "source_signal_run_id": source_signal_run_id,
            "source_screen_request_id": source_screen_request_id,
            "as_of_date": as_of_date.isoformat(),
            "effective_date": effective_date.isoformat(),
        },
        ensure_ascii=False,
    )

    return int(
        session.execute(
            sql,
            {
                "run_uid": str(uuid.uuid4()),
                "run_type": "paper_target_position",
                "run_name": "M6 Paper Target Position First Chain",
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


def _resolve_portfolio_id(session: Session) -> int:
    env_id = _get_env_int("M6_PAPER_PORTFOLIO_ID")
    if env_id is not None:
        exists = session.execute(
            text("select 1 from trading_paper_portfolio where id = :id"),
            {"id": env_id},
        ).scalar_one_or_none()
        if exists is None:
            raise ValueError(
                f"M6_PAPER_PORTFOLIO_ID={env_id} does not exist in trading_paper_portfolio. "
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


def main() -> None:
    source_signal_run_id = _get_env_int("M6_SOURCE_SIGNAL_RUN_ID", 81)
    source_screen_request_id = _get_env_int("M6_SOURCE_SCREEN_REQUEST_ID", 3)
    as_of_date = _get_env_date("M6_AS_OF_DATE", "2026-04-17")
    effective_date = _get_env_date("M6_EFFECTIVE_DATE", "2026-04-20")

    if source_signal_run_id is None:
        raise ValueError("M6_SOURCE_SIGNAL_RUN_ID is required")

    with _open_session() as session:
        portfolio_id = _resolve_portfolio_id(session)

        run_id = _create_ops_run(
            session=session,
            source_signal_run_id=source_signal_run_id,
            source_screen_request_id=source_screen_request_id,
            as_of_date=as_of_date,
            effective_date=effective_date,
            portfolio_id=portfolio_id,
        )

        request = BuildTargetPositionsTaskRequest(
            run_id=run_id,
            portfolio_id=portfolio_id,
            source_signal_run_id=source_signal_run_id,
            source_screen_request_id=source_screen_request_id,
            as_of_date=as_of_date,
            effective_date=effective_date,
            construction_mode=os.getenv(
                "M6_PORTFOLIO_CONSTRUCTION_MODE",
                DEFAULT_PORTFOLIO_CONSTRUCTION_MODE,
            ),
            target_count=_get_env_int("M6_TARGET_COUNT", DEFAULT_TARGET_COUNT),
            long_only=True,
            sizing_mode=os.getenv("M6_TARGET_SIZING_MODE", "EQUAL_WEIGHT_BY_EQUITY"),
            sizing_capital=_get_env_decimal("M6_TARGET_SIZING_CAPITAL"),
            price_date=_get_env_date("M6_TARGET_PRICE_DATE", as_of_date.isoformat()),
            price_source=os.getenv("M6_TARGET_PRICE_SOURCE", "AS_OF_CLOSE"),
            lot_size=_get_env_decimal("M6_TARGET_LOT_SIZE", "100") or Decimal("100"),
            cash_buffer_rate=_get_env_decimal("M6_TARGET_CASH_BUFFER_RATE", "0") or Decimal("0"),
        )

        result = build_target_positions(session=session, request=request)
        _mark_ops_run_success(session=session, run_id=run_id)

    print(
        json.dumps(
            {
                "run_id": result.run_id,
                "portfolio_id": result.portfolio_id,
                "source_signal_run_id": result.source_signal_run_id,
                "source_screen_request_id": result.source_screen_request_id,
                "as_of_date": result.as_of_date.isoformat(),
                "effective_date": result.effective_date.isoformat(),
                "target_position_count": result.target_position_count,
                "target_quantity_total": str(result.target_quantity_total),
                "target_amount_total": str(result.target_amount_total),
                "zero_quantity_count": result.zero_quantity_count,
                "construction_mode": result.construction_mode,
                "sizing_mode": result.sizing_mode,
                "status": result.status,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
