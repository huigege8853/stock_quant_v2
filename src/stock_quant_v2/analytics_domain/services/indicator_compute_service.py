from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from stock_quant_v2.analytics_domain.calculators.indicators_tradability import calc_tradable_flag
from stock_quant_v2.analytics_domain.calculators.indicators_trend import calc_simple_moving_average
from stock_quant_v2.analytics_domain.calculators.indicators_volatility import calc_population_std
from stock_quant_v2.analytics_domain.calculators.primitive_metrics import calc_adj_close, calc_return
from stock_quant_v2.analytics_domain.constants import INDICATOR_CODES, INDICATOR_VERSION_V1
from stock_quant_v2.analytics_domain.repositories.indicator_snapshot_repository import IndicatorSnapshotRepository
from stock_quant_v2.analytics_domain.services.analytics_universe_service import AnalyticsUniverseService
from stock_quant_v2.analytics_domain.services.warmup_service import WarmupService


DEFAULT_REQUIRED_LOOKBACK_BARS = 21
REQUIRED_INDICATOR_CODES = [
    INDICATOR_CODES["ADJ_CLOSE"],
    INDICATOR_CODES["RET_1D"],
    INDICATOR_CODES["RET_20D"],
    INDICATOR_CODES["MA_20"],
    INDICATOR_CODES["VOLATILITY_20"],
    INDICATOR_CODES["TRADABLE_FLAG"],
]


@dataclass
class IndicatorComputeResult:
    trade_date: date
    deleted_rows: int
    inserted_rows: int
    lookback_bars: int
    window_start_date: date | None


class IndicatorComputeService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.universe_service = AnalyticsUniverseService(session=session)
        self.snapshot_repo = IndicatorSnapshotRepository(session=session)
        self.warmup_service = WarmupService()

    def compute_for_trade_date(
        self,
        trade_date: date,
        run_id: int,
        data_version_id: int | None = None,
    ) -> IndicatorComputeResult:
        instrument_ids = self.universe_service.get_trade_date_instruments(trade_date=trade_date)
        if not instrument_ids:
            return IndicatorComputeResult(
                trade_date=trade_date,
                deleted_rows=0,
                inserted_rows=0,
                lookback_bars=DEFAULT_REQUIRED_LOOKBACK_BARS,
                window_start_date=None,
            )

        required_lookback_bars = self._resolve_required_lookback_bars()
        window_start_date = self._resolve_window_start_date(
            trade_date=trade_date,
            required_lookback_bars=required_lookback_bars,
        )
        if window_start_date is None:
            window_start_date = trade_date

        market_data = self._load_market_window_data(
            trade_date=trade_date,
            window_start_date=window_start_date,
            instrument_ids=instrument_ids,
        )

        rows_to_insert: list[dict[str, Any]] = []
        for instrument_id in instrument_ids:
            instrument_rows = market_data.get(instrument_id, [])
            if not instrument_rows:
                continue

            rows_to_insert.extend(
                self._build_indicator_rows(
                    trade_date=trade_date,
                    run_id=run_id,
                    data_version_id=data_version_id,
                    instrument_id=instrument_id,
                    instrument_rows=instrument_rows,
                )
            )

        deleted_rows = self.snapshot_repo.delete_by_trade_date_and_codes(
            trade_date=trade_date,
            indicator_codes=REQUIRED_INDICATOR_CODES,
        )
        self.snapshot_repo.bulk_insert(rows_to_insert)

        return IndicatorComputeResult(
            trade_date=trade_date,
            deleted_rows=deleted_rows,
            inserted_rows=len(rows_to_insert),
            lookback_bars=required_lookback_bars,
            window_start_date=window_start_date,
        )

    def _resolve_required_lookback_bars(self) -> int:
        sql = text(
            """
            SELECT COALESCE(MAX(GREATEST(COALESCE(window_size, 0), COALESCE(warmup_bars, 0))), 0) AS max_required_bars
            FROM meta_indicator_definition
            WHERE is_active = TRUE
              AND indicator_code IN :indicator_codes
            """
        ).bindparams(bindparam("indicator_codes", expanding=True))
        value = self.session.execute(sql, {"indicator_codes": REQUIRED_INDICATOR_CODES}).scalar_one_or_none()
        max_required = int(value or 0)
        return max(max_required, DEFAULT_REQUIRED_LOOKBACK_BARS)

    def _resolve_window_start_date(self, trade_date: date, required_lookback_bars: int) -> date | None:
        sql = text(
            """
            WITH trade_days AS (
                SELECT DISTINCT trade_date
                FROM core_daily_bar
                WHERE price_adjust_type = 'RAW'
                  AND trade_date <= :trade_date
            ), ranked AS (
                SELECT trade_date
                FROM trade_days
                ORDER BY trade_date DESC
                LIMIT :required_rows
            )
            SELECT MIN(trade_date) AS window_start_date
            FROM ranked
            """
        )
        value = self.session.execute(
            sql,
            {
                "trade_date": trade_date,
                "required_rows": required_lookback_bars,
            },
        ).scalar_one_or_none()
        return self._coerce_to_date(value)

    def _load_market_window_data(
        self,
        trade_date: date,
        window_start_date: date,
        instrument_ids: list[int],
    ) -> dict[int, list[dict[str, Any]]]:
        sql = (
            text(
                """
                SELECT
                    db.instrument_id,
                    db.trade_date,
                    db.close AS close_price,
                    af.forward_factor AS adjust_factor,
                    pl.up_limit AS up_limit_price,
                    COALESCE(isd.trading_status, 'NO_BAR') AS trading_status,
                    COALESCE(isd.is_suspended, false) AS is_suspended
                FROM core_daily_bar db
                LEFT JOIN core_adjust_factor af
                    ON af.instrument_id = db.instrument_id
                   AND af.trade_date = db.trade_date
                LEFT JOIN core_price_limit_daily pl
                    ON pl.instrument_id = db.instrument_id
                   AND pl.trade_date = db.trade_date
                LEFT JOIN core_instrument_status_daily isd
                    ON isd.instrument_id = db.instrument_id
                   AND isd.trade_date = db.trade_date
                WHERE db.instrument_id IN :instrument_ids
                  AND db.trade_date BETWEEN :window_start_date AND :trade_date
                  AND db.price_adjust_type = 'RAW'
                ORDER BY db.instrument_id, db.trade_date
                """
            ).bindparams(bindparam("instrument_ids", expanding=True))
        )

        rows = self.session.execute(
            sql,
            {
                "instrument_ids": instrument_ids,
                "window_start_date": window_start_date,
                "trade_date": trade_date,
            },
        ).mappings().all()

        grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[int(row["instrument_id"])].append(dict(row))
        return grouped

    def _build_indicator_rows(
        self,
        trade_date: date,
        run_id: int,
        data_version_id: int | None,
        instrument_id: int,
        instrument_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        current_idx = None
        for idx, row in enumerate(instrument_rows):
            if row["trade_date"] == trade_date:
                current_idx = idx
                break
        if current_idx is None:
            return []

        current_row = instrument_rows[current_idx]
        hist_rows = instrument_rows[: current_idx + 1]

        adj_close_series: list[Decimal | None] = [
            calc_adj_close(row.get("close_price"), row.get("adjust_factor"))
            for row in hist_rows
        ]

        ret_1d_series: list[Decimal | None] = []
        for i, adj_close in enumerate(adj_close_series):
            prev = adj_close_series[i - 1] if i >= 1 else None
            ret_1d_series.append(calc_return(adj_close, prev))

        current_adj_close = adj_close_series[-1]
        current_ret_1d = ret_1d_series[-1]

        current_ret_20d = calc_return(
            adj_close_series[-1],
            adj_close_series[-21] if len(adj_close_series) >= 21 else None,
        )

        ma20_values = adj_close_series[-20:]
        current_ma20 = calc_simple_moving_average(ma20_values) if len(ma20_values) == 20 else None

        vol20_values = ret_1d_series[-20:]
        current_vol20 = calc_population_std(vol20_values) if len(vol20_values) == 20 else None

        current_tradable_flag = calc_tradable_flag(
            trading_status=current_row.get("trading_status"),
            is_suspended=bool(current_row.get("is_suspended")),
            close_price=current_row.get("close_price"),
            up_limit_price=current_row.get("up_limit_price"),
        )

        results: list[dict[str, Any]] = []
        results.append(
            self._build_snapshot_row(
                trade_date=trade_date,
                instrument_id=instrument_id,
                indicator_code=INDICATOR_CODES["ADJ_CLOSE"],
                value_numeric=current_adj_close,
                warmup_ready=True,
                run_id=run_id,
                data_version_id=data_version_id,
            )
        )
        results.append(
            self._build_snapshot_row(
                trade_date=trade_date,
                instrument_id=instrument_id,
                indicator_code=INDICATOR_CODES["RET_1D"],
                value_numeric=current_ret_1d,
                warmup_ready=self.warmup_service.is_warmup_ready(len(adj_close_series), 2),
                run_id=run_id,
                data_version_id=data_version_id,
            )
        )
        results.append(
            self._build_snapshot_row(
                trade_date=trade_date,
                instrument_id=instrument_id,
                indicator_code=INDICATOR_CODES["RET_20D"],
                value_numeric=current_ret_20d,
                warmup_ready=self.warmup_service.is_warmup_ready(len(adj_close_series), 21),
                run_id=run_id,
                data_version_id=data_version_id,
            )
        )
        results.append(
            self._build_snapshot_row(
                trade_date=trade_date,
                instrument_id=instrument_id,
                indicator_code=INDICATOR_CODES["MA_20"],
                value_numeric=current_ma20,
                warmup_ready=self.warmup_service.is_warmup_ready(len(adj_close_series), 20),
                run_id=run_id,
                data_version_id=data_version_id,
            )
        )
        results.append(
            self._build_snapshot_row(
                trade_date=trade_date,
                instrument_id=instrument_id,
                indicator_code=INDICATOR_CODES["VOLATILITY_20"],
                value_numeric=current_vol20,
                warmup_ready=self.warmup_service.is_warmup_ready(len(ret_1d_series), 20),
                run_id=run_id,
                data_version_id=data_version_id,
            )
        )
        results.append(
            self._build_snapshot_row(
                trade_date=trade_date,
                instrument_id=instrument_id,
                indicator_code=INDICATOR_CODES["TRADABLE_FLAG"],
                value_numeric=Decimal("1") if current_tradable_flag else Decimal("0"),
                warmup_ready=True,
                run_id=run_id,
                data_version_id=data_version_id,
            )
        )
        return results

    @staticmethod
    def _build_snapshot_row(
        trade_date: date,
        instrument_id: int,
        indicator_code: str,
        value_numeric: Decimal | None,
        warmup_ready: bool,
        run_id: int,
        data_version_id: int | None,
    ) -> dict[str, Any]:
        return {
            "trade_date": trade_date,
            "instrument_id": instrument_id,
            "indicator_code": indicator_code,
            "definition_version": INDICATOR_VERSION_V1,
            "value_numeric": value_numeric,
            "value_text": None,
            "is_ready": value_numeric is not None,
            "warmup_ready": warmup_ready,
            "data_version_id": data_version_id,
            "run_id": run_id,
        }

    @staticmethod
    def _coerce_to_date(value: Any | None) -> date | None:
        if value is None:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            return datetime.strptime(value, "%Y-%m-%d").date()
        return None
