from __future__ import annotations

import argparse
import csv
import json
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.orm import Session

# Explicit model imports keep SQLAlchemy metadata / FK dependency resolution stable.
import stock_quant_v2.db.models.meta.instrument  # noqa: F401
import stock_quant_v2.db.models.ops.run  # noqa: F401
import stock_quant_v2.db.models.analytics  # noqa: F401

from stock_quant_v2.analytics_domain.tasks.build_feature_snapshot import run as run_build_feature_snapshot
from stock_quant_v2.analytics_domain.tasks.compute_factor_snapshot import run as run_compute_factor_snapshot
from stock_quant_v2.analytics_domain.tasks.compute_indicator_snapshot import run as run_compute_indicator_snapshot
from stock_quant_v2.analytics_domain.tasks.seed_factor_definitions import run as run_seed_factor_definitions
from stock_quant_v2.analytics_domain.tasks.seed_feature_definitions import run as run_seed_feature_definitions
from stock_quant_v2.analytics_domain.tasks.seed_indicator_definitions import run as run_seed_indicator_definitions
from stock_quant_v2.data_domain.repositories.run_repository import RunRepository
from stock_quant_v2.db.session import SessionLocal

load_dotenv()

# M5 alpha_selection requires all of these features as ready numeric rows.
# Readiness must check code coverage, not just analytics_feature_snapshot row count,
# because partial historical builds may contain only feat_tradable_flag.
REQUIRED_M5_ALPHA_FEATURE_CODES = [
    "feat_mom_20",
    "feat_trend_strength_20",
    "feat_volatility_rank_20",
    "feat_tradability_score",
    "feat_tradable_flag",
]
FEATURE_SET_CODE_M5_ALPHA = "fs_daily_alpha_v1"
FEATURE_SET_VERSION_M5_ALPHA = "v1"


@dataclass(frozen=True)
class M3FeatureBackfillTarget:
    sequence_no: int
    trade_date: date
    target_type: str


@dataclass
class M3FeatureBackfillItemResult:
    sequence_no: int
    target_type: str
    trade_date: str
    status: str
    run_id: int | None = None
    existing_indicator_rows: int = 0
    existing_factor_rows: int = 0
    existing_feature_rows: int = 0
    indicator_inserted_rows: int | None = None
    factor_inserted_rows: int | None = None
    feature_inserted_rows: int | None = None
    final_indicator_rows: int | None = None
    final_factor_rows: int | None = None
    final_feature_rows: int | None = None
    ready_feature_code_count: int | None = None
    missing_feature_codes: list[str] | None = None
    instrument_count: int | None = None
    error_message: str | None = None


class M3HistoricalFeatureBackfillP1:
    """Build historical M3 indicator -> factor -> feature snapshots for M5.11 readiness.

    This P1 script intentionally reuses the existing M3 compute/build services.
    It does not alter schemas, M2 data, M4 strategy logic, M5.10 backtest logic,
    paper trading, risk, or M8 ops behavior.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self.run_repo = RunRepository()

    def run(
        self,
        *,
        start_date: date,
        end_date: date,
        frequency: str,
        include_initial: bool,
        allow_effective_after_end: bool,
        replace_existing: bool,
        dry_run: bool,
        min_feature_rows: int,
    ) -> dict[str, Any]:
        trading_dates = self._load_trading_dates(start_date=start_date, end_date=end_date)
        targets = self._build_signal_aligned_feature_targets(
            trading_dates=trading_dates,
            start_date=start_date,
            end_date=end_date,
            frequency=frequency,
            include_initial=include_initial,
            allow_effective_after_end=allow_effective_after_end,
        )

        item_results: list[M3FeatureBackfillItemResult] = []
        for target in targets:
            item_results.append(
                self._run_one_target(
                    target=target,
                    dry_run=dry_run,
                    replace_existing=replace_existing,
                    min_feature_rows=min_feature_rows,
                )
            )

        summary = self._build_summary(
            start_date=start_date,
            end_date=end_date,
            frequency=frequency,
            include_initial=include_initial,
            allow_effective_after_end=allow_effective_after_end,
            replace_existing=replace_existing,
            dry_run=dry_run,
            min_feature_rows=min_feature_rows,
            targets=targets,
            item_results=item_results,
        )
        summary["artifact_paths"] = self._write_artifacts(summary=summary, item_results=item_results)
        return summary

    def _run_one_target(
        self,
        *,
        target: M3FeatureBackfillTarget,
        dry_run: bool,
        replace_existing: bool,
        min_feature_rows: int,
    ) -> M3FeatureBackfillItemResult:
        before = self._snapshot_counts(target.trade_date)

        if dry_run:
            return M3FeatureBackfillItemResult(
                sequence_no=target.sequence_no,
                target_type=target.target_type,
                trade_date=target.trade_date.isoformat(),
                status="DRY_RUN",
                existing_indicator_rows=before["indicator_rows"],
                existing_factor_rows=before["factor_rows"],
                existing_feature_rows=before["feature_rows"],
                ready_feature_code_count=before["ready_feature_code_count"],
                missing_feature_codes=before["missing_feature_codes"],
                instrument_count=before["instrument_count"],
            )

        before_ready = (
            before["feature_rows"] >= min_feature_rows
            and before["ready_feature_code_count"] >= len(REQUIRED_M5_ALPHA_FEATURE_CODES)
            and not before["missing_feature_codes"]
        )

        if before_ready and not replace_existing:
            return M3FeatureBackfillItemResult(
                sequence_no=target.sequence_no,
                target_type=target.target_type,
                trade_date=target.trade_date.isoformat(),
                status="SKIPPED_EXISTING",
                existing_indicator_rows=before["indicator_rows"],
                existing_factor_rows=before["factor_rows"],
                existing_feature_rows=before["feature_rows"],
                final_indicator_rows=before["indicator_rows"],
                final_factor_rows=before["factor_rows"],
                final_feature_rows=before["feature_rows"],
                ready_feature_code_count=before["ready_feature_code_count"],
                missing_feature_codes=before["missing_feature_codes"],
                instrument_count=before["instrument_count"],
            )

        run = self.run_repo.create_run(
            session=self.session,
            run_type="DATA_SYNC",
            run_name="bootstrap_m3_historical_feature_backfill_p1",
            trigger_type="MANUAL",
            parent_run_id=None,
            context_json={
                "module": "M3",
                "stage": "M3_HISTORICAL_FEATURE_BACKFILL_P1",
                "trade_date": target.trade_date.isoformat(),
                "target_type": target.target_type,
                "sequence_no": target.sequence_no,
                "replace_existing": replace_existing,
                "scope": ["indicator", "factor", "feature"],
            },
        )
        self.run_repo.mark_run_running(session=self.session, run=run)
        self.session.commit()

        try:
            # Definition seeders are idempotent in the existing M3 chains.
            run_seed_indicator_definitions(session=self.session)
            run_seed_factor_definitions(session=self.session)
            run_seed_feature_definitions(session=self.session)
            self.session.commit()

            indicator_result = run_compute_indicator_snapshot(
                session=self.session,
                trade_date=target.trade_date,
                run_id=run.id,
                data_version_id=None,
            )
            factor_result = run_compute_factor_snapshot(
                session=self.session,
                trade_date=target.trade_date,
                run_id=run.id,
                data_version_id=None,
            )
            feature_result = run_build_feature_snapshot(
                session=self.session,
                trade_date=target.trade_date,
                run_id=run.id,
                data_version_id=None,
            )

            after = self._snapshot_counts(target.trade_date)
            missing_required = list(after["missing_feature_codes"])
            if after["feature_rows"] < min_feature_rows or missing_required:
                if missing_required:
                    message = (
                        "feature snapshot missing M5 alpha required ready feature codes: "
                        f"{missing_required}; feature_rows={after['feature_rows']}; "
                        "check indicator/factor inputs for this trade_date or run with --replace-existing after upstream data is ready"
                    )
                else:
                    message = (
                        f"feature_rows below threshold: {after['feature_rows']} < {min_feature_rows}; "
                        "check M2 daily bars / M3 factor inputs for this trade_date"
                    )
                self.run_repo.mark_run_finished(
                    session=self.session,
                    run=run,
                    status="FAILED",
                    error_message=message,
                )
                self.session.commit()
                return M3FeatureBackfillItemResult(
                    sequence_no=target.sequence_no,
                    target_type=target.target_type,
                    trade_date=target.trade_date.isoformat(),
                    status="FAILED",
                    run_id=run.id,
                    existing_indicator_rows=before["indicator_rows"],
                    existing_factor_rows=before["factor_rows"],
                    existing_feature_rows=before["feature_rows"],
                    indicator_inserted_rows=int(indicator_result.get("inserted_rows") or 0),
                    factor_inserted_rows=int(factor_result.get("inserted_rows") or 0),
                    feature_inserted_rows=int(feature_result.get("inserted_rows") or 0),
                    final_indicator_rows=after["indicator_rows"],
                    final_factor_rows=after["factor_rows"],
                    final_feature_rows=after["feature_rows"],
                    ready_feature_code_count=after["ready_feature_code_count"],
                    missing_feature_codes=after["missing_feature_codes"],
                    instrument_count=after["instrument_count"],
                    error_message=message,
                )

            self.run_repo.mark_run_finished(
                session=self.session,
                run=run,
                status="SUCCESS",
                error_message=None,
            )
            self.session.commit()
            return M3FeatureBackfillItemResult(
                sequence_no=target.sequence_no,
                target_type=target.target_type,
                trade_date=target.trade_date.isoformat(),
                status="SUCCESS",
                run_id=run.id,
                existing_indicator_rows=before["indicator_rows"],
                existing_factor_rows=before["factor_rows"],
                existing_feature_rows=before["feature_rows"],
                indicator_inserted_rows=int(indicator_result.get("inserted_rows") or 0),
                factor_inserted_rows=int(factor_result.get("inserted_rows") or 0),
                feature_inserted_rows=int(feature_result.get("inserted_rows") or 0),
                final_indicator_rows=after["indicator_rows"],
                final_factor_rows=after["factor_rows"],
                final_feature_rows=after["feature_rows"],
                ready_feature_code_count=after["ready_feature_code_count"],
                missing_feature_codes=after["missing_feature_codes"],
                instrument_count=after["instrument_count"],
            )

        except Exception as exc:  # noqa: BLE001
            self.session.rollback()
            try:
                self.run_repo.mark_run_finished(
                    session=self.session,
                    run=run,
                    status="FAILED",
                    error_message=str(exc),
                )
                self.session.commit()
            except Exception:
                self.session.rollback()
            return M3FeatureBackfillItemResult(
                sequence_no=target.sequence_no,
                target_type=target.target_type,
                trade_date=target.trade_date.isoformat(),
                status="FAILED",
                run_id=run.id,
                existing_indicator_rows=before["indicator_rows"],
                existing_factor_rows=before["factor_rows"],
                existing_feature_rows=before["feature_rows"],
                ready_feature_code_count=before["ready_feature_code_count"],
                missing_feature_codes=before["missing_feature_codes"],
                instrument_count=before["instrument_count"],
                error_message=str(exc),
            )

    def _snapshot_counts(self, trade_date: date) -> dict[str, Any]:
        sql = text(
            """
            WITH universe AS (
                SELECT COUNT(DISTINCT instrument_id) AS instrument_count
                FROM core_daily_bar
                WHERE trade_date = :trade_date
            ),
            indicator AS (
                SELECT COUNT(*) AS indicator_rows
                FROM analytics_instrument_indicator_snapshot
                WHERE trade_date = :trade_date
            ),
            factor AS (
                SELECT COUNT(*) AS factor_rows
                FROM analytics_instrument_factor_snapshot
                WHERE trade_date = :trade_date
            ),
            feature AS (
                SELECT COUNT(*) AS feature_rows
                FROM analytics_feature_snapshot
                WHERE trade_date = :trade_date
            )
            SELECT
                universe.instrument_count,
                indicator.indicator_rows,
                factor.factor_rows,
                feature.feature_rows
            FROM universe, indicator, factor, feature
            """
        )
        row = self.session.execute(sql, {"trade_date": trade_date}).mappings().first() or {}

        code_rows = self.session.execute(
            text(
                """
                SELECT
                    feature_code,
                    COUNT(*) AS total_rows,
                    COUNT(*) FILTER (
                        WHERE sample_status = 'ready'
                          AND feature_value_numeric IS NOT NULL
                    ) AS ready_rows
                FROM analytics_feature_snapshot
                WHERE trade_date = :trade_date
                  AND feature_set_code = :feature_set_code
                  AND feature_set_version = :feature_set_version
                  AND feature_code IN (
                    'feat_mom_20',
                    'feat_trend_strength_20',
                    'feat_volatility_rank_20',
                    'feat_tradability_score',
                    'feat_tradable_flag'
                  )
                GROUP BY feature_code
                """
            ),
            {
                "trade_date": trade_date,
                "feature_set_code": FEATURE_SET_CODE_M5_ALPHA,
                "feature_set_version": FEATURE_SET_VERSION_M5_ALPHA,
            },
        ).mappings().all()
        ready_by_code = {
            str(item["feature_code"]): int(item["ready_rows"] or 0)
            for item in code_rows
        }
        missing_feature_codes = [
            code for code in REQUIRED_M5_ALPHA_FEATURE_CODES
            if ready_by_code.get(code, 0) <= 0
        ]

        return {
            "instrument_count": int(row.get("instrument_count") or 0),
            "indicator_rows": int(row.get("indicator_rows") or 0),
            "factor_rows": int(row.get("factor_rows") or 0),
            "feature_rows": int(row.get("feature_rows") or 0),
            "ready_feature_code_count": len(REQUIRED_M5_ALPHA_FEATURE_CODES) - len(missing_feature_codes),
            "missing_feature_codes": missing_feature_codes,
        }

    def _load_trading_dates(self, *, start_date: date, end_date: date) -> list[date]:
        query_start = start_date - timedelta(days=45)
        query_end = end_date + timedelta(days=10)

        for table_name in ["core_trading_calendar", "trading_calendar", "meta_trading_calendar"]:
            if not self._table_exists(table_name):
                continue
            dates = self._load_dates_from_calendar_table(
                table_name=table_name,
                start_date=query_start,
                end_date=query_end,
            )
            if dates:
                return dates

        if self._table_exists("core_daily_bar"):
            rows = self.session.execute(
                text(
                    """
                    SELECT DISTINCT trade_date
                    FROM core_daily_bar
                    WHERE trade_date BETWEEN :start_date AND :end_date
                    ORDER BY trade_date
                    """
                ),
                {"start_date": query_start, "end_date": query_end},
            ).scalars().all()
            dates = [_coerce_date(value) for value in rows]
            return [value for value in dates if value is not None]

        raise RuntimeError("No trading calendar source found: core_trading_calendar/trading_calendar/meta_trading_calendar/core_daily_bar")

    def _load_dates_from_calendar_table(
        self,
        *,
        table_name: str,
        start_date: date,
        end_date: date,
    ) -> list[date]:
        columns = self._columns(table_name)
        date_col = _pick(columns, ["trade_date", "calendar_date", "date", "dt"], required=False)
        if not date_col:
            return []

        open_col = _pick(
            columns,
            ["is_trading_day", "is_trade_date", "is_open", "is_trade", "trading", "is_trading"],
            required=False,
        )
        where_parts = [f"{date_col} BETWEEN :start_date AND :end_date"]
        if open_col:
            # Schema tolerant across boolean / numeric / string-like flags.
            where_parts.append(
                f"lower(cast({open_col} as text)) in ('1','true','t','y','yes','open')"
            )

        market_col = _pick(columns, ["market", "market_code", "exchange_code", "exchange"], required=False)
        if market_col:
            where_parts.append(
                f"({market_col} is null or upper(cast({market_col} as text)) in ('CN_A','A_SHARE','ASHARE','SSE','SZSE','SH','SZ','ALL'))"
            )

        rows = self.session.execute(
            text(
                f"""
                SELECT DISTINCT {date_col} AS trade_date
                FROM {table_name}
                WHERE {" AND ".join(where_parts)}
                ORDER BY {date_col}
                """
            ),
            {"start_date": start_date, "end_date": end_date},
        ).scalars().all()
        return [value for value in (_coerce_date(row) for row in rows) if value is not None]

    @staticmethod
    def _build_signal_aligned_feature_targets(
        *,
        trading_dates: list[date],
        start_date: date,
        end_date: date,
        frequency: str,
        include_initial: bool,
        allow_effective_after_end: bool,
    ) -> list[M3FeatureBackfillTarget]:
        if frequency.upper() != "MONTHLY":
            raise ValueError("M3 Historical Feature Backfill P1 currently supports MONTHLY only")

        trading_dates = sorted(set(trading_dates))
        if not trading_dates:
            raise RuntimeError("No trading dates available for feature backfill")

        signal_as_of_dates: list[tuple[date, str]] = []

        if include_initial:
            previous_dates = [d for d in trading_dates if d < start_date]
            effective_candidates = [d for d in trading_dates if d >= start_date]
            if previous_dates and effective_candidates:
                signal_as_of_dates.append((previous_dates[-1], "INITIAL_PRE_WINDOW"))

        in_window = [d for d in trading_dates if start_date <= d <= end_date]
        by_month: dict[tuple[int, int], list[date]] = {}
        for d in in_window:
            by_month.setdefault((d.year, d.month), []).append(d)

        used_dates = {d for d, _ in signal_as_of_dates}
        for _, month_dates in sorted(by_month.items()):
            as_of = max(month_dates)
            later = [d for d in trading_dates if d > as_of]
            if not later:
                continue
            effective = later[0]
            if effective > end_date and not allow_effective_after_end:
                continue
            if as_of in used_dates:
                continue
            signal_as_of_dates.append((as_of, "MONTH_END"))
            used_dates.add(as_of)

        return [
            M3FeatureBackfillTarget(sequence_no=i + 1, trade_date=trade_date, target_type=target_type)
            for i, (trade_date, target_type) in enumerate(signal_as_of_dates)
        ]

    def _table_exists(self, table_name: str) -> bool:
        value = self.session.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = :table_name
                )
                """
            ),
            {"table_name": table_name},
        ).scalar()
        return bool(value)

    def _columns(self, table_name: str) -> set[str]:
        rows = self.session.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = :table_name
                """
            ),
            {"table_name": table_name},
        ).scalars().all()
        return {str(row) for row in rows}

    def _build_summary(
        self,
        *,
        start_date: date,
        end_date: date,
        frequency: str,
        include_initial: bool,
        allow_effective_after_end: bool,
        replace_existing: bool,
        dry_run: bool,
        min_feature_rows: int,
        targets: list[M3FeatureBackfillTarget],
        item_results: list[M3FeatureBackfillItemResult],
    ) -> dict[str, Any]:
        status_counts: dict[str, int] = {}
        for item in item_results:
            status_counts[item.status] = status_counts.get(item.status, 0) + 1

        success_count = status_counts.get("SUCCESS", 0)
        skipped_existing_count = status_counts.get("SKIPPED_EXISTING", 0)
        failed_count = status_counts.get("FAILED", 0)
        dry_run_count = status_counts.get("DRY_RUN", 0)
        ready_count = success_count + skipped_existing_count

        if dry_run:
            overall_status = "DRY_RUN"
        elif failed_count == 0 and ready_count == len(targets):
            overall_status = "SUCCESS"
        elif ready_count > 0:
            overall_status = "PARTIAL_SUCCESS"
        else:
            overall_status = "FAIL"

        feature_ready_dates = sorted(
            item.trade_date
            for item in item_results
            if item.status in {"SUCCESS", "SKIPPED_EXISTING"}
        )

        return {
            "stage": "M3_HISTORICAL_FEATURE_BACKFILL_P1",
            "overall_status": overall_status,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "frequency": frequency.upper(),
            "include_initial": include_initial,
            "allow_effective_after_end": allow_effective_after_end,
            "replace_existing": replace_existing,
            "dry_run": dry_run,
            "min_feature_rows": min_feature_rows,
            "target_count": len(targets),
            "success_count": success_count,
            "skipped_existing_count": skipped_existing_count,
            "failed_count": failed_count,
            "dry_run_count": dry_run_count,
            "ready_count": ready_count,
            "status_counts": status_counts,
            "feature_ready_date_count": len(feature_ready_dates),
            "min_feature_ready_date": feature_ready_dates[0] if feature_ready_dates else None,
            "max_feature_ready_date": feature_ready_dates[-1] if feature_ready_dates else None,
            "items": [asdict(item) for item in item_results],
            "notes": [
                "P1 builds M3 indicator, factor and feature snapshots for the monthly signal as_of_dates used by M4/M5 historical signal backfill.",
                "The script reuses existing M3 services and does not modify schemas or downstream M5/M6/M7/M8 behavior.",
                "SKIPPED_EXISTING means analytics_feature_snapshot already has all M5 alpha required ready feature codes for the target trade_date.",
                "If targets fail with zero instrument_count, check M2 core_daily_bar coverage for that trade_date.",
            ],
        }

    @staticmethod
    def _write_artifacts(
        *,
        summary: dict[str, Any],
        item_results: list[M3FeatureBackfillItemResult],
    ) -> dict[str, str]:
        report_date = summary["end_date"]
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = Path("artifacts") / "m3" / "historical_feature_backfill"
        out_dir.mkdir(parents=True, exist_ok=True)

        prefix = f"m3_historical_feature_backfill_p1_{report_date}_{stamp}"
        json_path = out_dir / f"{prefix}.json"
        md_path = out_dir / f"{prefix}.md"
        csv_path = out_dir / f"{prefix}_items.csv"

        json_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

        with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
            fieldnames = list(asdict(item_results[0]).keys()) if item_results else ["status"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for item in item_results:
                writer.writerow(asdict(item))

        md_path.write_text(_render_markdown(summary), encoding="utf-8")

        return {
            "json": str(json_path),
            "markdown": str(md_path),
            "items_csv": str(csv_path),
        }


def _render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# M3 Historical Feature Backfill P1",
        "",
        f"- overall_status: {summary['overall_status']}",
        f"- start_date: {summary['start_date']}",
        f"- end_date: {summary['end_date']}",
        f"- frequency: {summary['frequency']}",
        f"- target_count: {summary['target_count']}",
        f"- ready_count: {summary['ready_count']}",
        f"- success_count: {summary['success_count']}",
        f"- skipped_existing_count: {summary['skipped_existing_count']}",
        f"- failed_count: {summary['failed_count']}",
        "",
        "## Items",
        "",
        "| # | Type | Trade Date | Status | Run ID | Instruments | Indicator Rows | Factor Rows | Feature Rows | Missing Features | Error |",
        "|---:|---|---|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for item in summary.get("items", []):
        error = str(item.get("error_message") or "").replace("|", "/")[:160]
        missing = ",".join(item.get("missing_feature_codes") or []).replace("|", "/")[:120]
        lines.append(
            "| {sequence_no} | {target_type} | {trade_date} | {status} | {run_id} | {instrument_count} | {final_indicator_rows} | {final_factor_rows} | {final_feature_rows} | {missing} | {error} |".format(
                sequence_no=item.get("sequence_no"),
                target_type=item.get("target_type"),
                trade_date=item.get("trade_date"),
                status=item.get("status"),
                run_id=item.get("run_id") or "",
                instrument_count=item.get("instrument_count") if item.get("instrument_count") is not None else "",
                final_indicator_rows=item.get("final_indicator_rows") if item.get("final_indicator_rows") is not None else item.get("existing_indicator_rows", ""),
                final_factor_rows=item.get("final_factor_rows") if item.get("final_factor_rows") is not None else item.get("existing_factor_rows", ""),
                final_feature_rows=item.get("final_feature_rows") if item.get("final_feature_rows") is not None else item.get("existing_feature_rows", ""),
                missing=missing,
                error=error,
            )
        )
    lines.append("")
    lines.append("## Notes")
    for note in summary.get("notes", []):
        lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)


def _coerce_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value)[:10])


def _pick(columns: set[str], candidates: Iterable[str], *, required: bool) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    if required:
        raise RuntimeError("none of candidate columns exists: " + ", ".join(candidates))
    return None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="M3 Historical Feature Backfill P1: build indicator/factor/feature snapshots for M5 historical signal backfill."
    )
    parser.add_argument("--start-date", default=os.getenv("M3_HIST_FEATURE_START_DATE", "2024-04-01"))
    parser.add_argument("--end-date", default=os.getenv("M3_HIST_FEATURE_END_DATE", "2026-04-24"))
    parser.add_argument("--frequency", default=os.getenv("M3_HIST_FEATURE_FREQUENCY", "MONTHLY"))
    parser.add_argument("--min-feature-rows", type=int, default=int(os.getenv("M3_HIST_FEATURE_MIN_ROWS", "1")))
    parser.add_argument("--replace-existing", action="store_true", help="Rebuild target dates even if feature rows already exist.")
    parser.add_argument("--dry-run", action="store_true", help="Plan target dates and write artifacts without computing snapshots.")
    parser.add_argument("--no-initial", action="store_true", help="Do not add previous-trading-day initial feature target.")
    parser.add_argument("--allow-effective-after-end", action="store_true", help="Include last month-end as_of_date even when next effective date exceeds end date.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    start_date = date.fromisoformat(args.start_date)
    end_date = date.fromisoformat(args.end_date)
    if end_date < start_date:
        raise ValueError("--end-date must be >= --start-date")

    with SessionLocal() as session:
        summary = M3HistoricalFeatureBackfillP1(session).run(
            start_date=start_date,
            end_date=end_date,
            frequency=args.frequency,
            include_initial=not args.no_initial,
            allow_effective_after_end=bool(args.allow_effective_after_end),
            replace_existing=bool(args.replace_existing),
            dry_run=bool(args.dry_run),
            min_feature_rows=int(args.min_feature_rows),
        )

    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0 if summary["overall_status"] in {"SUCCESS", "PARTIAL_SUCCESS", "DRY_RUN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
