from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from stock_quant_v2.data_domain.repositories._batching import iter_chunks
from stock_quant_v2.db.models.raw.adjust_factor_raw import AdjustFactorRaw
from stock_quant_v2.db.models.raw.daily_bar_raw import DailyBarRaw
from stock_quant_v2.db.models.raw.fundamental_snapshot_raw import FundamentalSnapshotRaw
from stock_quant_v2.db.models.raw.market_index_raw import MarketIndexRaw


class RawRepository:
    def upsert_raw_daily_bar(self, session: Session, payload: dict) -> DailyBarRaw:
        stmt = insert(DailyBarRaw).values(**payload)

        update_columns = {
            "symbol": stmt.excluded.symbol,
            "trade_date": stmt.excluded.trade_date,
            "batch_id": stmt.excluded.batch_id,
            "sync_run_id": stmt.excluded.sync_run_id,
            "request_params": stmt.excluded.request_params,
            "payload_json": stmt.excluded.payload_json,
            "payload_hash": stmt.excluded.payload_hash,
            "provider_update_ts": stmt.excluded.provider_update_ts,
            "ingested_at": stmt.excluded.ingested_at,
        }

        stmt = stmt.on_conflict_do_update(
            constraint="uq_raw_daily_bar_provider_key",
            set_=update_columns,
        ).returning(DailyBarRaw)

        return session.execute(stmt).scalar_one()

    def bulk_upsert_raw_daily_bar(
        self,
        session: Session,
        payloads: Sequence[dict],
        chunk_size: int = 500,
    ) -> int:
        if not payloads:
            return 0

        total = 0
        for chunk in iter_chunks(list(payloads), chunk_size):
            stmt = insert(DailyBarRaw).values(chunk)

            update_columns = {
                "symbol": stmt.excluded.symbol,
                "trade_date": stmt.excluded.trade_date,
                "batch_id": stmt.excluded.batch_id,
                "sync_run_id": stmt.excluded.sync_run_id,
                "request_params": stmt.excluded.request_params,
                "payload_json": stmt.excluded.payload_json,
                "payload_hash": stmt.excluded.payload_hash,
                "provider_update_ts": stmt.excluded.provider_update_ts,
                "ingested_at": stmt.excluded.ingested_at,
            }

            stmt = stmt.on_conflict_do_update(
                constraint="uq_raw_daily_bar_provider_key",
                set_=update_columns,
            )
            session.execute(stmt)
            total += len(chunk)

        return total

    def upsert_raw_market_index(self, session: Session, payload: dict) -> MarketIndexRaw:
        stmt = insert(MarketIndexRaw).values(**payload)

        update_columns = {
            "symbol": stmt.excluded.symbol,
            "trade_date": stmt.excluded.trade_date,
            "batch_id": stmt.excluded.batch_id,
            "sync_run_id": stmt.excluded.sync_run_id,
            "request_params": stmt.excluded.request_params,
            "payload_json": stmt.excluded.payload_json,
            "payload_hash": stmt.excluded.payload_hash,
            "provider_update_ts": stmt.excluded.provider_update_ts,
            "ingested_at": stmt.excluded.ingested_at,
        }

        stmt = stmt.on_conflict_do_update(
            constraint="uq_raw_market_index_provider_key",
            set_=update_columns,
        ).returning(MarketIndexRaw)

        return session.execute(stmt).scalar_one()

    def bulk_upsert_raw_market_index(
        self,
        session: Session,
        payloads: Sequence[dict],
        chunk_size: int = 500,
    ) -> int:
        if not payloads:
            return 0

        total = 0
        for chunk in iter_chunks(list(payloads), chunk_size):
            stmt = insert(MarketIndexRaw).values(chunk)

            update_columns = {
                "symbol": stmt.excluded.symbol,
                "trade_date": stmt.excluded.trade_date,
                "batch_id": stmt.excluded.batch_id,
                "sync_run_id": stmt.excluded.sync_run_id,
                "request_params": stmt.excluded.request_params,
                "payload_json": stmt.excluded.payload_json,
                "payload_hash": stmt.excluded.payload_hash,
                "provider_update_ts": stmt.excluded.provider_update_ts,
                "ingested_at": stmt.excluded.ingested_at,
            }

            stmt = stmt.on_conflict_do_update(
                constraint="uq_raw_market_index_provider_key",
                set_=update_columns,
            )
            session.execute(stmt)
            total += len(chunk)

        return total

    def upsert_raw_adjust_factor(self, session: Session, payload: dict) -> AdjustFactorRaw:
        stmt = insert(AdjustFactorRaw).values(**payload)

        update_columns = {
            "symbol": stmt.excluded.symbol,
            "trade_date": stmt.excluded.trade_date,
            "batch_id": stmt.excluded.batch_id,
            "sync_run_id": stmt.excluded.sync_run_id,
            "request_params": stmt.excluded.request_params,
            "payload_json": stmt.excluded.payload_json,
            "payload_hash": stmt.excluded.payload_hash,
            "provider_update_ts": stmt.excluded.provider_update_ts,
            "ingested_at": stmt.excluded.ingested_at,
        }

        stmt = stmt.on_conflict_do_update(
            constraint="uq_raw_adjfac_key",
            set_=update_columns,
        ).returning(AdjustFactorRaw)

        return session.execute(stmt).scalar_one()

    def bulk_upsert_raw_adjust_factor(
        self,
        session: Session,
        payloads: Sequence[dict],
        chunk_size: int = 500,
    ) -> int:
        if not payloads:
            return 0

        total = 0
        for chunk in iter_chunks(list(payloads), chunk_size):
            stmt = insert(AdjustFactorRaw).values(chunk)

            update_columns = {
                "symbol": stmt.excluded.symbol,
                "trade_date": stmt.excluded.trade_date,
                "batch_id": stmt.excluded.batch_id,
                "sync_run_id": stmt.excluded.sync_run_id,
                "request_params": stmt.excluded.request_params,
                "payload_json": stmt.excluded.payload_json,
                "payload_hash": stmt.excluded.payload_hash,
                "provider_update_ts": stmt.excluded.provider_update_ts,
                "ingested_at": stmt.excluded.ingested_at,
            }

            stmt = stmt.on_conflict_do_update(
                constraint="uq_raw_adjfac_key",
                set_=update_columns,
            )
            session.execute(stmt)
            total += len(chunk)

        return total

    def upsert_raw_fundamental_snapshot(
        self,
        session: Session,
        payload: dict,
    ) -> FundamentalSnapshotRaw:
        stmt = insert(FundamentalSnapshotRaw).values(**payload)

        update_columns = {
            "symbol": stmt.excluded.symbol,
            "trade_date": stmt.excluded.trade_date,
            "batch_id": stmt.excluded.batch_id,
            "sync_run_id": stmt.excluded.sync_run_id,
            "request_params": stmt.excluded.request_params,
            "payload_json": stmt.excluded.payload_json,
            "payload_hash": stmt.excluded.payload_hash,
            "provider_update_ts": stmt.excluded.provider_update_ts,
            "ingested_at": stmt.excluded.ingested_at,
        }

        stmt = stmt.on_conflict_do_update(
            constraint="uq_raw_fundamental_snapshot_key",
            set_=update_columns,
        ).returning(FundamentalSnapshotRaw)

        return session.execute(stmt).scalar_one()

    def bulk_upsert_raw_fundamental_snapshot(
        self,
        session: Session,
        payloads: Sequence[dict],
        chunk_size: int = 300,
    ) -> int:
        if not payloads:
            return 0

        total = 0
        for chunk in iter_chunks(list(payloads), chunk_size):
            stmt = insert(FundamentalSnapshotRaw).values(chunk)

            update_columns = {
                "symbol": stmt.excluded.symbol,
                "trade_date": stmt.excluded.trade_date,
                "batch_id": stmt.excluded.batch_id,
                "sync_run_id": stmt.excluded.sync_run_id,
                "request_params": stmt.excluded.request_params,
                "payload_json": stmt.excluded.payload_json,
                "payload_hash": stmt.excluded.payload_hash,
                "provider_update_ts": stmt.excluded.provider_update_ts,
                "ingested_at": stmt.excluded.ingested_at,
            }

            stmt = stmt.on_conflict_do_update(
                constraint="uq_raw_fundamental_snapshot_key",
                set_=update_columns,
            )
            session.execute(stmt)
            total += len(chunk)

        return total