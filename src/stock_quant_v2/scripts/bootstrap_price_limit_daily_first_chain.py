from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from stock_quant_v2.config.settings import settings
from stock_quant_v2.data_domain.tasks.sync_price_limit_daily import run_sync_price_limit_daily
from stock_quant_v2.db.session import SessionLocal, dispose_engine
from stock_quant_v2.scripts.bootstrap_meta_data_domain import main as bootstrap_meta_data_domain


def _resolve_trade_date() -> date:
    return settings.bootstrap_daily_bar_start_date


def _resolve_data_version_id(session: Session, preferred_id: int | None = 1) -> int:
    if preferred_id is not None:
        exists = session.execute(
            text("SELECT 1 FROM meta_data_version WHERE id = :id"),
            {"id": preferred_id},
        ).scalar_one_or_none()
        if exists is not None:
            return int(preferred_id)

    latest_id = session.execute(
        text("SELECT MAX(id) FROM meta_data_version")
    ).scalar_one_or_none()

    if latest_id is None:
        raise ValueError("meta_data_version is empty; please create a data version first")

    return int(latest_id)


def main() -> None:
    bootstrap_meta_data_domain()

    try:
        root_run_id = 1
        trade_date = _resolve_trade_date()

        with SessionLocal() as session:
            session: Session

            data_version_id = _resolve_data_version_id(session=session, preferred_id=1)

            run_sync_price_limit_daily(
                session=session,
                run_id=root_run_id,
                data_version_id=data_version_id,
                trade_date=trade_date,
            )

    finally:
        dispose_engine()


if __name__ == "__main__":
    main()