import os
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from importlib import import_module
from typing import Iterator

from sqlalchemy.orm import Session

from stock_quant_v2.trading_domain.constants import (
    DEFAULT_INITIAL_CASH,
    DEFAULT_PAPER_ACCOUNT_CODE,
    DEFAULT_PAPER_PORTFOLIO_CODE,
)
from stock_quant_v2.trading_domain.tasks.seed_paper_trading_account import (
    SeedPaperTradingAccountRequest,
    seed_paper_trading_account,
)


@contextmanager
def _open_session() -> Iterator[Session]:
    """
    Compatible session opener.

    Preferred:
        stock_quant_v2.db.session.SessionLocal

    If your project uses another session factory name,
    only adjust this helper.
    """
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


def _get_env_decimal(name: str, default: Decimal) -> Decimal:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return Decimal(value)


def _get_env_date(name: str, default: str) -> date:
    value = os.getenv(name, default)
    return date.fromisoformat(value)


def main() -> None:
    request = SeedPaperTradingAccountRequest(
        account_code=os.getenv("M6_PAPER_ACCOUNT_CODE", DEFAULT_PAPER_ACCOUNT_CODE),
        portfolio_code=os.getenv("M6_PAPER_PORTFOLIO_CODE", DEFAULT_PAPER_PORTFOLIO_CODE),
        strategy_version_id=_get_env_int("M6_STRATEGY_VERSION_ID", 1),
        execution_assumption_profile_id=_get_env_int(
            "M6_EXECUTION_ASSUMPTION_PROFILE_ID",
            1,
        ),
        source_signal_run_id=_get_env_int("M6_SOURCE_SIGNAL_RUN_ID", 53),
        source_screen_request_id=_get_env_int("M6_SOURCE_SCREEN_REQUEST_ID", 3),
        start_date=_get_env_date("M6_START_DATE", "2024-04-01"),
        initial_cash=_get_env_decimal("M6_INITIAL_CASH", DEFAULT_INITIAL_CASH),
    )

    if request.strategy_version_id is None:
        raise ValueError("M6_STRATEGY_VERSION_ID is required")

    if request.execution_assumption_profile_id is None:
        raise ValueError("M6_EXECUTION_ASSUMPTION_PROFILE_ID is required")

    with _open_session() as session:
        result = seed_paper_trading_account(session=session, request=request)

    print(
        {
            "account_id": result.account_id,
            "account_code": result.account_code,
            "portfolio_id": result.portfolio_id,
            "portfolio_code": result.portfolio_code,
            "strategy_version_id": result.strategy_version_id,
            "execution_assumption_profile_id": result.execution_assumption_profile_id,
            "source_signal_run_id": result.source_signal_run_id,
            "source_screen_request_id": result.source_screen_request_id,
            "initial_cash": str(result.initial_cash),
            "status": result.status,
        }
    )


if __name__ == "__main__":
    main()