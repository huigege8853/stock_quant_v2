from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from stock_quant_v2.analytics_domain.calculators.labels_forward_return import (
    calc_binary_down_label,
    calc_binary_up_label,
    calc_forward_return,
)
from stock_quant_v2.analytics_domain.constants import LABEL_CODES, LABEL_VERSION_V1
from stock_quant_v2.analytics_domain.repositories.label_snapshot_repository import LabelSnapshotRepository


MAX_LABEL_HORIZON_DAYS = 10
REQUIRED_LABEL_CODES = [
    LABEL_CODES["LABEL_FWD_RET_5D"],
    LABEL_CODES["LABEL_FWD_RET_10D"],
    LABEL_CODES["LABEL_UP_5D_GE_3PCT"],
    LABEL_CODES["LABEL_DOWN_5D_LE_M3PCT"],
]


@dataclass
class LabelBuildResult:
    anchor_date: date
    deleted_rows: int
    inserted_rows: int
    horizon_end_date: date | None


class LabelBuildService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.snapshot_repo = LabelSnapshotRepository(session=session)

    def build_for_anchor_date(
        self,
        anchor_date: date,
        run_id: int,
        data_version_id: int | None = None,
    ) -> LabelBuildResult:
        instrument_ids = self._load_anchor_instruments(anchor_date=anchor_date)
        if not instrument_ids:
            return LabelBuildResult(anchor_date=anchor_date, deleted_rows=0, inserted_rows=0, horizon_end_date=None)

        horizon_end_date = self._resolve_horizon_end_date(anchor_date=anchor_date, horizon_days=MAX_LABEL_HORIZON_DAYS)
        if horizon_end_date is None:
            horizon_end_date = anchor_date

        price_history = self._load_price_window(
            anchor_date=anchor_date,
            horizon_end_date=horizon_end_date,
            instrument_ids=instrument_ids,
        )

        rows_to_insert: list[dict[str, Any]] = []
        for instrument_id in instrument_ids:
            series = price_history.get(instrument_id, [])
            if not series:
                continue

            rows_to_insert.extend(
                self._build_label_rows(
                    anchor_date=anchor_date,
                    instrument_id=instrument_id,
                    series=series,
                    run_id=run_id,
                    data_version_id=data_version_id,
                )
            )

        deleted_rows = self.snapshot_repo.delete_by_anchor_date_and_codes(
            anchor_date=anchor_date,
            label_codes=REQUIRED_LABEL_CODES,
        )
        self.snapshot_repo.bulk_insert(rows_to_insert)

        return LabelBuildResult(
            anchor_date=anchor_date,
            deleted_rows=deleted_rows,
            inserted_rows=len(rows_to_insert),
            horizon_end_date=horizon_end_date,
        )

    def _load_anchor_instruments(self, anchor_date: date) -> list[int]:
        sql = text(
            """
            SELECT DISTINCT instrument_id
            FROM core_daily_bar
            WHERE trade_date = :anchor_date
              AND price_adjust_type = 'RAW'
            ORDER BY instrument_id
            """
        )
        rows = self.session.execute(sql, {"anchor_date": anchor_date}).mappings().all()
        return [int(row["instrument_id"]) for row in rows]

    def _resolve_horizon_end_date(self, anchor_date: date, horizon_days: int) -> date | None:
        sql = text(
            """
            WITH trade_days AS (
                SELECT DISTINCT trade_date
                FROM core_daily_bar
                WHERE price_adjust_type = 'RAW'
                  AND trade_date >= :anchor_date
            ), ranked AS (
                SELECT trade_date
                FROM trade_days
                ORDER BY trade_date ASC
                LIMIT :required_rows
            )
            SELECT MAX(trade_date) AS horizon_end_date
            FROM ranked
            """
        )
        value = self.session.execute(
            sql,
            {
                "anchor_date": anchor_date,
                "required_rows": horizon_days + 1,
            },
        ).scalar_one_or_none()
        return self._coerce_to_date(value)

    def _load_price_window(self, anchor_date: date, horizon_end_date: date, instrument_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
        sql = (
            text(
                """
                SELECT
                    db.instrument_id,
                    db.trade_date,
                    db.close AS close_price,
                    af.forward_factor AS forward_factor
                FROM core_daily_bar db
                LEFT JOIN core_adjust_factor af
                    ON af.instrument_id = db.instrument_id
                   AND af.trade_date = db.trade_date
                WHERE db.instrument_id IN :instrument_ids
                  AND db.trade_date BETWEEN :anchor_date AND :horizon_end_date
                  AND db.price_adjust_type = 'RAW'
                ORDER BY db.instrument_id, db.trade_date
                """
            ).bindparams(bindparam("instrument_ids", expanding=True))
        )

        rows = self.session.execute(
            sql,
            {
                "instrument_ids": instrument_ids,
                "anchor_date": anchor_date,
                "horizon_end_date": horizon_end_date,
            },
        ).mappings().all()

        grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[int(row["instrument_id"])].append(dict(row))
        return grouped

    def _build_label_rows(
        self,
        anchor_date: date,
        instrument_id: int,
        series: list[dict[str, Any]],
        run_id: int,
        data_version_id: int | None,
    ) -> list[dict[str, Any]]:
        anchor_idx = None
        for idx, row in enumerate(series):
            if row["trade_date"] == anchor_date:
                anchor_idx = idx
                break
        if anchor_idx is None:
            return []

        anchor_row = series[anchor_idx]
        anchor_adj_close = self._calc_adj_close(
            close_price=anchor_row.get("close_price"),
            forward_factor=anchor_row.get("forward_factor"),
        )

        future_5_row = series[anchor_idx + 5] if len(series) > anchor_idx + 5 else None
        future_10_row = series[anchor_idx + 10] if len(series) > anchor_idx + 10 else None

        future_5_adj_close = self._calc_adj_close_from_row(future_5_row)
        future_10_adj_close = self._calc_adj_close_from_row(future_10_row)

        fwd_ret_5d = calc_forward_return(anchor_adj_close=anchor_adj_close, future_adj_close=future_5_adj_close)
        fwd_ret_10d = calc_forward_return(anchor_adj_close=anchor_adj_close, future_adj_close=future_10_adj_close)

        horizon_5_end_date = future_5_row["trade_date"] if future_5_row is not None else anchor_date
        horizon_10_end_date = future_10_row["trade_date"] if future_10_row is not None else anchor_date

        up_5d_ge_3pct = calc_binary_up_label(fwd_ret_5d, Decimal("0.03"))
        down_5d_le_m3pct = calc_binary_down_label(fwd_ret_5d, Decimal("-0.03"))

        rows: list[dict[str, Any]] = []
        rows.append(
            self._build_snapshot_row(
                anchor_date=anchor_date,
                instrument_id=instrument_id,
                label_code=LABEL_CODES["LABEL_FWD_RET_5D"],
                label_value_numeric=fwd_ret_5d,
                label_value_class=None,
                horizon_end_date=horizon_5_end_date,
                is_censored=(future_5_row is None or anchor_adj_close is None or future_5_adj_close is None),
                run_id=run_id,
                data_version_id=data_version_id,
            )
        )
        rows.append(
            self._build_snapshot_row(
                anchor_date=anchor_date,
                instrument_id=instrument_id,
                label_code=LABEL_CODES["LABEL_FWD_RET_10D"],
                label_value_numeric=fwd_ret_10d,
                label_value_class=None,
                horizon_end_date=horizon_10_end_date,
                is_censored=(future_10_row is None or anchor_adj_close is None or future_10_adj_close is None),
                run_id=run_id,
                data_version_id=data_version_id,
            )
        )
        rows.append(
            self._build_snapshot_row(
                anchor_date=anchor_date,
                instrument_id=instrument_id,
                label_code=LABEL_CODES["LABEL_UP_5D_GE_3PCT"],
                label_value_numeric=None,
                label_value_class=up_5d_ge_3pct,
                horizon_end_date=horizon_5_end_date,
                is_censored=(future_5_row is None or anchor_adj_close is None or future_5_adj_close is None),
                run_id=run_id,
                data_version_id=data_version_id,
            )
        )
        rows.append(
            self._build_snapshot_row(
                anchor_date=anchor_date,
                instrument_id=instrument_id,
                label_code=LABEL_CODES["LABEL_DOWN_5D_LE_M3PCT"],
                label_value_numeric=None,
                label_value_class=down_5d_le_m3pct,
                horizon_end_date=horizon_5_end_date,
                is_censored=(future_5_row is None or anchor_adj_close is None or future_5_adj_close is None),
                run_id=run_id,
                data_version_id=data_version_id,
            )
        )
        return rows

    @staticmethod
    def _calc_adj_close(close_price, forward_factor) -> Decimal | None:
        if close_price is None or forward_factor is None:
            return None
        return Decimal(str(close_price)) * Decimal(str(forward_factor))

    def _calc_adj_close_from_row(self, row: dict[str, Any] | None) -> Decimal | None:
        if row is None:
            return None
        return self._calc_adj_close(
            close_price=row.get("close_price"),
            forward_factor=row.get("forward_factor"),
        )

    @staticmethod
    def _build_snapshot_row(
        anchor_date: date,
        instrument_id: int,
        label_code: str,
        label_value_numeric: Decimal | None,
        label_value_class: str | None,
        horizon_end_date: date,
        is_censored: bool,
        run_id: int,
        data_version_id: int | None,
    ) -> dict[str, Any]:
        return {
            "anchor_date": anchor_date,
            "instrument_id": instrument_id,
            "label_code": label_code,
            "definition_version": LABEL_VERSION_V1,
            "label_value_numeric": label_value_numeric,
            "label_value_class": label_value_class,
            "horizon_end_date": horizon_end_date,
            "is_censored": is_censored,
            "leakage_checked": True,
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
