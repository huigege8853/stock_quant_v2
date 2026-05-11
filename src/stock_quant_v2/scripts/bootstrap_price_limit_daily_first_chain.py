from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session


def _load_env_file(env_file: str | Path = ".env.research") -> Path | None:
    """Load a dotenv-style file before Settings is imported.

    This bootstrap script is often executed directly with only
    BOOTSTRAP_DAILY_BAR_START_DATE / BOOTSTRAP_DAILY_BAR_END_DATE in the shell.
    Loading .env.research here keeps the entrypoint consistent with newer M4/M5
    bootstrap scripts and prevents V2_SQLALCHEMY_URL from being missing during
    Settings validation.
    """
    path = Path(env_file)
    if not path.exists():
        return None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not ((value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'"))):
            value = value.split(" #", 1)[0].strip()
        value = value.strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value

    return path.resolve()


_LOADED_ENV_PATH = _load_env_file()
print(f"ENV_LOADED={_LOADED_ENV_PATH if _LOADED_ENV_PATH is not None else False}", flush=True)

from stock_quant_v2.config.settings import settings
from stock_quant_v2.data_domain.tasks.sync_price_limit_daily import run_sync_price_limit_daily
from stock_quant_v2.db.session import SessionLocal, dispose_engine
from stock_quant_v2.scripts.bootstrap_meta_data_domain import main as bootstrap_meta_data_domain


def _date_iter(start_date: date, end_date: date):
    current = start_date
    while current <= end_date:
        yield current
        current = date.fromordinal(current.toordinal() + 1)


def _resolve_trade_dates() -> tuple[date, date]:
    start_date = settings.bootstrap_daily_bar_start_date
    end_date = settings.bootstrap_daily_bar_end_date

    if start_date > end_date:
        raise ValueError(
            "BOOTSTRAP_DAILY_BAR_START_DATE must be <= BOOTSTRAP_DAILY_BAR_END_DATE "
            f"but got {start_date.isoformat()} > {end_date.isoformat()}"
        )

    return start_date, end_date


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
        start_date, end_date = _resolve_trade_dates()

        with SessionLocal() as session:
            session: Session

            data_version_id = _resolve_data_version_id(session=session, preferred_id=1)

            for trade_date in _date_iter(start_date, end_date):
                print(f"[PRICE_LIMIT_DAILY] sync {trade_date.isoformat()}", flush=True)
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
