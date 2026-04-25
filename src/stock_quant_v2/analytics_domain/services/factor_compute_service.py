from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from math import floor
from statistics import pstdev
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from stock_quant_v2.analytics_domain.calculators.factors_momentum import calc_mom_20, calc_trend_strength
from stock_quant_v2.analytics_domain.calculators.factors_tradability import calc_tradability_score
from stock_quant_v2.analytics_domain.constants import FACTOR_CODES, FACTOR_VERSION_V1, INDICATOR_CODES
from stock_quant_v2.analytics_domain.repositories.factor_snapshot_repository import FactorSnapshotRepository


@dataclass
class FactorComputeResult:
    trade_date: date
    deleted_rows: int
    inserted_rows: int


class FactorComputeService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.snapshot_repo = FactorSnapshotRepository(session=session)

    def compute_for_trade_date(
        self,
        trade_date: date,
        run_id: int,
        data_version_id: int | None = None,
    ) -> FactorComputeResult:
        indicator_rows = self._load_indicator_snapshot(trade_date=trade_date)
        if not indicator_rows:
            return FactorComputeResult(trade_date=trade_date, deleted_rows=0, inserted_rows=0)

        per_instrument = self._group_indicator_rows(indicator_rows=indicator_rows)

        raw_factor_values: dict[str, dict[int, Decimal | None]] = {
            FACTOR_CODES["MOM_20"]: {},
            FACTOR_CODES["TREND_STRENGTH_20"]: {},
            FACTOR_CODES["VOLATILITY_RANK_20"]: {},
            FACTOR_CODES["TRADABILITY_SCORE"]: {},
        }

        instrument_ids = sorted(per_instrument.keys())
        for instrument_id in instrument_ids:
            item = per_instrument[instrument_id]

            ret_20d = self._extract_ready_numeric(item, INDICATOR_CODES["RET_20D"])
            adj_close = self._extract_ready_numeric(item, INDICATOR_CODES["ADJ_CLOSE"])
            ma_20 = self._extract_ready_numeric(item, INDICATOR_CODES["MA_20"])
            volatility_20 = self._extract_ready_numeric(item, INDICATOR_CODES["VOLATILITY_20"])
            tradable_flag = self._extract_ready_numeric(item, INDICATOR_CODES["TRADABLE_FLAG"])

            raw_factor_values[FACTOR_CODES["MOM_20"]][instrument_id] = calc_mom_20(ret_20d)
            raw_factor_values[FACTOR_CODES["TREND_STRENGTH_20"]][instrument_id] = calc_trend_strength(
                adj_close=adj_close,
                ma_20=ma_20,
            )
            raw_factor_values[FACTOR_CODES["VOLATILITY_RANK_20"]][instrument_id] = volatility_20
            raw_factor_values[FACTOR_CODES["TRADABILITY_SCORE"]][instrument_id] = calc_tradability_score(
                tradable_flag=tradable_flag
            )

        rows_to_insert: list[dict[str, Any]] = []
        for factor_code, values_by_instrument in raw_factor_values.items():
            standardized_map = self._calc_zscore(values_by_instrument)
            rank_map = self._calc_percent_rank(values_by_instrument)
            bucket_map = self._calc_quintile_bucket(rank_map)

            for instrument_id in instrument_ids:
                raw_value = values_by_instrument.get(instrument_id)
                rows_to_insert.append(
                    {
                        "trade_date": trade_date,
                        "instrument_id": instrument_id,
                        "factor_code": factor_code,
                        "definition_version": FACTOR_VERSION_V1,
                        "raw_value": raw_value,
                        "winsorized_value": raw_value,
                        "standardized_value": standardized_map.get(instrument_id),
                        "rank_value": rank_map.get(instrument_id),
                        "bucket_value": bucket_map.get(instrument_id),
                        "is_ready": raw_value is not None,
                        "data_version_id": data_version_id,
                        "run_id": run_id,
                    }
                )

        deleted_rows = self.snapshot_repo.delete_by_trade_date_and_codes(
            trade_date=trade_date,
            factor_codes=[
                FACTOR_CODES["MOM_20"],
                FACTOR_CODES["TREND_STRENGTH_20"],
                FACTOR_CODES["VOLATILITY_RANK_20"],
                FACTOR_CODES["TRADABILITY_SCORE"],
            ],
        )
        self.snapshot_repo.bulk_insert(rows_to_insert)

        return FactorComputeResult(
            trade_date=trade_date,
            deleted_rows=deleted_rows,
            inserted_rows=len(rows_to_insert),
        )

    def _load_indicator_snapshot(self, trade_date: date) -> list[dict[str, Any]]:
        sql = text(
            """
            SELECT
                instrument_id,
                indicator_code,
                value_numeric,
                is_ready,
                warmup_ready
            FROM analytics_instrument_indicator_snapshot
            WHERE trade_date = :trade_date
              AND definition_version = 'v1'
              AND indicator_code IN (
                  :adj_close,
                  :ret_20d,
                  :ma_20,
                  :volatility_20,
                  :tradable_flag
              )
            """
        )
        rows = self.session.execute(
            sql,
            {
                "trade_date": trade_date,
                "adj_close": INDICATOR_CODES["ADJ_CLOSE"],
                "ret_20d": INDICATOR_CODES["RET_20D"],
                "ma_20": INDICATOR_CODES["MA_20"],
                "volatility_20": INDICATOR_CODES["VOLATILITY_20"],
                "tradable_flag": INDICATOR_CODES["TRADABLE_FLAG"],
            },
        ).mappings().all()
        return [dict(row) for row in rows]

    @staticmethod
    def _group_indicator_rows(indicator_rows: list[dict[str, Any]]) -> dict[int, dict[str, dict[str, Any]]]:
        result: dict[int, dict[str, dict[str, Any]]] = {}
        for row in indicator_rows:
            instrument_id = int(row["instrument_id"])
            indicator_code = str(row["indicator_code"])
            result.setdefault(instrument_id, {})
            result[instrument_id][indicator_code] = row
        return result

    @staticmethod
    def _extract_ready_numeric(item: dict[str, dict[str, Any]], indicator_code: str) -> Decimal | None:
        row = item.get(indicator_code)
        if row is None:
            return None
        if not row.get("is_ready"):
            return None
        if not row.get("warmup_ready"):
            return None

        value = row.get("value_numeric")
        if value is None:
            return None
        return Decimal(str(value))

    @staticmethod
    def _calc_zscore(values_by_instrument: dict[int, Decimal | None]) -> dict[int, Decimal | None]:
        numeric_items = [(k, float(v)) for k, v in values_by_instrument.items() if v is not None]
        if not numeric_items:
            return {k: None for k in values_by_instrument}

        raw_values = [v for _, v in numeric_items]
        mean_value = sum(raw_values) / len(raw_values)
        std_value = pstdev(raw_values) if len(raw_values) >= 2 else 0.0

        result: dict[int, Decimal | None] = {}
        for instrument_id, raw_value in values_by_instrument.items():
            if raw_value is None:
                result[instrument_id] = None
                continue
            if std_value == 0:
                result[instrument_id] = Decimal("0")
                continue
            z = (float(raw_value) - mean_value) / std_value
            result[instrument_id] = Decimal(str(z))
        return result

    @staticmethod
    def _calc_percent_rank(values_by_instrument: dict[int, Decimal | None]) -> dict[int, Decimal | None]:
        numeric_items = [(k, Decimal(str(v))) for k, v in values_by_instrument.items() if v is not None]
        result: dict[int, Decimal | None] = {k: None for k in values_by_instrument}

        if not numeric_items:
            return result

        value_to_ids: dict[Decimal, list[int]] = {}
        for instrument_id, value in numeric_items:
            value_to_ids.setdefault(value, []).append(instrument_id)

        unique_sorted_values = sorted(value_to_ids.keys())
        total = len(numeric_items)

        if total == 1:
            only_key = numeric_items[0][0]
            result[only_key] = Decimal("1")
            return result

        cumulative_count = 0
        for value in unique_sorted_values:
            ids = value_to_ids[value]
            group_size = len(ids)

            # 采用组中位次对应的百分位，保证相同值同 rank
            avg_position = cumulative_count + (group_size + 1) / 2
            pct = (avg_position - 1) / (total - 1)

            pct_decimal = Decimal(str(pct))
            for instrument_id in ids:
                result[instrument_id] = pct_decimal

            cumulative_count += group_size

        return result

    @staticmethod
    def _calc_quintile_bucket(rank_map: dict[int, Decimal | None]) -> dict[int, str | None]:
        result: dict[int, str | None] = {}
        for instrument_id, rank_value in rank_map.items():
            if rank_value is None:
                result[instrument_id] = None
                continue

            rank_float = float(rank_value)

            if rank_float <= 0.2:
                bucket = "Q1"
            elif rank_float <= 0.4:
                bucket = "Q2"
            elif rank_float <= 0.6:
                bucket = "Q3"
            elif rank_float <= 0.8:
                bucket = "Q4"
            else:
                bucket = "Q5"

            result[instrument_id] = bucket
        return result