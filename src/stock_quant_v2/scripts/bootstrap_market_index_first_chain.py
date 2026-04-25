from __future__ import annotations

from datetime import date
import os

from sqlalchemy import select

from stock_quant_v2.data_domain.repositories.run_repository import RunRepository
from stock_quant_v2.data_domain.tasks.sync_market_index_bar import run_sync_market_index_bar
from stock_quant_v2.db.models.core.market_index import MarketIndex
from stock_quant_v2.db.session import SessionLocal


def _parse_date(value: str, default: str) -> date:
    return date.fromisoformat(value or default)


def _parse_index_codes(value: str | None) -> list[str]:
    if not value:
        return ["000001.SH", "399001.SZ", "399006.SZ", "000300.SH"]
    return [item.strip() for item in value.split(",") if item.strip()]


def main() -> None:
    start_date = _parse_date(os.getenv("BOOTSTRAP_MARKET_INDEX_START_DATE"), "2024-01-02")
    end_date = _parse_date(os.getenv("BOOTSTRAP_MARKET_INDEX_END_DATE"), "2024-01-05")
    index_codes = _parse_index_codes(os.getenv("BOOTSTRAP_MARKET_INDEX_CODES"))
    provider_name = os.getenv("BOOTSTRAP_MARKET_INDEX_PROVIDER", "sina")

    session = SessionLocal()
    try:
        existing_codes = set(
            session.execute(
                select(MarketIndex.index_code).where(MarketIndex.index_code.in_(index_codes))
            ).scalars().all()
        )
        missing_codes = [code for code in index_codes if code not in existing_codes]
        if missing_codes:
            raise RuntimeError(
                "market_index records missing. Seed them first via "
                "python -m stock_quant_v2.scripts.seed_market_index_core_universe. "
                f"Missing: {missing_codes}"
            )

        run_repo = RunRepository()
        run = run_repo.create_run(
            session=session,
            run_type="DATA_SYNC",
            run_name="bootstrap_market_index_first_chain",
            trigger_type="MANUAL",
            context_json={
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "index_codes": index_codes,
                "provider_name": provider_name,
            },
        )
        session.commit()

        run_repo.mark_run_running(session, run)
        session.commit()

        result = run_sync_market_index_bar(
            session=session,
            sina_api_client=None,
            run_id=run.id,
            start_date=start_date,
            end_date=end_date,
            index_codes=index_codes,
            provider_name=provider_name,
        )

        final_status = "SUCCESS" if result.get("error_rows", 0) == 0 else "PARTIAL"
        run_repo.mark_run_finished(session, run, final_status)
        session.commit()
        print(result)
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        try:
            run
        except NameError:
            raise
        else:
            run = session.get(type(run), run.id)
            if run is not None:
                run_repo.mark_run_finished(session, run, "FAILED", error_message=str(exc))
                session.commit()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
