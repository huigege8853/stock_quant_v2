from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Callable, Iterable, Sequence

from sqlalchemy import bindparam, delete, select, text
from sqlalchemy.orm import Session

from stock_quant_v2.analytics_domain.constants import FEATURE_CODES, FEATURE_SET_CODES, FEATURE_VERSION_V1
from stock_quant_v2.db.models.analytics.feature_snapshot import AnalyticsFeatureSnapshot


DEFAULT_INDUSTRY_TAG_TYPE = "SW_INDUSTRY_L2"
DEFAULT_WINDOW_SIZE = 20
DEFAULT_MIN_INDUSTRY_SIZE = 1
DEFAULT_MIN_INDUSTRY_COUNT = 5
INDUSTRY_STRENGTH_FEATURE_CODES = (
    "feat_industry_strength_20",
    "feat_industry_ret_20",
    "feat_industry_breadth_20",
)


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _quantize(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(Decimal("0.0000000001"), rounding=ROUND_HALF_UP)


def calc_percent_rank_by_key(values_by_key: dict[str, Decimal | None]) -> dict[str, Decimal | None]:
    """Percent-rank values with deterministic tie handling.

    Returns values in [0, 1]. Larger input value receives larger rank. Ties get
    the average rank position, matching the stock factor rank convention used in
    M3 factor computation.
    """

    numeric_items = [(key, Decimal(str(value))) for key, value in values_by_key.items() if value is not None]
    result: dict[str, Decimal | None] = {key: None for key in values_by_key}
    if not numeric_items:
        return result
    if len(numeric_items) == 1:
        result[numeric_items[0][0]] = Decimal("1")
        return result

    value_to_keys: dict[Decimal, list[str]] = {}
    for key, value in numeric_items:
        value_to_keys.setdefault(value, []).append(key)

    total = len(numeric_items)
    cumulative_count = 0
    for value in sorted(value_to_keys.keys()):
        keys = sorted(value_to_keys[value])
        group_size = len(keys)
        avg_position = cumulative_count + (group_size + 1) / 2
        pct = Decimal(str((avg_position - 1) / (total - 1)))
        for key in keys:
            result[key] = pct
        cumulative_count += group_size
    return result


@dataclass
class IndustryStrengthDateResult:
    trade_date: date
    requested_trade_date: date
    window_size: int
    window_start_date: date | None
    industry_tag_type: str
    deleted_rows: int = 0
    inserted_rows: int = 0
    ready_rows: int = 0
    missing_rows: int = 0
    industry_count: int = 0
    min_industry_count: int = DEFAULT_MIN_INDUSTRY_COUNT
    instrument_count: int = 0
    source_stock_return_rows: int = 0
    status: str = "SKIPPED"
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date.isoformat(),
            "requested_trade_date": self.requested_trade_date.isoformat(),
            "window_size": self.window_size,
            "window_start_date": self.window_start_date.isoformat() if self.window_start_date else None,
            "industry_tag_type": self.industry_tag_type,
            "deleted_rows": self.deleted_rows,
            "inserted_rows": self.inserted_rows,
            "ready_rows": self.ready_rows,
            "missing_rows": self.missing_rows,
            "industry_count": self.industry_count,
            "min_industry_count": self.min_industry_count,
            "instrument_count": self.instrument_count,
            "source_stock_return_rows": self.source_stock_return_rows,
            "status": self.status,
            "reason": self.reason,
        }


@dataclass
class IndustryStrengthBuildResult:
    started_at: str
    finished_at: str | None = None
    status: str = "RUNNING"
    run_id: int | None = None
    report_date: str | None = None
    feature_set_code: str = FEATURE_SET_CODES["FS_DAILY_ALPHA_V1"]
    feature_set_version: str = FEATURE_VERSION_V1
    industry_tag_type: str = DEFAULT_INDUSTRY_TAG_TYPE
    window_size: int = DEFAULT_WINDOW_SIZE
    min_industry_size: int = DEFAULT_MIN_INDUSTRY_SIZE
    min_industry_count: int = DEFAULT_MIN_INDUSTRY_COUNT
    dates: list[IndustryStrengthDateResult] = field(default_factory=list)
    artifact_paths: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "report_date": self.report_date,
            "feature_set_code": self.feature_set_code,
            "feature_set_version": self.feature_set_version,
            "industry_tag_type": self.industry_tag_type,
            "window_size": self.window_size,
            "min_industry_size": self.min_industry_size,
            "min_industry_count": self.min_industry_count,
            "feature_codes": list(INDUSTRY_STRENGTH_FEATURE_CODES),
            "dates": [item.to_dict() for item in self.dates],
            "artifact_paths": self.artifact_paths,
            "scope_guard": {
                "does_not_generate_strategy_signal": True,
                "does_not_submit_backtest": True,
                "does_not_touch_paper_trading": True,
                "does_not_touch_risk": True,
                "does_not_change_scheduler": True,
                "writes_only_existing_analytics_feature_snapshot": True,
            },
        }


class IndustryStrengthFeatureService:
    """Build S1.2 industry strength features into analytics_feature_snapshot.

    This service intentionally uses the existing analytics feature snapshot
    contract. It does not create new tables and does not publish M4 signals.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def resolve_trade_dates(
        self,
        *,
        trade_date: date | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[date]:
        if trade_date is not None:
            resolved = self._resolve_latest_trade_date_on_or_before(trade_date)
            return [resolved] if resolved is not None else []
        if start_date is None or end_date is None:
            raise ValueError("Provide either --trade-date or both --start-date and --end-date.")
        rows = self.session.execute(
            text(
                """
                select distinct trade_date
                from core_daily_bar
                where price_adjust_type = 'RAW'
                  and trade_date between :start_date and :end_date
                order by trade_date
                """
            ),
            {"start_date": start_date, "end_date": end_date},
        ).scalars().all()
        return [self._coerce_date(value) for value in rows]

    def build_for_dates(
        self,
        *,
        trade_dates: Sequence[date],
        run_id: int,
        window_size: int = DEFAULT_WINDOW_SIZE,
        industry_tag_type: str = DEFAULT_INDUSTRY_TAG_TYPE,
        min_industry_size: int = DEFAULT_MIN_INDUSTRY_SIZE,
        min_industry_count: int = DEFAULT_MIN_INDUSTRY_COUNT,
        commit_every: int = 1,
        progress_callback: Callable[[str], None] | None = None,
    ) -> list[IndustryStrengthDateResult]:
        results: list[IndustryStrengthDateResult] = []
        for index, trade_date in enumerate(trade_dates, start=1):
            if progress_callback:
                progress_callback(f"INDUSTRY_STRENGTH_DATE_START {index}/{len(trade_dates)} trade_date={trade_date}")
            result = self.build_for_trade_date(
                trade_date=trade_date,
                run_id=run_id,
                window_size=window_size,
                industry_tag_type=industry_tag_type,
                min_industry_size=min_industry_size,
                min_industry_count=min_industry_count,
            )
            results.append(result)
            if commit_every > 0 and index % commit_every == 0:
                self.session.commit()
                if progress_callback:
                    progress_callback(f"INDUSTRY_STRENGTH_COMMIT date_index={index} trade_date={trade_date}")
            if progress_callback:
                progress_callback(
                    "INDUSTRY_STRENGTH_DATE_DONE "
                    f"{index}/{len(trade_dates)} trade_date={result.trade_date} "
                    f"status={result.status} inserted_rows={result.inserted_rows} "
                    f"ready_rows={result.ready_rows} industry_count={result.industry_count}"
                )
        return results

    def build_for_trade_date(
        self,
        *,
        trade_date: date,
        run_id: int,
        window_size: int = DEFAULT_WINDOW_SIZE,
        industry_tag_type: str = DEFAULT_INDUSTRY_TAG_TYPE,
        min_industry_size: int = DEFAULT_MIN_INDUSTRY_SIZE,
        min_industry_count: int = DEFAULT_MIN_INDUSTRY_COUNT,
    ) -> IndustryStrengthDateResult:
        actual_trade_date = self._resolve_latest_trade_date_on_or_before(trade_date)
        if actual_trade_date is None:
            return IndustryStrengthDateResult(
                trade_date=trade_date,
                requested_trade_date=trade_date,
                window_size=window_size,
                window_start_date=None,
                industry_tag_type=industry_tag_type,
                min_industry_count=min_industry_count,
                status="SKIPPED",
                reason="No core_daily_bar trade_date exists on or before requested date.",
            )

        window_start_date = self._resolve_window_start_date(actual_trade_date, window_size)
        result = IndustryStrengthDateResult(
            trade_date=actual_trade_date,
            requested_trade_date=trade_date,
            window_size=window_size,
            window_start_date=window_start_date,
            industry_tag_type=industry_tag_type,
            min_industry_count=min_industry_count,
        )
        if window_start_date is None:
            result.status = "SKIPPED"
            result.reason = "Insufficient daily bar history for requested window."
            return result

        stock_rows = self._load_stock_industry_returns(
            trade_date=actual_trade_date,
            window_start_date=window_start_date,
            industry_tag_type=industry_tag_type,
        )
        result.source_stock_return_rows = len(stock_rows)
        if not stock_rows:
            result.status = "SKIPPED"
            result.reason = "No stock return rows with active industry assignments were found."
            return result

        industry_stats = self._calc_industry_stats(stock_rows)
        result.industry_count = len(industry_stats)
        if result.industry_count < int(min_industry_count or 0):
            result.status = "SKIPPED"
            result.reason = (
                f"Industry count {result.industry_count} is below required minimum {min_industry_count}; "
                "check industry_tag_type and taxonomy coverage before writing strength features."
            )
            return result

        rank_map = calc_percent_rank_by_key({code: stats["industry_ret_20"] for code, stats in industry_stats.items()})

        rows_to_insert: list[dict[str, Any]] = []
        feature_set_code = FEATURE_SET_CODES["FS_DAILY_ALPHA_V1"]
        feature_set_version = FEATURE_VERSION_V1
        for row in stock_rows:
            industry_code = str(row["industry_code"])
            stats = industry_stats[industry_code]
            ready = int(stats["instrument_count"] or 0) >= min_industry_size
            sample_status = "ready" if ready else "low_sample"
            result.instrument_count += 1
            if ready:
                result.ready_rows += len(INDUSTRY_STRENGTH_FEATURE_CODES)
            else:
                result.missing_rows += len(INDUSTRY_STRENGTH_FEATURE_CODES)

            features = {
                FEATURE_CODES["FEAT_INDUSTRY_STRENGTH_20"]: rank_map.get(industry_code),
                FEATURE_CODES["FEAT_INDUSTRY_RET_20"]: stats["industry_ret_20"],
                FEATURE_CODES["FEAT_INDUSTRY_BREADTH_20"]: stats["industry_breadth_20"],
            }
            for feature_code, value in features.items():
                rows_to_insert.append(
                    {
                        "trade_date": actual_trade_date,
                        "instrument_id": int(row["instrument_id"]),
                        "feature_code": feature_code,
                        "feature_set_code": feature_set_code,
                        "feature_set_version": feature_set_version,
                        "feature_value_numeric": _quantize(value),
                        "feature_value_text": industry_code,
                        "is_imputed": False,
                        "impute_method": None,
                        "scaling_applied": "industry_rank" if feature_code == FEATURE_CODES["FEAT_INDUSTRY_STRENGTH_20"] else "none",
                        "sample_status": sample_status,
                        "run_id": run_id,
                    }
                )

        deleted_rows = self._delete_existing_industry_features(
            trade_date=actual_trade_date,
            feature_set_code=feature_set_code,
            feature_set_version=feature_set_version,
        )
        self._insert_feature_snapshot_rows(rows_to_insert)

        result.deleted_rows = deleted_rows
        result.inserted_rows = len(rows_to_insert)
        result.status = "SUCCESS" if result.inserted_rows > 0 and result.ready_rows > 0 else "PARTIAL"
        return result

    def _resolve_latest_trade_date_on_or_before(self, trade_date: date) -> date | None:
        value = self.session.execute(
            text(
                """
                select max(trade_date) as trade_date
                from core_daily_bar
                where price_adjust_type = 'RAW'
                  and trade_date <= :trade_date
                """
            ),
            {"trade_date": trade_date},
        ).scalar_one_or_none()
        return self._coerce_date_or_none(value)

    def _resolve_window_start_date(self, trade_date: date, window_size: int) -> date | None:
        value = self.session.execute(
            text(
                """
                with ranked_days as (
                    select distinct trade_date
                    from core_daily_bar
                    where price_adjust_type = 'RAW'
                      and trade_date <= :trade_date
                    order by trade_date desc
                    limit :required_rows
                )
                select case when count(*) = :required_rows then min(trade_date) else null end as window_start_date
                from ranked_days
                """
            ),
            {"trade_date": trade_date, "required_rows": int(window_size) + 1},
        ).scalar_one_or_none()
        return self._coerce_date_or_none(value)

    def _load_stock_industry_returns(
        self,
        *,
        trade_date: date,
        window_start_date: date,
        industry_tag_type: str,
    ) -> list[dict[str, Any]]:
        rows = self.session.execute(
            text(
                """
                select
                    c.instrument_id,
                    t.tag_code as industry_code,
                    t.tag_name as industry_name,
                    ((c.close / nullif(p.close, 0)) - 1) as stock_ret_20
                from core_daily_bar c
                join core_daily_bar p
                  on p.instrument_id = c.instrument_id
                 and p.trade_date = :window_start_date
                 and p.price_adjust_type = 'RAW'
                join instrument_tag it
                  on it.instrument_id = c.instrument_id
                 and it.effective_from <= :trade_date
                 and (it.effective_to is null or it.effective_to >= :trade_date)
                join tag t
                  on t.id = it.tag_id
                 and t.tag_type = :industry_tag_type
                 and t.is_active = true
                where c.trade_date = :trade_date
                  and c.price_adjust_type = 'RAW'
                  and c.close is not null
                  and p.close is not null
                  and c.close > 0
                  and p.close > 0
                """
            ),
            {
                "trade_date": trade_date,
                "window_start_date": window_start_date,
                "industry_tag_type": industry_tag_type,
            },
        ).mappings().all()
        return [dict(row) for row in rows]

    @staticmethod
    def _calc_industry_stats(stock_rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        grouped: dict[str, list[Decimal]] = {}
        for row in stock_rows:
            industry_code = str(row["industry_code"])
            value = _decimal(row.get("stock_ret_20"))
            if value is None:
                continue
            grouped.setdefault(industry_code, []).append(value)

        result: dict[str, dict[str, Any]] = {}
        for industry_code, values in grouped.items():
            if not values:
                continue
            industry_ret = sum(values) / Decimal(len(values))
            breadth = Decimal(sum(1 for value in values if value > 0)) / Decimal(len(values))
            result[industry_code] = {
                "industry_ret_20": industry_ret,
                "industry_breadth_20": breadth,
                "instrument_count": len(values),
            }
        return result

    def _insert_feature_snapshot_rows(self, rows: list[dict[str, Any]]) -> None:
        """Insert feature snapshot rows through SQLAlchemy Core text.

        The project may import the analytics feature model without importing all
        referenced meta/ops ORM models in the same metadata registry. ORM
        bulk_insert_mappings() can then try to sort unresolved foreign-key
        tables and raise NoReferencedTableError before issuing SQL. A Core text
        insert keeps the write path aligned with the existing table contract
        while avoiding ORM metadata dependency ordering.
        """

        if not rows:
            return
        self.session.execute(
            text(
                """
                insert into analytics_feature_snapshot (
                    trade_date,
                    instrument_id,
                    feature_code,
                    feature_set_code,
                    feature_set_version,
                    feature_value_numeric,
                    feature_value_text,
                    is_imputed,
                    impute_method,
                    scaling_applied,
                    sample_status,
                    run_id
                ) values (
                    :trade_date,
                    :instrument_id,
                    :feature_code,
                    :feature_set_code,
                    :feature_set_version,
                    :feature_value_numeric,
                    :feature_value_text,
                    :is_imputed,
                    :impute_method,
                    :scaling_applied,
                    :sample_status,
                    :run_id
                )
                """
            ),
            rows,
        )

    def _delete_existing_industry_features(
        self,
        *,
        trade_date: date,
        feature_set_code: str,
        feature_set_version: str,
    ) -> int:
        stmt = (
            delete(AnalyticsFeatureSnapshot)
            .where(AnalyticsFeatureSnapshot.trade_date == trade_date)
            .where(AnalyticsFeatureSnapshot.feature_set_code == feature_set_code)
            .where(AnalyticsFeatureSnapshot.feature_set_version == feature_set_version)
            .where(AnalyticsFeatureSnapshot.feature_code.in_(INDUSTRY_STRENGTH_FEATURE_CODES))
        )
        result = self.session.execute(stmt)
        return int(result.rowcount or 0)

    @staticmethod
    def _coerce_date(value: Any) -> date:
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value))

    @classmethod
    def _coerce_date_or_none(cls, value: Any) -> date | None:
        if value is None:
            return None
        return cls._coerce_date(value)
