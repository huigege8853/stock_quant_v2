from __future__ import annotations

import argparse
import csv
import json
import os
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

# Explicit model imports keep SQLAlchemy metadata / FK dependency resolution stable
# when StrategySignal ORM rows are flushed from this standalone backfill script.
import stock_quant_v2.db.models.meta.instrument  # noqa: F401
import stock_quant_v2.db.models.ops.run  # noqa: F401
import stock_quant_v2.db.models.strategy.strategy_definition  # noqa: F401
import stock_quant_v2.db.models.strategy.strategy_signal  # noqa: F401
import stock_quant_v2.db.models.strategy.strategy_version  # noqa: F401

from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.research_domain.repositories.ops_run_repository import OpsRunRepository
from stock_quant_v2.research_domain.services.signal_resolver_service import SignalResolverService
from stock_quant_v2.strategy_domain.constants import (
    DEFAULT_PARAMETER_VALUES_ALPHA_SELECTION,
    STRATEGY_CODE_ALPHA_SELECTION,
    STRATEGY_VERSION_CODE_V1,
)
from stock_quant_v2.strategy_domain.tasks.build_strategy_signal import build_alpha_selection_signal


@dataclass(frozen=True)
class BackfillTarget:
    sequence_no: int
    as_of_date: date
    effective_date: date
    target_type: str


@dataclass
class BackfillItemResult:
    sequence_no: int
    target_type: str
    as_of_date: str
    effective_date: str
    status: str
    run_id: int | None = None
    selected_count: int | None = None
    eligible_universe_size: int | None = None
    score_min: float | None = None
    score_max: float | None = None
    score_avg: float | None = None
    existing_run_ids: list[int] | None = None
    existing_signal_rows: int | None = None
    error_message: str | None = None


class HistoricalSignalBackfillP1:
    """M4/M5 monthly historical signal backfill.

    P1 deliberately reuses the existing M4 alpha_selection signal builder instead of
    duplicating strategy logic. It creates a set of historical as_of/effective_date
    pairs, then runs the same alpha-selection signal generation used by the current
    M5 screen chain.
    """

    def __init__(self, session: Session):
        self.session = session
        self.ops_runs = OpsRunRepository(session)
        self.signal_resolver = SignalResolverService(session)

    def run(
        self,
        *,
        start_date: date,
        end_date: date,
        frequency: str,
        top_n: int,
        min_score: float,
        strategy_code: str,
        version_code: str,
        include_initial: bool,
        replace_existing: bool,
        dry_run: bool,
        allow_effective_after_end: bool,
    ) -> dict[str, Any]:
        strategy_version_id = self.signal_resolver.resolve_strategy_version_id(
            strategy_code=strategy_code,
            version_code=version_code,
        )

        trading_dates = self._load_trading_dates(start_date=start_date, end_date=end_date)
        targets = self._build_targets(
            trading_dates=trading_dates,
            start_date=start_date,
            end_date=end_date,
            frequency=frequency,
            include_initial=include_initial,
            allow_effective_after_end=allow_effective_after_end,
        )

        runtime_params = deepcopy(DEFAULT_PARAMETER_VALUES_ALPHA_SELECTION)
        runtime_params["top_n"] = int(top_n)
        runtime_params["min_score"] = float(min_score)

        item_results: list[BackfillItemResult] = []
        for target in targets:
            item_results.append(
                self._run_one_target(
                    target=target,
                    strategy_version_id=strategy_version_id,
                    runtime_params=runtime_params,
                    replace_existing=replace_existing,
                    dry_run=dry_run,
                )
            )

        summary = self._build_summary(
            start_date=start_date,
            end_date=end_date,
            frequency=frequency,
            strategy_code=strategy_code,
            version_code=version_code,
            strategy_version_id=strategy_version_id,
            top_n=top_n,
            min_score=min_score,
            include_initial=include_initial,
            replace_existing=replace_existing,
            dry_run=dry_run,
            targets=targets,
            item_results=item_results,
        )
        artifact_paths = self._write_artifacts(summary=summary, item_results=item_results)
        summary["artifact_paths"] = artifact_paths
        return summary

    def _run_one_target(
        self,
        *,
        target: BackfillTarget,
        strategy_version_id: int,
        runtime_params: dict[str, Any],
        replace_existing: bool,
        dry_run: bool,
    ) -> BackfillItemResult:
        existing = self._find_existing_signal_runs(
            strategy_version_id=strategy_version_id,
            as_of_date=target.as_of_date,
            effective_date=target.effective_date,
        )

        if existing["signal_rows"] > 0 and not replace_existing:
            return BackfillItemResult(
                sequence_no=target.sequence_no,
                target_type=target.target_type,
                as_of_date=str(target.as_of_date),
                effective_date=str(target.effective_date),
                status="SKIPPED_EXISTING",
                existing_run_ids=existing["run_ids"],
                existing_signal_rows=existing["signal_rows"],
            )

        if dry_run:
            return BackfillItemResult(
                sequence_no=target.sequence_no,
                target_type=target.target_type,
                as_of_date=str(target.as_of_date),
                effective_date=str(target.effective_date),
                status="DRY_RUN",
                existing_run_ids=existing["run_ids"],
                existing_signal_rows=existing["signal_rows"],
            )

        run_payload = {
            "stage": "M4_M5_HISTORICAL_SIGNAL_BACKFILL_P1",
            "strategy_version_id": strategy_version_id,
            "as_of_date": str(target.as_of_date),
            "effective_date": str(target.effective_date),
            "target_type": target.target_type,
            "runtime_params": runtime_params,
            "replace_existing": replace_existing,
        }

        run_id = self.ops_runs.create_run(
            run_type="strategy_signal_backfill",
            run_name="M4/M5 Historical Signal Backfill P1",
            payload=run_payload,
        )
        # Preserve a failed run marker if the later signal build fails.
        self.session.commit()

        try:
            if existing["signal_rows"] > 0 and replace_existing:
                self._delete_existing_signals(
                    strategy_version_id=strategy_version_id,
                    as_of_date=target.as_of_date,
                    effective_date=target.effective_date,
                )
                self.session.commit()

            result = build_alpha_selection_signal(
                self.session,
                run_id=run_id,
                strategy_version_id=strategy_version_id,
                as_of_date=target.as_of_date,
                effective_date=target.effective_date,
                runtime_params=runtime_params,
            )
            self.ops_runs.mark_success(run_id)
            self.session.commit()

            return BackfillItemResult(
                sequence_no=target.sequence_no,
                target_type=target.target_type,
                as_of_date=str(target.as_of_date),
                effective_date=str(target.effective_date),
                status="SUCCESS",
                run_id=run_id,
                selected_count=int(result.get("selected_count") or 0),
                eligible_universe_size=int(result.get("eligible_universe_size") or 0),
                score_min=_as_float(result.get("score_min")),
                score_max=_as_float(result.get("score_max")),
                score_avg=_as_float(result.get("score_avg")),
                existing_run_ids=existing["run_ids"],
                existing_signal_rows=existing["signal_rows"],
            )

        except Exception as exc:
            self.session.rollback()
            self.ops_runs.mark_failed(run_id, str(exc))
            self.session.commit()
            return BackfillItemResult(
                sequence_no=target.sequence_no,
                target_type=target.target_type,
                as_of_date=str(target.as_of_date),
                effective_date=str(target.effective_date),
                status="FAILED",
                run_id=run_id,
                existing_run_ids=existing["run_ids"],
                existing_signal_rows=existing["signal_rows"],
                error_message=str(exc),
            )

    def _load_trading_dates(self, *, start_date: date, end_date: date) -> list[date]:
        # Need lookback for the initial as_of_date and lookahead for next effective_date.
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

        # Fallback: infer trading dates from core_daily_bar. This is good enough for
        # backfill targeting because signals require feature snapshots built from bars.
        if self._table_exists("core_daily_bar"):
            rows = self.session.execute(
                text(
                    """
                    select distinct trade_date
                    from core_daily_bar
                    where trade_date between :start_date and :end_date
                    order by trade_date
                    """
                ),
                {"start_date": query_start, "end_date": query_end},
            ).scalars().all()
            dates = [_coerce_date(value) for value in rows]
            return [value for value in dates if value is not None]

        raise RuntimeError("No trading calendar source found: core_trading_calendar/core_daily_bar missing")

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
        where_parts = [f"{date_col} between :start_date and :end_date"]
        if open_col:
            # Keep this schema-tolerant across boolean, integer-like and text flags.
            # PostgreSQL does not allow boolean = integer, so use text casting only.
            where_parts.append(
                f"lower(cast({open_col} as text)) in ('1','true','t','y','yes','open')"
            )

        market_col = _pick(columns, ["market", "market_code", "exchange_code", "exchange"], required=False)
        params: dict[str, Any] = {"start_date": start_date, "end_date": end_date}
        if market_col:
            where_parts.append(
                f"({market_col} is null or upper(cast({market_col} as text)) in ('CN_A','A_SHARE','ASHARE','SSE','SZSE','SH','SZ','ALL'))"
            )

        rows = self.session.execute(
            text(
                f"""
                select distinct {date_col} as trade_date
                from {table_name}
                where {" and ".join(where_parts)}
                order by {date_col}
                """
            ),
            params,
        ).scalars().all()
        return [value for value in (_coerce_date(row) for row in rows) if value is not None]

    @staticmethod
    def _build_targets(
        *,
        trading_dates: list[date],
        start_date: date,
        end_date: date,
        frequency: str,
        include_initial: bool,
        allow_effective_after_end: bool,
    ) -> list[BackfillTarget]:
        if frequency.upper() != "MONTHLY":
            raise ValueError("M4/M5 Historical Signal Backfill P1 currently supports MONTHLY only")

        trading_dates = sorted(set(trading_dates))
        if not trading_dates:
            raise RuntimeError("No trading dates available for backfill")

        targets: list[BackfillTarget] = []

        if include_initial:
            previous_dates = [d for d in trading_dates if d < start_date]
            effective_candidates = [d for d in trading_dates if d >= start_date]
            if previous_dates and effective_candidates:
                targets.append(
                    BackfillTarget(
                        sequence_no=1,
                        as_of_date=previous_dates[-1],
                        effective_date=effective_candidates[0],
                        target_type="INITIAL_PRE_WINDOW",
                    )
                )

        in_window = [d for d in trading_dates if start_date <= d <= end_date]
        by_month: dict[tuple[int, int], list[date]] = {}
        for d in in_window:
            by_month.setdefault((d.year, d.month), []).append(d)

        used_pairs = {(t.as_of_date, t.effective_date) for t in targets}
        for _, month_dates in sorted(by_month.items()):
            as_of = max(month_dates)
            later = [d for d in trading_dates if d > as_of]
            if not later:
                continue
            effective = later[0]
            if effective > end_date and not allow_effective_after_end:
                continue
            if (as_of, effective) in used_pairs:
                continue
            targets.append(
                BackfillTarget(
                    sequence_no=len(targets) + 1,
                    as_of_date=as_of,
                    effective_date=effective,
                    target_type="MONTH_END",
                )
            )
            used_pairs.add((as_of, effective))

        return [
            BackfillTarget(
                sequence_no=i + 1,
                as_of_date=t.as_of_date,
                effective_date=t.effective_date,
                target_type=t.target_type,
            )
            for i, t in enumerate(targets)
        ]

    def _find_existing_signal_runs(
        self,
        *,
        strategy_version_id: int,
        as_of_date: date,
        effective_date: date,
    ) -> dict[str, Any]:
        rows = self.session.execute(
            text(
                """
                select run_id, count(*) as signal_rows
                from strategy_signal
                where strategy_version_id = :strategy_version_id
                  and as_of_date = :as_of_date
                  and effective_date = :effective_date
                group by run_id
                order by run_id
                """
            ),
            {
                "strategy_version_id": strategy_version_id,
                "as_of_date": as_of_date,
                "effective_date": effective_date,
            },
        ).mappings().all()
        return {
            "run_ids": [int(row["run_id"]) for row in rows],
            "signal_rows": int(sum(int(row["signal_rows"]) for row in rows)),
        }

    def _delete_existing_signals(
        self,
        *,
        strategy_version_id: int,
        as_of_date: date,
        effective_date: date,
    ) -> int:
        result = self.session.execute(
            text(
                """
                delete from strategy_signal
                where strategy_version_id = :strategy_version_id
                  and as_of_date = :as_of_date
                  and effective_date = :effective_date
                """
            ),
            {
                "strategy_version_id": strategy_version_id,
                "as_of_date": as_of_date,
                "effective_date": effective_date,
            },
        )
        return int(result.rowcount or 0)

    def _table_exists(self, table_name: str) -> bool:
        return bool(
            self.session.execute(
                text(
                    """
                    select 1
                    from information_schema.tables
                    where table_schema = 'public'
                      and table_name = :table_name
                    limit 1
                    """
                ),
                {"table_name": table_name},
            ).first()
        )

    def _columns(self, table_name: str) -> set[str]:
        rows = self.session.execute(
            text(
                """
                select column_name
                from information_schema.columns
                where table_schema = 'public'
                  and table_name = :table_name
                """
            ),
            {"table_name": table_name},
        ).scalars().all()
        return set(rows)

    @staticmethod
    def _build_summary(
        *,
        start_date: date,
        end_date: date,
        frequency: str,
        strategy_code: str,
        version_code: str,
        strategy_version_id: int,
        top_n: int,
        min_score: float,
        include_initial: bool,
        replace_existing: bool,
        dry_run: bool,
        targets: list[BackfillTarget],
        item_results: list[BackfillItemResult],
    ) -> dict[str, Any]:
        status_counts: dict[str, int] = {}
        for item in item_results:
            status_counts[item.status] = status_counts.get(item.status, 0) + 1

        success_count = status_counts.get("SUCCESS", 0)
        failed_count = status_counts.get("FAILED", 0)
        skipped_existing_count = status_counts.get("SKIPPED_EXISTING", 0)
        dry_run_count = status_counts.get("DRY_RUN", 0)

        if failed_count > 0 and success_count == 0:
            overall_status = "FAIL"
        elif failed_count > 0:
            overall_status = "PASS_WITH_WARN"
        elif dry_run:
            overall_status = "DRY_RUN"
        else:
            overall_status = "PASS"

        generated_effective_dates = sorted(
            {
                item.effective_date
                for item in item_results
                if item.status in {"SUCCESS", "SKIPPED_EXISTING", "DRY_RUN"}
            }
        )

        return {
            "stage": "M4_M5_HISTORICAL_SIGNAL_BACKFILL_P1",
            "overall_status": overall_status,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "start_date": str(start_date),
            "end_date": str(end_date),
            "frequency": frequency.upper(),
            "strategy_code": strategy_code,
            "version_code": version_code,
            "strategy_version_id": strategy_version_id,
            "top_n": int(top_n),
            "min_score": float(min_score),
            "include_initial": include_initial,
            "replace_existing": replace_existing,
            "dry_run": dry_run,
            "target_count": len(targets),
            "success_count": success_count,
            "failed_count": failed_count,
            "skipped_existing_count": skipped_existing_count,
            "dry_run_count": dry_run_count,
            "status_counts": status_counts,
            "effective_date_count_after_run_window": len(generated_effective_dates),
            "min_effective_date_in_targets": generated_effective_dates[0] if generated_effective_dates else None,
            "max_effective_date_in_targets": generated_effective_dates[-1] if generated_effective_dates else None,
            "items": [asdict(item) for item in item_results],
            "notes": [
                "P1 uses monthly rebalance targets plus optional initial pre-window target.",
                "Signal generation reuses existing M4 alpha_selection logic and feature snapshots.",
                "SKIPPED_EXISTING means signal rows already existed for the same strategy/as_of/effective date.",
                "If many targets fail with missing feature rows, run historical M3 feature snapshot backfill first.",
            ],
        }

    @staticmethod
    def _write_artifacts(
        *,
        summary: dict[str, Any],
        item_results: list[BackfillItemResult],
    ) -> dict[str, str]:
        report_date = summary["end_date"]
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = Path("artifacts") / "m5" / "historical_signal_backfill"
        out_dir.mkdir(parents=True, exist_ok=True)

        prefix = f"m5_historical_signal_backfill_p1_{report_date}_{stamp}"
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
                row = asdict(item)
                row["existing_run_ids"] = ",".join(str(x) for x in (item.existing_run_ids or []))
                writer.writerow(row)

        md_path.write_text(_render_markdown(summary), encoding="utf-8")

        return {
            "json": str(json_path),
            "markdown": str(md_path),
            "items_csv": str(csv_path),
        }


def _render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# M4/M5 Historical Signal Backfill P1",
        "",
        f"- overall_status: {summary['overall_status']}",
        f"- start_date: {summary['start_date']}",
        f"- end_date: {summary['end_date']}",
        f"- frequency: {summary['frequency']}",
        f"- strategy: {summary['strategy_code']}:{summary['version_code']}",
        f"- strategy_version_id: {summary['strategy_version_id']}",
        f"- top_n: {summary['top_n']}",
        f"- min_score: {summary['min_score']}",
        f"- target_count: {summary['target_count']}",
        f"- success_count: {summary['success_count']}",
        f"- skipped_existing_count: {summary['skipped_existing_count']}",
        f"- failed_count: {summary['failed_count']}",
        "",
        "## Items",
        "",
        "| # | Type | As Of | Effective | Status | Run ID | Selected | Error |",
        "|---:|---|---|---|---|---:|---:|---|",
    ]
    for item in summary.get("items", []):
        error = str(item.get("error_message") or "").replace("|", "/")[:160]
        lines.append(
            "| {sequence_no} | {target_type} | {as_of_date} | {effective_date} | {status} | {run_id} | {selected_count} | {error} |".format(
                sequence_no=item.get("sequence_no"),
                target_type=item.get("target_type"),
                as_of_date=item.get("as_of_date"),
                effective_date=item.get("effective_date"),
                status=item.get("status"),
                run_id=item.get("run_id") or "",
                selected_count=item.get("selected_count") or "",
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


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="M4/M5 Historical Signal Backfill P1: monthly alpha_selection signal generation."
    )
    parser.add_argument("--start-date", default=os.getenv("M5_HIST_SIGNAL_START_DATE", "2024-04-01"))
    parser.add_argument("--end-date", default=os.getenv("M5_HIST_SIGNAL_END_DATE", "2026-04-24"))
    parser.add_argument("--frequency", default=os.getenv("M5_HIST_SIGNAL_FREQUENCY", "MONTHLY"))
    parser.add_argument("--top-n", type=int, default=int(os.getenv("M5_HIST_SIGNAL_TOP_N", "30")))
    parser.add_argument("--min-score", type=float, default=float(os.getenv("M5_HIST_SIGNAL_MIN_SCORE", "0.60")))
    parser.add_argument("--strategy-code", default=os.getenv("M5_HIST_SIGNAL_STRATEGY_CODE", STRATEGY_CODE_ALPHA_SELECTION))
    parser.add_argument("--version-code", default=os.getenv("M5_HIST_SIGNAL_VERSION_CODE", STRATEGY_VERSION_CODE_V1))
    parser.add_argument("--replace-existing", action="store_true", help="Delete and rebuild rows for existing as_of/effective dates.")
    parser.add_argument("--dry-run", action="store_true", help="Plan targets and write artifacts without writing strategy_signal rows.")
    parser.add_argument("--no-initial", action="store_true", help="Do not add previous-trading-day -> first-trading-day initial target.")
    parser.add_argument("--allow-effective-after-end", action="store_true", help="Allow the last target effective_date to exceed end_date.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    start_date = date.fromisoformat(args.start_date)
    end_date = date.fromisoformat(args.end_date)
    if end_date < start_date:
        raise ValueError("--end-date must be >= --start-date")

    with SessionLocal() as session:
        summary = HistoricalSignalBackfillP1(session).run(
            start_date=start_date,
            end_date=end_date,
            frequency=args.frequency,
            top_n=args.top_n,
            min_score=args.min_score,
            strategy_code=args.strategy_code,
            version_code=args.version_code,
            include_initial=not args.no_initial,
            replace_existing=bool(args.replace_existing),
            dry_run=bool(args.dry_run),
            allow_effective_after_end=bool(args.allow_effective_after_end),
        )

    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0 if summary["overall_status"] in {"PASS", "PASS_WITH_WARN", "DRY_RUN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
