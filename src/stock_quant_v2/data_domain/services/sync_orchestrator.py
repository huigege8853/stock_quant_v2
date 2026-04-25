from __future__ import annotations

from datetime import datetime
from typing import Callable

from sqlalchemy.orm import Session

from stock_quant_v2.data_domain.dto.daily_bar import DailyBarDTO
from stock_quant_v2.data_domain.enums import SyncStatus
from stock_quant_v2.data_domain.mappers.daily_bar_mapper import (
    dto_to_raw_daily_bar_dict,
    dto_to_staging_daily_bar_dict,
    staging_to_core_daily_bar_dict,
)
from stock_quant_v2.data_domain.repositories.core_repository import CoreRepository
from stock_quant_v2.data_domain.repositories.instrument_lookup_repository import InstrumentLookupRepository
from stock_quant_v2.data_domain.repositories.raw_repository import RawRepository
from stock_quant_v2.data_domain.repositories.staging_repository import StagingRepository
from stock_quant_v2.data_domain.repositories.sync_run_repository import SyncRunRepository
from stock_quant_v2.data_domain.services.lineage_service import LineageService
from stock_quant_v2.data_domain.services.quality_service import QualityService


class SyncOrchestrator:
    def __init__(self) -> None:
        self.raw_repo = RawRepository()
        self.stg_repo = StagingRepository()
        self.core_repo = CoreRepository()
        self.sync_repo = SyncRunRepository()
        self.instrument_repo = InstrumentLookupRepository()
        self.quality_service = QualityService()
        self.lineage_service = LineageService()

    def process_daily_bar_batch(
        self,
        session: Session,
        sync_run_id: int,
        batch_id: int,
        dtos: list[DailyBarDTO],
        data_version_id: int,
        is_open_day_lookup: Callable[[str, object], bool | None] | None = None,
        instrument_lifecycle_lookup: Callable[[str, str, str], object] | None = None,
    ) -> dict:
        input_rows = len(dtos)
        raw_rows = 0
        staging_rows = 0
        core_upsert_rows = 0
        error_rows = 0

        for dto in dtos:
            try:
                raw_payload = dto_to_raw_daily_bar_dict(dto=dto, sync_run_id=sync_run_id, batch_id=batch_id)
                raw_obj = self.raw_repo.upsert_raw_daily_bar(session, raw_payload)
                raw_rows += 1

                stg_payload = dto_to_staging_daily_bar_dict(
                    dto=dto,
                    sync_run_id=sync_run_id,
                    batch_id=batch_id,
                    raw_record_id=raw_obj.id,
                )

                issues = []
                issues.extend(self.quality_service.validate_daily_bar_row(stg_payload))

                if is_open_day_lookup is not None:
                    issues.extend(
                        self.quality_service.validate_trade_date_is_open_day(
                            stg_payload,
                            is_open_day_lookup=is_open_day_lookup,
                        )
                    )

                if instrument_lifecycle_lookup is not None:
                    issues.extend(
                        self.quality_service.validate_trade_date_within_instrument_lifecycle(
                            stg_payload,
                            instrument_lifecycle_lookup=instrument_lifecycle_lookup,
                        )
                    )

                for issue in issues:
                    if not issue.passed:
                        self.sync_repo.add_quality_issue(
                            session,
                            {
                                "data_sync_run_id": sync_run_id,
                                "batch_id": batch_id,
                                "theme_code": "DailyBar",
                                "dataset_code": "daily_bar",
                                "layer_code": "STAGING",
                                "issue_code": issue.issue_code,
                                "severity": issue.severity,
                                "business_key": f'{stg_payload["ticker"]}:{stg_payload["trade_date"]}:{stg_payload["price_adjust_type"]}',
                                "provider_name": stg_payload["provider_name"],
                                "trade_date": stg_payload["trade_date"],
                                "symbol": stg_payload["ticker"],
                                "record_ref": {"raw_record_id": raw_obj.id},
                                "issue_detail": issue.detail,
                                "created_at": datetime.utcnow(),
                            },
                        )

                blocking_issues = [x for x in issues if not x.passed and x.severity in ("ERROR", "FATAL")]
                if blocking_issues:
                    error_rows += 1
                    continue

                stg_obj = self.stg_repo.upsert_stg_daily_bar(session, stg_payload)
                staging_rows += 1

                self.sync_repo.add_lineage(
                    session,
                    self.lineage_service.build_raw_to_staging(
                        sync_run_id=sync_run_id,
                        batch_id=batch_id,
                        raw_id=raw_obj.id,
                        stg_id=stg_obj.id,
                    ),
                )

                instrument_id = self.instrument_repo.get_instrument_id(
                    session=session,
                    market_code=stg_payload["market_code"],
                    exchange_code=stg_payload["exchange_code"],
                    ticker=stg_payload["ticker"],
                )
                if instrument_id is None:
                    self.sync_repo.add_quality_issue(
                        session,
                        {
                            "data_sync_run_id": sync_run_id,
                            "batch_id": batch_id,
                            "theme_code": "DailyBar",
                            "dataset_code": "daily_bar",
                            "layer_code": "CORE",
                            "issue_code": "INSTRUMENT_NOT_FOUND",
                            "severity": "ERROR",
                            "business_key": f'{stg_payload["ticker"]}:{stg_payload["trade_date"]}:{stg_payload["price_adjust_type"]}',
                            "provider_name": stg_payload["provider_name"],
                            "trade_date": stg_payload["trade_date"],
                            "symbol": stg_payload["ticker"],
                            "record_ref": {"stg_id": stg_obj.id},
                            "issue_detail": {"ticker": stg_payload["ticker"], "exchange_code": stg_payload["exchange_code"]},
                            "created_at": datetime.utcnow(),
                        },
                    )
                    error_rows += 1
                    continue

                core_payload = staging_to_core_daily_bar_dict(
                    stg_row=stg_payload,
                    instrument_id=instrument_id,
                    data_version_id=data_version_id,
                )

                self.core_repo.upsert_daily_bar(session, core_payload)
                core_upsert_rows += 1

                self.sync_repo.add_lineage(
                    session,
                    self.lineage_service.build_staging_to_core(
                        sync_run_id=sync_run_id,
                        batch_id=batch_id,
                        stg_id=stg_obj.id,
                        instrument_id=instrument_id,
                        trade_date=str(stg_payload["trade_date"]),
                        price_adjust_type=stg_payload["price_adjust_type"],
                    ),
                )



            except Exception as exc:  # noqa: BLE001

                session.rollback()

                error_rows += 1

                try:

                    self.sync_repo.add_quality_issue(

                        session,

                        {

                            "data_sync_run_id": sync_run_id,

                            "batch_id": batch_id,

                            "theme_code": "DailyBar",

                            "dataset_code": "daily_bar",

                            "layer_code": "STAGING",

                            "issue_code": "UNHANDLED_EXCEPTION",

                            "severity": "ERROR",

                            "business_key": None,

                            "provider_name": getattr(dto, "provider_name", None),

                            "trade_date": getattr(dto, "trade_date", None),

                            "symbol": getattr(dto, "ticker", None),

                            "record_ref": None,

                            "issue_detail": {"error": str(exc)},

                            "created_at": datetime.utcnow(),

                        },

                    )

                    session.commit()

                except Exception:

                    session.rollback()

        return {
            "input_rows": input_rows,
            "raw_rows": raw_rows,
            "staging_rows": staging_rows,
            "core_upsert_rows": core_upsert_rows,
            "error_rows": error_rows,
            "status": SyncStatus.SUCCESS.value if error_rows == 0 else SyncStatus.PARTIAL.value,
        }