from __future__ import annotations

from contextlib import suppress
from datetime import date

from sqlalchemy.orm import Session

from stock_quant_v2.config.settings import settings
from stock_quant_v2.data_domain.tasks.sync_fundamental_snapshot import run_sync_fundamental_snapshot
from stock_quant_v2.db.session import SessionLocal, dispose_engine
from stock_quant_v2.scripts.bootstrap_meta_data_domain import main as bootstrap_meta_data_domain


def _build_akshare_api_client():
    try:
        import akshare as ak
    except ImportError as exc:
        raise ImportError("akshare is not installed. Please add it to pyproject.toml") from exc
    return ak


def _build_tushare_api_client():
    from stock_quant_v2.data_domain.providers.tushare.builder import build_tushare_api_client

    return build_tushare_api_client()


def _resolve_trade_date() -> date:
    # 第一版先直接复用 daily bar 的 bootstrap 起始日
    return settings.bootstrap_daily_bar_start_date


def main() -> None:
    # 1) metadata bootstrap
    bootstrap_meta_data_domain()

    akshare_api_client = None
    tushare_api_client = None

    try:
        # 2) provider clients
        akshare_api_client = _build_akshare_api_client()
        tushare_api_client = _build_tushare_api_client()

        # phase-1 temporary run id
        root_run_id = 1

        # fixed version id for current stage
        data_version_id = 1

        trade_date = _resolve_trade_date()

        with SessionLocal() as session:
            session: Session

            run_sync_fundamental_snapshot(
                session=session,
                akshare_api_client=akshare_api_client,
                tushare_api_client=tushare_api_client,
                run_id=root_run_id,
                data_version_id=data_version_id,
                trade_date=trade_date,
            )

    finally:
        with suppress(Exception):
            _ = tushare_api_client
        dispose_engine()


if __name__ == "__main__":
    main()