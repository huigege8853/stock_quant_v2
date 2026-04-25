from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from stock_quant_v2.config.settings import settings
from stock_quant_v2.data_domain.tasks.backfill_adjust_factor import run_backfill_adjust_factor
from stock_quant_v2.db.session import SessionLocal, dispose_engine
from stock_quant_v2.scripts.bootstrap_meta_data_domain import main as bootstrap_meta_data_domain


def _build_akshare_api_client():
    try:
        import akshare as ak
    except ImportError as exc:
        raise ImportError("akshare is not installed. Please add it to pyproject.toml") from exc
    return ak


def _build_baostock_api_client():
    from stock_quant_v2.data_domain.providers.baostock.builder import build_baostock_api_client
    return build_baostock_api_client()


def _build_tushare_api_client():
    from stock_quant_v2.data_domain.providers.tushare.builder import build_tushare_api_client
    return build_tushare_api_client()


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


def _resolve_start_date() -> date:
    return settings.bootstrap_daily_bar_start_date


def _resolve_end_date() -> date:
    return settings.bootstrap_daily_bar_end_date


def main() -> None:
    bootstrap_meta_data_domain()

    try:
        baostock_api_client = _build_baostock_api_client()
        akshare_api_client = _build_akshare_api_client()
        tushare_api_client = _build_tushare_api_client()

        with SessionLocal() as session:
            session: Session

            root_run_id = 1
            data_version_id = _resolve_data_version_id(session=session, preferred_id=1)

            run_backfill_adjust_factor(
                session=session,
                baostock_api_client=baostock_api_client,
                akshare_api_client=akshare_api_client,
                tushare_api_client=tushare_api_client,
                run_id=root_run_id,
                data_version_id=data_version_id,
                start_date=_resolve_start_date(),
                end_date=_resolve_end_date(),
                chunk_days=5,
                max_workers=12,
            )

    finally:
        dispose_engine()


if __name__ == "__main__":
    main()