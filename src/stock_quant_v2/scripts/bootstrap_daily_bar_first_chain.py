from __future__ import annotations

from contextlib import suppress
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from stock_quant_v2.config.settings import settings
from stock_quant_v2.data_domain.tasks.sync_adjust_factor import run_sync_adjust_factor
from stock_quant_v2.data_domain.tasks.sync_daily_bar import run_sync_daily_bar
from stock_quant_v2.data_domain.tasks.sync_instrument import run_sync_instrument
from stock_quant_v2.data_domain.tasks.sync_market_breadth import run_sync_market_breadth
from stock_quant_v2.data_domain.tasks.sync_trading_calendar import run_sync_trading_calendar
from stock_quant_v2.db.session import SessionLocal, dispose_engine
from stock_quant_v2.scripts.bootstrap_meta_data_domain import main as bootstrap_meta_data_domain


def _date_iter(start_date: date, end_date: date):
    current = start_date
    while current <= end_date:
        yield current
        current = date.fromordinal(current.toordinal() + 1)


def _build_akshare_api_client():
    try:
        import akshare as ak
    except ImportError as exc:
        raise ImportError("akshare is not installed. Please add it to pyproject.toml") from exc
    return ak


def _build_sina_api_client():
    # 当前项目树里没有 providers/sina/builder.py，所以这里先返回一个占位 client。
    # sync_daily_bar / sync_adjust_factor 里已经能处理 None 或 provider 空实现。
    return None


def _safe_logout_baostock(baostock_api_client) -> None:
    if baostock_api_client is None:
        return
    with suppress(Exception):
        logout = getattr(baostock_api_client, "logout", None)
        if callable(logout):
            logout()


def _resolve_data_version_id(session: Session) -> int:
    row = session.execute(
        text(
            """
            select id
            from meta_data_version
            where dataset_id = :dataset_id
            order by id desc
            limit 1
            """
        ),
        {"dataset_id": 1},
    ).scalar_one_or_none()

    if row is None:
        raise RuntimeError(
            "No row found in meta_data_version for dataset_id=1. "
            "Please bootstrap metadata/version rows first."
        )

    return int(row)


def main() -> None:
    # 1) metadata bootstrap
    bootstrap_meta_data_domain()

    # 2) provider clients
    from stock_quant_v2.data_domain.providers.baostock.builder import build_baostock_api_client
    from stock_quant_v2.data_domain.providers.tushare.builder import build_tushare_api_client

    baostock_api_client = None
    tushare_api_client = None
    akshare_api_client = None
    sina_api_client = None

    try:
        baostock_api_client = build_baostock_api_client()
        tushare_api_client = build_tushare_api_client()
        akshare_api_client = _build_akshare_api_client()
        sina_api_client = _build_sina_api_client()

        # phase-1 temporary run id
        root_run_id = 1

        with SessionLocal() as session:
            session: Session

            data_version_id = _resolve_data_version_id(session)

            # 3) instrument
            run_sync_instrument(
                session=session,
                baostock_api_client=baostock_api_client,
                tushare_api_client=tushare_api_client,
                akshare_api_client=akshare_api_client,
                run_id=root_run_id,
            )

            # 4) trading calendar
            run_sync_trading_calendar(
                session=session,
                baostock_api_client=baostock_api_client,
                tushare_api_client=tushare_api_client,
                akshare_api_client=akshare_api_client,
                run_id=root_run_id,
                start_date=settings.bootstrap_calendar_start_date,
                end_date=settings.bootstrap_calendar_end_date,
                exchanges=("SSE", "SZSE", "BSE"),
            )

            # 5) daily bar
            run_sync_daily_bar(
                session=session,
                baostock_api_client=baostock_api_client,
                tushare_api_client=tushare_api_client,
                sina_api_client=sina_api_client,
                akshare_api_client=akshare_api_client,
                run_id=root_run_id,
                data_version_id=data_version_id,
                start_date=settings.bootstrap_daily_bar_start_date,
                end_date=settings.bootstrap_daily_bar_end_date,
                _provider_name="fallback",
            )

            # 6) adjust factor
            for trade_date in _date_iter(
                settings.bootstrap_daily_bar_start_date,
                settings.bootstrap_daily_bar_end_date,
            ):
                run_sync_adjust_factor(
                    session=session,
                    baostock_api_client=baostock_api_client,
                    sina_api_client=sina_api_client,
                    akshare_api_client=akshare_api_client,
                    pytdx_api_client=None,
                    tushare_api_client=tushare_api_client,
                    paid_api_client=None,
                    run_id=root_run_id,
                    data_version_id=data_version_id,
                    trade_date=trade_date,
                )

            # 7) market breadth
            for trade_date in _date_iter(
                settings.bootstrap_daily_bar_start_date,
                settings.bootstrap_daily_bar_end_date,
            ):
                run_sync_market_breadth(
                    session=session,
                    run_id=root_run_id,
                    trade_date=trade_date,
                    market_scope="CN_ALL",
                    exchange_codes=("SSE", "SZSE", "BSE"),
                    data_version_id=data_version_id,
                )

    finally:
        _safe_logout_baostock(baostock_api_client)
        dispose_engine()


if __name__ == "__main__":
    main()