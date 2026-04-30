from __future__ import annotations

from datetime import date, datetime

from stock_quant_v2.config.settings import settings
from stock_quant_v2.data_domain.repositories.run_repository import RunRepository
from stock_quant_v2.data_domain.tasks.sync_instrument import run_sync_instrument
from stock_quant_v2.data_domain.tasks.sync_trading_calendar import run_sync_trading_calendar
from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.scripts.bootstrap_meta_data_domain import main as bootstrap_meta_data_domain


def _json_safe(value):
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _build_baostock_api_client():
    from stock_quant_v2.data_domain.providers.baostock.builder import build_baostock_api_client

    return build_baostock_api_client()


def _build_tushare_api_client():
    if not settings.tushare_enabled:
        return None

    from stock_quant_v2.data_domain.providers.tushare.builder import build_tushare_api_client

    return build_tushare_api_client()


def _build_akshare_api_client():
    try:
        import akshare as ak
    except ImportError:
        return None
    return ak


def main() -> None:
    bootstrap_meta_data_domain()

    session = SessionLocal()
    run_repo = RunRepository()
    root_run = None
    baostock_api_client = None

    try:
        baostock_api_client = _build_baostock_api_client()

        tushare_api_client = _build_tushare_api_client()

        akshare_api_client = _build_akshare_api_client()

        context_json = _json_safe(
            {
                "start_date": settings.bootstrap_calendar_start_date,
                "end_date": settings.bootstrap_calendar_end_date,
                "providers": ["akshare", "tushare", "baostock"],
                "tushare_enabled": bool(settings.tushare_enabled),
                "script_name": "bootstrap_instrument_calendar",
            }
        )

        root_run = run_repo.create_run(
            session=session,
            run_type="DATA_BOOTSTRAP",
            run_name="bootstrap_instrument_calendar",
            trigger_type="MANUAL",
            context_json=context_json,
        )
        session.commit()

        run_repo.mark_run_running(session, root_run)
        session.commit()

        run_sync_instrument(
            session=session,
            baostock_api_client=baostock_api_client,
            tushare_api_client=tushare_api_client,
            akshare_api_client=akshare_api_client,
            run_id=root_run.id,
        )
        session.commit()

        run_sync_trading_calendar(
            session=session,
            baostock_api_client=baostock_api_client,
            tushare_api_client=tushare_api_client,
            akshare_api_client=akshare_api_client,
            run_id=root_run.id,
            start_date=settings.bootstrap_calendar_start_date,
            end_date=settings.bootstrap_calendar_end_date,
            exchanges=("SSE", "SZSE", "BSE"),
        )
        session.commit()

        run_repo.mark_run_finished(session, root_run, status="SUCCESS")
        session.commit()

    except Exception as exc:  # noqa: BLE001
        session.rollback()
        try:
            if root_run is not None:
                run_repo.mark_run_finished(
                    session,
                    root_run,
                    status="FAILED",
                    error_message=str(exc),
                )
                session.commit()
        except Exception:
            session.rollback()
        raise

    finally:
        try:
            if baostock_api_client is not None:
                logout_fn = getattr(baostock_api_client, "logout", None)
                if callable(logout_fn):
                    logout_fn()
        except Exception:
            pass

        session.close()


if __name__ == "__main__":
    main()