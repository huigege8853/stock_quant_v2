from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from stock_quant_v2.data_domain.repositories._batching import iter_chunks
from stock_quant_v2.db.models.staging.adjust_factor_staging import AdjustFactorStaging
from stock_quant_v2.db.models.staging.daily_bar_staging import DailyBarStaging
from stock_quant_v2.db.models.staging.fundamental_snapshot_staging import FundamentalSnapshotStaging
from stock_quant_v2.db.models.staging.market_index_staging import MarketIndexStaging


class StagingRepository:
    def upsert_stg_daily_bar(self, session: Session, payload: dict) -> DailyBarStaging:
        stmt = insert(DailyBarStaging).values(**payload)

        update_columns = {
            "sync_run_id": stmt.excluded.sync_run_id,
            "batch_id": stmt.excluded.batch_id,
            "dataset_code": stmt.excluded.dataset_code,
            "market_code": stmt.excluded.market_code,
            "exchange_code": stmt.excluded.exchange_code,
            "vendor_symbol": stmt.excluded.vendor_symbol,
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "pre_close": stmt.excluded.pre_close,
            "volume": stmt.excluded.volume,
            "turnover": stmt.excluded.turnover,
            "amplitude": stmt.excluded.amplitude,
            "pct_change": stmt.excluded.pct_change,
            "price_change": stmt.excluded.price_change,
            "turnover_rate": stmt.excluded.turnover_rate,
            "suspended_flag": stmt.excluded.suspended_flag,
            "provider_record_key": stmt.excluded.provider_record_key,
            "raw_record_id": stmt.excluded.raw_record_id,
        }

        stmt = stmt.on_conflict_do_update(
            constraint="uq_stg_daily_bar_provider_ticker_date_adj",
            set_=update_columns,
        ).returning(DailyBarStaging)

        return session.execute(stmt).scalar_one()

    def bulk_upsert_stg_daily_bar(
        self,
        session: Session,
        payloads: Sequence[dict],
        chunk_size: int = 200,
    ) -> int:
        if not payloads:
            return 0

        total = 0
        for chunk in iter_chunks(list(payloads), chunk_size):
            stmt = insert(DailyBarStaging).values(chunk)

            update_columns = {
                "sync_run_id": stmt.excluded.sync_run_id,
                "batch_id": stmt.excluded.batch_id,
                "dataset_code": stmt.excluded.dataset_code,
                "market_code": stmt.excluded.market_code,
                "exchange_code": stmt.excluded.exchange_code,
                "vendor_symbol": stmt.excluded.vendor_symbol,
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "pre_close": stmt.excluded.pre_close,
                "volume": stmt.excluded.volume,
                "turnover": stmt.excluded.turnover,
                "amplitude": stmt.excluded.amplitude,
                "pct_change": stmt.excluded.pct_change,
                "price_change": stmt.excluded.price_change,
                "turnover_rate": stmt.excluded.turnover_rate,
                "suspended_flag": stmt.excluded.suspended_flag,
                "provider_record_key": stmt.excluded.provider_record_key,
                "raw_record_id": stmt.excluded.raw_record_id,
            }

            stmt = stmt.on_conflict_do_update(
                constraint="uq_stg_daily_bar_provider_ticker_date_adj",
                set_=update_columns,
            )

            session.execute(stmt)
            total += len(chunk)

        return total

    def upsert_stg_market_index(self, session: Session, payload: dict) -> MarketIndexStaging:
        stmt = insert(MarketIndexStaging).values(**payload)

        update_columns = {
            "sync_run_id": stmt.excluded.sync_run_id,
            "batch_id": stmt.excluded.batch_id,
            "dataset_code": stmt.excluded.dataset_code,
            "exchange_code": stmt.excluded.exchange_code,
            "index_name": stmt.excluded.index_name,
            "index_type": stmt.excluded.index_type,
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "volume": stmt.excluded.volume,
            "turnover": stmt.excluded.turnover,
            "provider_record_key": stmt.excluded.provider_record_key,
            "raw_record_id": stmt.excluded.raw_record_id,
        }

        stmt = stmt.on_conflict_do_update(
            constraint="uq_stg_market_index_provider_code_date",
            set_=update_columns,
        ).returning(MarketIndexStaging)

        return session.execute(stmt).scalar_one()

    def bulk_upsert_stg_market_index(
        self,
        session: Session,
        payloads: Sequence[dict],
        chunk_size: int = 500,
    ) -> int:
        if not payloads:
            return 0

        total = 0
        for chunk in iter_chunks(list(payloads), chunk_size):
            stmt = insert(MarketIndexStaging).values(chunk)

            update_columns = {
                "sync_run_id": stmt.excluded.sync_run_id,
                "batch_id": stmt.excluded.batch_id,
                "dataset_code": stmt.excluded.dataset_code,
                "exchange_code": stmt.excluded.exchange_code,
                "index_name": stmt.excluded.index_name,
                "index_type": stmt.excluded.index_type,
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
                "turnover": stmt.excluded.turnover,
                "provider_record_key": stmt.excluded.provider_record_key,
                "raw_record_id": stmt.excluded.raw_record_id,
            }

            stmt = stmt.on_conflict_do_update(
                constraint="uq_stg_market_index_provider_code_date",
                set_=update_columns,
            )

            session.execute(stmt)
            total += len(chunk)

        return total

    def upsert_stg_adjust_factor(self, session: Session, payload: dict) -> AdjustFactorStaging:
        stmt = insert(AdjustFactorStaging).values(**payload)

        update_columns = {
            "sync_run_id": stmt.excluded.sync_run_id,
            "batch_id": stmt.excluded.batch_id,
            "dataset_code": stmt.excluded.dataset_code,
            "market_code": stmt.excluded.market_code,
            "exchange_code": stmt.excluded.exchange_code,
            "vendor_symbol": stmt.excluded.vendor_symbol,
            "adjust_factor": stmt.excluded.adjust_factor,
            "provider_record_key": stmt.excluded.provider_record_key,
            "raw_record_id": stmt.excluded.raw_record_id,
        }

        stmt = stmt.on_conflict_do_update(
            constraint="uq_stg_adjfac_key",
            set_=update_columns,
        ).returning(AdjustFactorStaging)

        return session.execute(stmt).scalar_one()

    def bulk_upsert_stg_adjust_factor(
        self,
        session: Session,
        payloads: Sequence[dict],
        chunk_size: int = 500,
    ) -> int:
        if not payloads:
            return 0

        total = 0
        for chunk in iter_chunks(list(payloads), chunk_size):
            stmt = insert(AdjustFactorStaging).values(chunk)

            update_columns = {
                "sync_run_id": stmt.excluded.sync_run_id,
                "batch_id": stmt.excluded.batch_id,
                "dataset_code": stmt.excluded.dataset_code,
                "market_code": stmt.excluded.market_code,
                "exchange_code": stmt.excluded.exchange_code,
                "vendor_symbol": stmt.excluded.vendor_symbol,
                "adjust_factor": stmt.excluded.adjust_factor,
                "provider_record_key": stmt.excluded.provider_record_key,
                "raw_record_id": stmt.excluded.raw_record_id,
            }

            stmt = stmt.on_conflict_do_update(
                constraint="uq_stg_adjfac_key",
                set_=update_columns,
            )

            session.execute(stmt)
            total += len(chunk)

        return total

    def upsert_stg_fundamental_snapshot(
        self,
        session: Session,
        payload: dict,
    ) -> FundamentalSnapshotStaging:
        stmt = insert(FundamentalSnapshotStaging).values(**payload)

        update_columns = {
            "sync_run_id": stmt.excluded.sync_run_id,
            "batch_id": stmt.excluded.batch_id,
            "dataset_code": stmt.excluded.dataset_code,
            "market_code": stmt.excluded.market_code,
            "exchange_code": stmt.excluded.exchange_code,
            "vendor_symbol": stmt.excluded.vendor_symbol,
            "snapshot_type": stmt.excluded.snapshot_type,
            "pe_ttm": stmt.excluded.pe_ttm,
            "pb": stmt.excluded.pb,
            "ps_ttm": stmt.excluded.ps_ttm,
            "dv_ttm": stmt.excluded.dv_ttm,
            "total_mv": stmt.excluded.total_mv,
            "circ_mv": stmt.excluded.circ_mv,
            "roe": stmt.excluded.roe,
            "roa": stmt.excluded.roa,
            "gross_margin": stmt.excluded.gross_margin,
            "net_profit_yoy": stmt.excluded.net_profit_yoy,
            "report_period": stmt.excluded.report_period,
            "announcement_date": stmt.excluded.announcement_date,
            "provider_record_key": stmt.excluded.provider_record_key,
            "raw_record_id": stmt.excluded.raw_record_id,
        }

        stmt = stmt.on_conflict_do_update(
            constraint="uq_stg_fundamental_snapshot_key",
            set_=update_columns,
        ).returning(FundamentalSnapshotStaging)

        return session.execute(stmt).scalar_one()

    def bulk_upsert_stg_fundamental_snapshot(
        self,
        session: Session,
        payloads: Sequence[dict],
        chunk_size: int = 300,
    ) -> int:
        if not payloads:
            return 0

        total = 0
        for chunk in iter_chunks(list(payloads), chunk_size):
            stmt = insert(FundamentalSnapshotStaging).values(chunk)

            update_columns = {
                "sync_run_id": stmt.excluded.sync_run_id,
                "batch_id": stmt.excluded.batch_id,
                "dataset_code": stmt.excluded.dataset_code,
                "market_code": stmt.excluded.market_code,
                "exchange_code": stmt.excluded.exchange_code,
                "vendor_symbol": stmt.excluded.vendor_symbol,
                "snapshot_type": stmt.excluded.snapshot_type,
                "pe_ttm": stmt.excluded.pe_ttm,
                "pb": stmt.excluded.pb,
                "ps_ttm": stmt.excluded.ps_ttm,
                "dv_ttm": stmt.excluded.dv_ttm,
                "total_mv": stmt.excluded.total_mv,
                "circ_mv": stmt.excluded.circ_mv,
                "roe": stmt.excluded.roe,
                "roa": stmt.excluded.roa,
                "gross_margin": stmt.excluded.gross_margin,
                "net_profit_yoy": stmt.excluded.net_profit_yoy,
                "report_period": stmt.excluded.report_period,
                "announcement_date": stmt.excluded.announcement_date,
                "provider_record_key": stmt.excluded.provider_record_key,
                "raw_record_id": stmt.excluded.raw_record_id,
            }

            stmt = stmt.on_conflict_do_update(
                constraint="uq_stg_fundamental_snapshot_key",
                set_=update_columns,
            )

            session.execute(stmt)
            total += len(chunk)

        return total