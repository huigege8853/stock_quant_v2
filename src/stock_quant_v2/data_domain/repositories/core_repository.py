from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from stock_quant_v2.data_domain.repositories._batching import iter_chunks
from stock_quant_v2.db.models.core.adjust_factor import CoreAdjustFactor
from stock_quant_v2.db.models.core.daily_bar import CoreDailyBar
from stock_quant_v2.db.models.core.fundamental_snapshot import FundamentalSnapshot
from stock_quant_v2.db.models.core.instrument_status_daily import CoreInstrumentStatusDaily
from stock_quant_v2.db.models.core.market_breadth import CoreMarketBreadth
from stock_quant_v2.db.models.core.market_index_bar import MarketIndexBar
from stock_quant_v2.db.models.core.price_limit_daily import CorePriceLimitDaily


class CoreRepository:
    def upsert_daily_bar(self, session: Session, payload: dict) -> None:
        stmt = insert(CoreDailyBar).values(**payload)

        update_columns = {
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "pre_close": stmt.excluded.pre_close,
            "pct_change": stmt.excluded.pct_change,
            "price_change": stmt.excluded.price_change,
            "volume": stmt.excluded.volume,
            "amount": stmt.excluded.amount,
            "data_version_id": stmt.excluded.data_version_id,
            "updated_at": stmt.excluded.updated_at,
        }

        stmt = stmt.on_conflict_do_update(
            index_elements=["instrument_id", "trade_date", "price_adjust_type"],
            set_=update_columns,
        )

        session.execute(stmt)

    def bulk_upsert_daily_bar(
        self,
        session: Session,
        payloads: Sequence[dict],
        chunk_size: int = 500,
    ) -> int:
        if not payloads:
            return 0

        total = 0
        for chunk in iter_chunks(list(payloads), chunk_size):
            stmt = insert(CoreDailyBar).values(chunk)

            update_columns = {
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "pre_close": stmt.excluded.pre_close,
                "volume": stmt.excluded.volume,
                "amount": stmt.excluded.amount,
                "data_version_id": stmt.excluded.data_version_id,
                "updated_at": stmt.excluded.updated_at,
            }

            stmt = stmt.on_conflict_do_update(
                index_elements=["instrument_id", "trade_date", "price_adjust_type"],
                set_=update_columns,
            )

            session.execute(stmt)
            total += len(chunk)

        return total

    def upsert_market_index_bar(self, session: Session, payload: dict) -> None:
        stmt = insert(MarketIndexBar).values(**payload)
        update_columns = {
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "volume": stmt.excluded.volume,
            "turnover": stmt.excluded.turnover,
            "source_provider": stmt.excluded.source_provider,
            "data_version_id": stmt.excluded.data_version_id,
        }
        stmt = stmt.on_conflict_do_update(
            constraint="uq_market_index_bar_idx_date",
            set_=update_columns,
        )
        session.execute(stmt)

    def bulk_upsert_market_index_bar(
        self,
        session: Session,
        payloads: Sequence[dict],
        chunk_size: int = 500,
    ) -> int:
        if not payloads:
            return 0

        total = 0
        for chunk in iter_chunks(list(payloads), chunk_size):
            stmt = insert(MarketIndexBar).values(chunk)

            update_columns = {
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
                "turnover": stmt.excluded.turnover,
                "source_provider": stmt.excluded.source_provider,
                "data_version_id": stmt.excluded.data_version_id,
            }
            stmt = stmt.on_conflict_do_update(
                constraint="uq_market_index_bar_idx_date",
                set_=update_columns,
            )
            session.execute(stmt)
            total += len(chunk)

        return total

    def upsert_market_breadth(self, session: Session, payload: dict) -> None:
        stmt = insert(CoreMarketBreadth).values(**payload)

        update_columns = {
            "universe_count": stmt.excluded.universe_count,
            "bar_count": stmt.excluded.bar_count,
            "advancers": stmt.excluded.advancers,
            "decliners": stmt.excluded.decliners,
            "unchanged": stmt.excluded.unchanged,
            "suspended_count": stmt.excluded.suspended_count,
            "total_turnover_amount_cny": stmt.excluded.total_turnover_amount_cny,
            "mean_return": stmt.excluded.mean_return,
            "median_return": stmt.excluded.median_return,
            "data_version_id": stmt.excluded.data_version_id,
            "updated_at": stmt.excluded.updated_at,
        }

        stmt = stmt.on_conflict_do_update(
            index_elements=["market_scope", "trade_date"],
            set_=update_columns,
        )

        session.execute(stmt)

    def upsert_adjust_factor(self, session: Session, payload: dict) -> None:
        stmt = insert(CoreAdjustFactor).values(**payload)

        update_columns = {
            "forward_factor": stmt.excluded.forward_factor,
            "backward_factor": stmt.excluded.backward_factor,
            "data_version_id": stmt.excluded.data_version_id,
            "updated_at": stmt.excluded.updated_at,
        }

        stmt = stmt.on_conflict_do_update(
            index_elements=["instrument_id", "trade_date"],
            set_=update_columns,
        )

        session.execute(stmt)

    def bulk_upsert_adjust_factor(
        self,
        session: Session,
        payloads: Sequence[dict],
        chunk_size: int = 500,
    ) -> int:
        if not payloads:
            return 0

        total = 0
        for chunk in iter_chunks(list(payloads), chunk_size):
            stmt = insert(CoreAdjustFactor).values(chunk)

            update_columns = {
                "forward_factor": stmt.excluded.forward_factor,
                "backward_factor": stmt.excluded.backward_factor,
                "data_version_id": stmt.excluded.data_version_id,
                "updated_at": stmt.excluded.updated_at,
            }

            stmt = stmt.on_conflict_do_update(
                index_elements=["instrument_id", "trade_date"],
                set_=update_columns,
            )

            session.execute(stmt)
            total += len(chunk)

        return total

    def upsert_fundamental_snapshot(self, session: Session, payload: dict) -> None:
        stmt = insert(FundamentalSnapshot).values(**payload)

        update_columns = {
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
            "source_provider": stmt.excluded.source_provider,
            "data_version_id": stmt.excluded.data_version_id,
        }

        stmt = stmt.on_conflict_do_update(
            constraint="uq_fundamental_snapshot_inst_date_type",
            set_=update_columns,
        )

        session.execute(stmt)

    def bulk_upsert_fundamental_snapshot(
        self,
        session: Session,
        payloads: Sequence[dict],
        chunk_size: int = 300,
    ) -> int:
        if not payloads:
            return 0

        total = 0
        for chunk in iter_chunks(list(payloads), chunk_size):
            stmt = insert(FundamentalSnapshot).values(chunk)

            update_columns = {
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
                "source_provider": stmt.excluded.source_provider,
                "data_version_id": stmt.excluded.data_version_id,
            }

            stmt = stmt.on_conflict_do_update(
                constraint="uq_fundamental_snapshot_inst_date_type",
                set_=update_columns,
            )

            session.execute(stmt)
            total += len(chunk)

        return total

    def upsert_price_limit_daily(self, session: Session, payload: dict) -> None:
        stmt = insert(CorePriceLimitDaily).values(**payload)

        update_columns = {
            "up_limit": stmt.excluded.up_limit,
            "down_limit": stmt.excluded.down_limit,
            "data_version_id": stmt.excluded.data_version_id,
            "updated_at": stmt.excluded.updated_at,
        }

        stmt = stmt.on_conflict_do_update(
            constraint="uq_core_price_limit_daily__instrument_id_trade_date",
            set_=update_columns,
        )

        session.execute(stmt)

    def upsert_instrument_status_daily(self, session: Session, payload: dict) -> None:
        stmt = insert(CoreInstrumentStatusDaily).values(**payload)

        update_columns = {
            "trading_status": stmt.excluded.trading_status,
            "is_st": stmt.excluded.is_st,
            "is_suspended": stmt.excluded.is_suspended,
            "data_version_id": stmt.excluded.data_version_id,
            "updated_at": stmt.excluded.updated_at,
        }

        stmt = stmt.on_conflict_do_update(
            constraint="uq_core_instrument_status_daily__instrument_id_trade_date",
            set_=update_columns,
        )

        session.execute(stmt)