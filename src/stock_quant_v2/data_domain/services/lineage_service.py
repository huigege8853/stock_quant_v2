from __future__ import annotations

from datetime import datetime

from stock_quant_v2.data_domain.constants import (
    TRANSFORM_MERGE_DAILY_BAR_CORE_V1,
    TRANSFORM_NORMALIZE_DAILY_BAR_V1,
    TRANSFORM_VERSION_M2_V1,
)


class LineageService:
    def build_raw_to_staging(
        self,
        sync_run_id: int,
        batch_id: int | None,
        raw_id: int,
        stg_id: int,
    ) -> dict:
        return {
            "data_sync_run_id": sync_run_id,
            "batch_id": batch_id,
            "theme_code": "DailyBar",
            "dataset_code": "daily_bar",
            "source_layer": "RAW",
            "source_table": "raw_daily_bar",
            "source_record_ref": str(raw_id),
            "target_layer": "STAGING",
            "target_table": "stg_daily_bar",
            "target_record_ref": str(stg_id),
            "transform_code": TRANSFORM_NORMALIZE_DAILY_BAR_V1,
            "transform_version": TRANSFORM_VERSION_M2_V1,
            "lineage_meta": None,
            "created_at": datetime.utcnow(),
        }

    def build_staging_to_core(
        self,
        sync_run_id: int,
        batch_id: int | None,
        stg_id: int,
        instrument_id: int,
        trade_date: str,
        price_adjust_type: str,
    ) -> dict:
        return {
            "data_sync_run_id": sync_run_id,
            "batch_id": batch_id,
            "theme_code": "DailyBar",
            "dataset_code": "daily_bar",
            "source_layer": "STAGING",
            "source_table": "stg_daily_bar",
            "source_record_ref": str(stg_id),
            "target_layer": "CORE",
            "target_table": "daily_bar",
            "target_record_ref": f"{instrument_id}:{trade_date}:{price_adjust_type}",
            "transform_code": TRANSFORM_MERGE_DAILY_BAR_CORE_V1,
            "transform_version": TRANSFORM_VERSION_M2_V1,
            "lineage_meta": None,
            "created_at": datetime.utcnow(),
        }

    def build_market_index_raw_to_staging(
            self,
            sync_run_id: int,
            batch_id: int | None,
            raw_id: int,
            stg_id: int,
    ) -> dict:
        return {
            "data_sync_run_id": sync_run_id,
            "batch_id": batch_id,
            "theme_code": "MarketIndex",
            "dataset_code": "market_index_bar",
            "source_layer": "RAW",
            "source_table": "raw_market_index",
            "source_record_ref": str(raw_id),
            "target_layer": "STAGING",
            "target_table": "stg_market_index",
            "target_record_ref": str(stg_id),
            "transform_code": "TRANSFORM_NORMALIZE_MARKET_INDEX_BAR_V1",
            "transform_version": "TRANSFORM_VERSION_M2_V1",
            "lineage_meta": None,
            "created_at": datetime.utcnow(),
        }

    def build_market_index_staging_to_core(
            self,
            sync_run_id: int,
            batch_id: int | None,
            stg_id: int,
            market_index_id: int,
            trade_date: str,
    ) -> dict:
        return {
            "data_sync_run_id": sync_run_id,
            "batch_id": batch_id,
            "theme_code": "MarketIndex",
            "dataset_code": "market_index_bar",
            "source_layer": "STAGING",
            "source_table": "stg_market_index",
            "source_record_ref": str(stg_id),
            "target_layer": "CORE",
            "target_table": "market_index_bar",
            "target_record_ref": f"{market_index_id}:{trade_date}",
            "transform_code": "TRANSFORM_MERGE_MARKET_INDEX_BAR_CORE_V1",
            "transform_version": "TRANSFORM_VERSION_M2_V1",
            "lineage_meta": None,
            "created_at": datetime.utcnow(),
        }