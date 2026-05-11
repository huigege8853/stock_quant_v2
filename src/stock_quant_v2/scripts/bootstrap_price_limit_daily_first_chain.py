from __future__ import annotations

import os
from datetime import date, datetime
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


def _coerce_to_date(value: object | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    return None


def _resolve_date_range() -> tuple[date, date]:
    start_date = settings.bootstrap_daily_bar_start_date
    end_date = settings.bootstrap_daily_bar_end_date

    if start_date > end_date:
        raise ValueError(
            "BOOTSTRAP_DAILY_BAR_START_DATE must be <= BOOTSTRAP_DAILY_BAR_END_DATE "
            f"but got {start_date.isoformat()} > {end_date.isoformat()}"
        )

    return start_date, end_date


def _query_trading_calendar_dates(session: Session, start_date: date, end_date: date) -> list[date]:
    candidates = [
        ("meta_trading_calendar", "trade_date", "is_open"),
        ("meta_trading_calendar", "calendar_date", "is_open"),
        ("meta_trading_calendar", "trade_date", "is_trading_day"),
        ("meta_trading_calendar", "calendar_date", "is_trading_day"),
    ]

    for table_name, date_col, open_col in candidates:
        try:
            rows = session.execute(
                text(
                    f"""
                    SELECT DISTINCT {date_col} AS trade_date
                    FROM {table_name}
                    WHERE {open_col} = TRUE
                      AND {date_col} BETWEEN :start_date AND :end_date
                    ORDER BY {date_col}
                    """
                ),
                {"start_date": start_date, "end_date": end_date},
            ).all()
        except Exception:
            continue

        resolved = [_coerce_to_date(row._mapping.get("trade_date")) for row in rows]
        dates = [trade_date for trade_date in resolved if trade_date is not None]
        if dates:
            return dates

    return []


def _query_core_daily_bar_dates(session: Session, start_date: date, end_date: date) -> list[date]:
    try:
        rows = session.execute(
            text(
                """
                SELECT DISTINCT trade_date
                FROM core_daily_bar
                WHERE price_adjust_type = 'RAW'
                  AND trade_date BETWEEN :start_date AND :end_date
                ORDER BY trade_date
                """
            ),
            {"start_date": start_date, "end_date": end_date},
        ).all()
    except Exception:
        return []

    resolved = [_coerce_to_date(row._mapping.get("trade_date")) for row in rows]
    return [trade_date for trade_date in resolved if trade_date is not None]


def _resolve_target_trade_dates(session: Session, start_date: date, end_date: date) -> list[date]:
    calendar_dates = _query_trading_calendar_dates(session, start_date, end_date)
    if calendar_dates:
        return calendar_dates

    # Fallback only for damaged/incomplete calendar bootstrap states.  price_limit_daily
    # is derived from core_daily_bar, so RAW daily-bar dates are still valid trading
    # evidence and avoid iterating natural-calendar holidays/weekends.
    return _query_core_daily_bar_dates(session, start_date, end_date)


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
        start_date, end_date = _resolve_date_range()

        with SessionLocal() as session:
            session: Session

            data_version_id = _resolve_data_version_id(session=session, preferred_id=1)
            trade_dates = _resolve_target_trade_dates(session=session, start_date=start_date, end_date=end_date)

            if not trade_dates:
                print(
                    "[PRICE_LIMIT_DAILY] no trading dates to sync "
                    f"for range {start_date.isoformat()} -> {end_date.isoformat()}, skipped.",
                    flush=True,
                )
                return

            print(
                "[PRICE_LIMIT_DAILY] resolved trading dates: "
                f"{trade_dates[0].isoformat()} -> {trade_dates[-1].isoformat()} "
                f"count={len(trade_dates)}",
                flush=True,
            )

            for trade_date in trade_dates:
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
