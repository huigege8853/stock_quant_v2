from __future__ import annotations

from datetime import date
import os

from sqlalchemy import and_, exists, select

from stock_quant_v2.data_domain.repositories.run_repository import RunRepository
from stock_quant_v2.data_domain.tasks.sync_market_index_bar import run_sync_market_index_bar
from stock_quant_v2.db.models.core.market_index import MarketIndex
from stock_quant_v2.db.models.core.market_index_bar import MarketIndexBar
from stock_quant_v2.db.models.meta.exchange import MetaExchange
from stock_quant_v2.db.models.meta.trading_calendar import MetaTradingCalendar
from stock_quant_v2.db.session import SessionLocal


def _parse_date(value: str | None, default: str) -> date:
    return date.fromisoformat(value or default)


def _parse_index_codes(value: str | None) -> list[str] | None:
    if not value:
        return None
    rows = [x.strip() for x in value.split(",") if x.strip()]
    return rows or None


def discover_missing_pairs(
    session,
    start_date: date,
    end_date: date,
    index_codes: list[str] | None = None,
) -> list[tuple[str, date]]:
    exchange_id = session.execute(
        select(MetaExchange.id).where(MetaExchange.exchange_code == "SSE")
    ).scalar_one_or_none()
    if exchange_id is None:
        return []

    date_stmt = (
        select(MetaTradingCalendar.trade_date)
        .where(
            MetaTradingCalendar.exchange_id == exchange_id,
            MetaTradingCalendar.trade_date >= start_date,
            MetaTradingCalendar.trade_date <= end_date,
            MetaTradingCalendar.is_open.is_(True),
        )
        .order_by(MetaTradingCalendar.trade_date)
    )
    trade_dates = list(session.execute(date_stmt).scalars().all())

    idx_stmt = select(MarketIndex).where(MarketIndex.is_active.is_(True)).order_by(MarketIndex.index_code)
    if index_codes:
        idx_stmt = idx_stmt.where(MarketIndex.index_code.in_(index_codes))
    indexes = list(session.execute(idx_stmt).scalars().all())

    missing: list[tuple[str, date]] = []
    for idx in indexes:
        for trade_date in trade_dates:
            exists_stmt = select(
                exists().where(
                    and_(
                        MarketIndexBar.market_index_id == idx.id,
                        MarketIndexBar.trade_date == trade_date,
                    )
                )
            )
            present = session.execute(exists_stmt).scalar_one()
            if not present:
                missing.append((idx.index_code, trade_date))

    return missing


def main() -> None:
    start_date = _parse_date(os.getenv("REPAIR_MARKET_INDEX_START_DATE"), "2024-01-02")
    end_date = _parse_date(os.getenv("REPAIR_MARKET_INDEX_END_DATE"), "2024-01-05")
    index_codes = _parse_index_codes(os.getenv("REPAIR_MARKET_INDEX_CODES"))

    session = SessionLocal()
    try:
        missing_pairs = discover_missing_pairs(
            session=session,
            start_date=start_date,
            end_date=end_date,
            index_codes=index_codes,
        )

        if not missing_pairs:
            print(
                {
                    "message": "no missing pairs",
                    "start_date": str(start_date),
                    "end_date": str(end_date),
                }
            )
            return

        grouped: dict[date, list[str]] = {}
        for index_code, trade_date in missing_pairs:
            grouped.setdefault(trade_date, []).append(index_code)

        run_repo = RunRepository()
        run = run_repo.create_run(
            session=session,
            run_type="DATA_REPAIR",
            run_name="repair_missing_market_index_bar",
            trigger_type="MANUAL",
            context_json={
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "missing_pairs": len(missing_pairs),
            },
        )
        session.commit()

        run_repo.mark_run_running(session, run)
        session.commit()

        total = {
            "input_rows": 0,
            "raw_rows": 0,
            "staging_rows": 0,
            "core_upsert_rows": 0,
            "error_rows": 0,
            "skipped_batches": 0,
            "data_version_id": None,
        }

        for trade_date, codes in grouped.items():
            result = run_sync_market_index_bar(
                session=session,
                sina_api_client=None,
                run_id=run.id,
                start_date=trade_date,
                end_date=trade_date,
                index_codes=sorted(set(codes)),
                provider_name="fallback",
            )

            for key in ("input_rows", "raw_rows", "staging_rows", "core_upsert_rows", "error_rows", "skipped_batches"):
                total[key] += int(result.get(key, 0) or 0)

            total["data_version_id"] = result.get("data_version_id") or total["data_version_id"]

        final_status = "SUCCESS" if total["error_rows"] == 0 else "PARTIAL"
        run_repo.mark_run_finished(session, run, final_status)
        session.commit()

        total["missing_pairs"] = len(missing_pairs)
        print(total)

    except Exception as exc:  # noqa: BLE001
        session.rollback()
        run = locals().get("run")
        if run is not None:
            run = session.get(type(run), run.id)
            if run is not None:
                run_repo.mark_run_finished(session, run, "FAILED", error_message=str(exc))
                session.commit()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    def main() -> None:
        start_date = _parse_date(os.getenv("REPAIR_MARKET_INDEX_START_DATE"), "2024-01-02")
        end_date = _parse_date(os.getenv("REPAIR_MARKET_INDEX_END_DATE"), "2024-01-05")
        index_codes = _parse_index_codes(os.getenv("REPAIR_MARKET_INDEX_CODES"))
        provider_priority = os.getenv(
            "MARKET_INDEX_BAR_PROVIDER_PRIORITY",
            "baostock,sina,akshare,pytdx,tushare,paid,skip",
        )

        session = SessionLocal()
        try:
            missing_pairs = discover_missing_pairs(
                session=session,
                start_date=start_date,
                end_date=end_date,
                index_codes=index_codes,
            )

            if not missing_pairs:
                print(
                    {
                        "message": "no missing pairs",
                        "start_date": str(start_date),
                        "end_date": str(end_date),
                    }
                )
                return

            grouped: dict[date, list[str]] = {}
            for index_code, trade_date in missing_pairs:
                grouped.setdefault(trade_date, []).append(index_code)

            run_repo = RunRepository()
            run = run_repo.create_run(
                session=session,
                run_type="DATA_REPAIR",
                run_name="repair_missing_market_index_bar",
                trigger_type="MANUAL",
                context_json={
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "missing_pairs": len(missing_pairs),
                    "provider_priority": provider_priority,
                },
            )
            session.commit()

            run_repo.mark_run_running(session, run)
            session.commit()

            total = {
                "input_rows": 0,
                "raw_rows": 0,
                "staging_rows": 0,
                "core_upsert_rows": 0,
                "error_rows": 0,
                "skipped_batches": 0,
                "data_version_id": None,
            }

            for trade_date, codes in grouped.items():
                result = run_sync_market_index_bar(
                    session=session,
                    sina_api_client=None,
                    run_id=run.id,
                    start_date=trade_date,
                    end_date=trade_date,
                    index_codes=sorted(set(codes)),
                    provider_name="fallback",
                )

                for key in (
                        "input_rows",
                        "raw_rows",
                        "staging_rows",
                        "core_upsert_rows",
                        "error_rows",
                        "skipped_batches",
                ):
                    total[key] += int(result.get(key, 0) or 0)

                total["data_version_id"] = result.get("data_version_id") or total["data_version_id"]

            final_status = "SUCCESS" if total["error_rows"] == 0 else "PARTIAL"
            run_repo.mark_run_finished(session, run, final_status)
            session.commit()

            total["missing_pairs"] = len(missing_pairs)
            print(total)

        except Exception as exc:  # noqa: BLE001
            session.rollback()
            run = locals().get("run")
            if run is not None:
                run = session.get(type(run), run.id)
                if run is not None:
                    run_repo.mark_run_finished(session, run, "FAILED", error_message=str(exc))
                    session.commit()
            raise
        finally:
            session.close()


if __name__ == "__main__":
    main()
