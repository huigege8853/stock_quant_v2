from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from stock_quant_v2.analytics_domain.constants import FEATURE_CODES, FEATURE_SET_CODES, FEATURE_VERSION_V1
from stock_quant_v2.analytics_domain.repositories.feature_snapshot_repository import FeatureSnapshotRepository


@dataclass
class FeatureBuildResult:
    trade_date: date
    deleted_rows: int
    inserted_rows: int


class FeatureBuildService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.snapshot_repo = FeatureSnapshotRepository(session=session)

    def build_for_trade_date(
        self,
        trade_date: date,
        run_id: int,
        data_version_id: int | None = None,
    ) -> FeatureBuildResult:
        feature_set_code = FEATURE_SET_CODES["FS_DAILY_ALPHA_V1"]
        feature_set_version = FEATURE_VERSION_V1

        feature_rows = self._load_feature_source_rows(trade_date=trade_date)
        if not feature_rows:
            return FeatureBuildResult(trade_date=trade_date, deleted_rows=0, inserted_rows=0)

        rows_to_insert: list[dict[str, Any]] = []
        for row in feature_rows:
            feature_value_numeric = row["source_value_numeric"]
            rows_to_insert.append(
                {
                    "trade_date": trade_date,
                    "instrument_id": int(row["instrument_id"]),
                    "feature_code": str(row["feature_code"]),
                    "feature_set_code": feature_set_code,
                    "feature_set_version": feature_set_version,
                    "feature_value_numeric": feature_value_numeric,
                    "feature_value_text": None,
                    "is_imputed": False,
                    "impute_method": None,
                    "scaling_applied": "none",
                    "sample_status": "ready" if feature_value_numeric is not None else "missing",
                    "run_id": run_id,
                }
            )

        deleted_rows = self.snapshot_repo.delete_by_trade_date_feature_set_and_codes(
            trade_date=trade_date,
            feature_set_code=feature_set_code,
            feature_set_version=feature_set_version,
            feature_codes=[
                FEATURE_CODES["FEAT_MOM_20"],
                FEATURE_CODES["FEAT_TREND_STRENGTH_20"],
                FEATURE_CODES["FEAT_VOLATILITY_RANK_20"],
                FEATURE_CODES["FEAT_TRADABILITY_SCORE"],
                FEATURE_CODES["FEAT_TRADABLE_FLAG"],
            ],
        )
        self.snapshot_repo.bulk_insert(rows_to_insert)

        return FeatureBuildResult(
            trade_date=trade_date,
            deleted_rows=deleted_rows,
            inserted_rows=len(rows_to_insert),
        )

    def _load_feature_source_rows(self, trade_date: date) -> list[dict[str, Any]]:
        sql = text(
            """
            SELECT
                f.trade_date,
                f.instrument_id,
                CASE
                    WHEN f.factor_code = 'mom_20' THEN 'feat_mom_20'
                    WHEN f.factor_code = 'trend_strength_20' THEN 'feat_trend_strength_20'
                    WHEN f.factor_code = 'volatility_rank_20' THEN 'feat_volatility_rank_20'
                    WHEN f.factor_code = 'tradability_score' THEN 'feat_tradability_score'
                    ELSE NULL
                END AS feature_code,
                f.raw_value AS source_value_numeric
            FROM analytics_instrument_factor_snapshot f
            WHERE f.trade_date = :trade_date
              AND f.definition_version = 'v1'
              AND f.factor_code IN (
                  'mom_20',
                  'trend_strength_20',
                  'volatility_rank_20',
                  'tradability_score'
              )

            UNION ALL

            SELECT
                i.trade_date,
                i.instrument_id,
                'feat_tradable_flag' AS feature_code,
                i.value_numeric AS source_value_numeric
            FROM analytics_instrument_indicator_snapshot i
            WHERE i.trade_date = :trade_date
              AND i.definition_version = 'v1'
              AND i.indicator_code = 'tradable_flag'
            """
        )
        rows = self.session.execute(sql, {"trade_date": trade_date}).mappings().all()
        return [dict(row) for row in rows if row["feature_code"] is not None]