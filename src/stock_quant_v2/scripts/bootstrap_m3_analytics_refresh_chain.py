from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import create_engine, text

from stock_quant_v2.config.settings import settings


CHECKPOINT_PATH = Path("tmp/m3_analytics_refresh_checkpoint.json")
DEFAULT_MODE = "latest"
DEFAULT_CHUNK_DAYS = 20
DEFAULT_LABEL_TAIL_REFRESH_DAYS = 10
M3_SKIP_SEED_ENV = {"M3_SKIP_SEED": "true"}


@dataclass(frozen=True)
class M3Topic:
    name: str
    module_name: str
    env_date_name: str
    table_name: str
    date_column: str
    kind: str  # trade_date | anchor_date


M3_TOPICS: list[M3Topic] = [
    M3Topic(
        name="indicator",
        module_name="stock_quant_v2.scripts.bootstrap_m3_indicator_chain",
        env_date_name="M3_INDICATOR_TRADE_DATE",
        table_name="analytics_instrument_indicator_snapshot",
        date_column="trade_date",
        kind="trade_date",
    ),
    M3Topic(
        name="factor",
        module_name="stock_quant_v2.scripts.bootstrap_m3_factor_chain",
        env_date_name="M3_FACTOR_TRADE_DATE",
        table_name="analytics_instrument_factor_snapshot",
        date_column="trade_date",
        kind="trade_date",
    ),
    M3Topic(
        name="feature",
        module_name="stock_quant_v2.scripts.bootstrap_m3_feature_chain",
        env_date_name="M3_FEATURE_TRADE_DATE",
        table_name="analytics_feature_snapshot",
        date_column="trade_date",
        kind="trade_date",
    ),
    M3Topic(
        name="label",
        module_name="stock_quant_v2.scripts.bootstrap_m3_label_chain",
        env_date_name="M3_LABEL_ANCHOR_DATE",
        table_name="analytics_label_snapshot",
        date_column="anchor_date",
        kind="anchor_date",
    ),
]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _normalize_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _should_skip_seed() -> bool:
    return _normalize_bool(os.getenv("M3_SKIP_SEED"), default=False)


def _run_module(module_name: str, extra_env: dict[str, str] | None = None) -> int:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    cmd = [sys.executable, "-m", module_name]
    completed = subprocess.run(cmd, cwd=_project_root(), env=env)
    return int(completed.returncode)


class DatabaseInspector:
    def __init__(self, db_url: str) -> None:
        self.engine = create_engine(db_url)

    def close(self) -> None:
        self.engine.dispose()

    def latest_trade_date(self) -> date | None:
        value = self._safe_scalar(
            """
            SELECT MAX(trade_date)
            FROM core_daily_bar
            WHERE price_adjust_type = 'RAW'
            """
        )
        return self._coerce_to_date(value)

    def first_trade_date(self) -> date | None:
        value = self._safe_scalar(
            """
            SELECT MIN(trade_date)
            FROM core_daily_bar
            WHERE price_adjust_type = 'RAW'
            """
        )
        return self._coerce_to_date(value)

    def max_date(self, table_name: str, date_column: str) -> date | None:
        value = self._safe_scalar(f"SELECT MAX({date_column}) FROM {table_name}")
        return self._coerce_to_date(value)

    def row_count_for_date(self, table_name: str, date_column: str, target_date: date) -> int:
        sql = text(f"SELECT COUNT(*) FROM {table_name} WHERE {date_column} = :target_date")
        try:
            with self.engine.connect() as conn:
                value = conn.execute(sql, {"target_date": target_date}).scalar()
            return int(value or 0)
        except Exception:
            return 0

    def list_trade_dates(self, start_date: date, end_date: date) -> list[date]:
        sql = text(
            """
            SELECT DISTINCT trade_date
            FROM core_daily_bar
            WHERE price_adjust_type = 'RAW'
              AND trade_date BETWEEN :start_date AND :end_date
            ORDER BY trade_date ASC
            """
        )
        with self.engine.connect() as conn:
            rows = conn.execute(sql, {"start_date": start_date, "end_date": end_date}).scalars().all()
        return [d for d in (self._coerce_to_date(row) for row in rows) if d is not None]

    def list_trade_dates_after(self, after_date: date | None, end_date: date) -> list[date]:
        if after_date is None:
            return [end_date]
        sql = text(
            """
            SELECT DISTINCT trade_date
            FROM core_daily_bar
            WHERE price_adjust_type = 'RAW'
              AND trade_date > :after_date
              AND trade_date <= :end_date
            ORDER BY trade_date ASC
            """
        )
        with self.engine.connect() as conn:
            rows = conn.execute(sql, {"after_date": after_date, "end_date": end_date}).scalars().all()
        return [d for d in (self._coerce_to_date(row) for row in rows) if d is not None]

    def list_tail_trade_dates(self, end_date: date, limit: int) -> list[date]:
        if limit <= 0:
            return []
        sql = text(
            """
            SELECT trade_date
            FROM (
                SELECT DISTINCT trade_date
                FROM core_daily_bar
                WHERE price_adjust_type = 'RAW'
                  AND trade_date <= :end_date
                ORDER BY trade_date DESC
                LIMIT :limit
            ) d
            ORDER BY trade_date ASC
            """
        )
        with self.engine.connect() as conn:
            rows = conn.execute(sql, {"end_date": end_date, "limit": limit}).scalars().all()
        return [d for d in (self._coerce_to_date(row) for row in rows) if d is not None]

    def resolve_label_tail_refresh_days(self) -> int:
        env_value = os.getenv("M3_LABEL_TAIL_REFRESH_DAYS")
        if env_value:
            try:
                return max(1, int(env_value))
            except ValueError:
                pass

        # Try to infer horizon from meta_label_definition if a horizon-like column exists.
        # Keep this defensive: older M3 schemas may not have these columns yet.
        for column_name in ("horizon_days", "horizon_bars", "lookahead_days", "lookahead_bars"):
            if not self.column_exists("meta_label_definition", column_name):
                continue
            value = self._safe_scalar(f"SELECT MAX({column_name}) FROM meta_label_definition")
            try:
                if value is not None and int(value) > 0:
                    return int(value)
            except (TypeError, ValueError):
                continue
        return DEFAULT_LABEL_TAIL_REFRESH_DAYS

    def column_exists(self, table_name: str, column_name: str) -> bool:
        sql = text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name
              AND column_name = :column_name
            LIMIT 1
            """
        )
        try:
            with self.engine.connect() as conn:
                value = conn.execute(sql, {"table_name": table_name, "column_name": column_name}).scalar()
            return value is not None
        except Exception:
            return False

    def _safe_scalar(self, sql: str) -> Any | None:
        try:
            with self.engine.connect() as conn:
                return conn.execute(text(sql)).scalar()
        except Exception:
            return None

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


def _seed_definitions_once() -> None:
    from stock_quant_v2.analytics_domain.tasks.seed_factor_definitions import run as run_seed_factor_definitions
    from stock_quant_v2.analytics_domain.tasks.seed_feature_definitions import run as run_seed_feature_definitions
    from stock_quant_v2.analytics_domain.tasks.seed_indicator_definitions import run as run_seed_indicator_definitions
    from stock_quant_v2.analytics_domain.tasks.seed_label_definitions import run as run_seed_label_definitions
    from stock_quant_v2.db.session import SessionLocal

    with SessionLocal() as session:
        run_seed_indicator_definitions(session=session)
        run_seed_factor_definitions(session=session)
        run_seed_feature_definitions(session=session)
        run_seed_label_definitions(session=session)
        session.commit()


def _build_topic_env(topic: M3Topic, target_date: date) -> dict[str, str]:
    return {**M3_SKIP_SEED_ENV, topic.env_date_name: target_date.isoformat()}


def _ensure_checkpoint_dir() -> None:
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)


def _load_checkpoint() -> dict[str, Any] | None:
    if not CHECKPOINT_PATH.exists():
        return None
    try:
        return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_checkpoint(payload: dict[str, Any]) -> None:
    _ensure_checkpoint_dir()
    CHECKPOINT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _clear_checkpoint() -> None:
    if CHECKPOINT_PATH.exists():
        CHECKPOINT_PATH.unlink()


def _select_topics(indicator_only: bool, factor_only: bool, feature_only: bool, label_only: bool) -> list[M3Topic]:
    flags = [indicator_only, factor_only, feature_only, label_only]
    if not any(flags):
        return list(M3_TOPICS)

    selected_topics: list[M3Topic] = []
    if indicator_only:
        selected_topics.append(next(t for t in M3_TOPICS if t.name == "indicator"))
    if factor_only:
        selected_topics.append(next(t for t in M3_TOPICS if t.name == "factor"))
    if feature_only:
        selected_topics.append(next(t for t in M3_TOPICS if t.name == "feature"))
    if label_only:
        selected_topics.append(next(t for t in M3_TOPICS if t.name == "label"))
    return selected_topics


def _filter_missing_dates(inspector: DatabaseInspector, topic: M3Topic, dates: Iterable[date]) -> list[date]:
    return [
        target_date
        for target_date in dates
        if inspector.row_count_for_date(topic.table_name, topic.date_column, target_date) == 0
    ]


def _apply_resume_filter(topic: M3Topic, dates: list[date], resume_enabled: bool) -> list[date]:
    checkpoint = _load_checkpoint() if resume_enabled else None
    if checkpoint and checkpoint.get("topic") == topic.name and checkpoint.get("last_success_date"):
        last_success = datetime.strptime(checkpoint["last_success_date"], "%Y-%m-%d").date()
        return [d for d in dates if d > last_success]
    return dates


def _chunked(items: list[date], chunk_size: int) -> list[list[date]]:
    if chunk_size <= 0:
        chunk_size = DEFAULT_CHUNK_DAYS
    return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]


def _format_date_span(dates: list[date]) -> str:
    if not dates:
        return "-"
    return f"{dates[0].isoformat()} -> {dates[-1].isoformat()}"


def _resolve_latest_topic_dates(
    inspector: DatabaseInspector,
    topic: M3Topic,
    latest_core_trade_date: date,
    replace_existing: bool,
    label_tail_refresh_days: int,
) -> list[date]:
    current_max_date = inspector.max_date(topic.table_name, topic.date_column)

    if topic.kind == "trade_date":
        # Production latest mode: catch up from current M3 max date to M2/core latest date.
        # If a topic table is empty, only run latest_core_trade_date; use range mode for full backfills.
        if current_max_date is None:
            planned_dates = [latest_core_trade_date]
        else:
            planned_dates = inspector.list_trade_dates_after(after_date=current_max_date, end_date=latest_core_trade_date)

        if replace_existing and not planned_dates:
            planned_dates = [latest_core_trade_date]

        if not replace_existing:
            planned_dates = _filter_missing_dates(inspector, topic, planned_dates)

        print(f"[M3][{topic.name}] latest_core_trade_date={latest_core_trade_date.isoformat()}")
        print(f"[M3][{topic.name}] current_max_date={current_max_date.isoformat() if current_max_date else '-'}")
        print(f"[M3][{topic.name}] planned_dates={len(planned_dates)} span={_format_date_span(planned_dates)}")
        return planned_dates

    # Label latest mode is special:
    # 1) catch up new anchor_dates until latest_core_trade_date;
    # 2) always refresh the latest N trade dates, because censored labels may become uncensored
    #    as new M2 bars arrive.
    new_anchor_dates = inspector.list_trade_dates_after(after_date=current_max_date, end_date=latest_core_trade_date)
    tail_refresh_dates = inspector.list_tail_trade_dates(end_date=latest_core_trade_date, limit=label_tail_refresh_days)
    planned_dates = sorted(set(new_anchor_dates).union(tail_refresh_dates))

    if not replace_existing:
        # Do NOT drop existing tail_refresh_dates. They must be recomputed to update censored labels.
        missing_new_anchor_dates = _filter_missing_dates(inspector, topic, new_anchor_dates)
        planned_dates = sorted(set(missing_new_anchor_dates).union(tail_refresh_dates))

    print(f"[M3][{topic.name}] latest_core_trade_date={latest_core_trade_date.isoformat()}")
    print(f"[M3][{topic.name}] current_max_anchor_date={current_max_date.isoformat() if current_max_date else '-'}")
    print(f"[M3][{topic.name}] new_anchor_dates={len(new_anchor_dates)}")
    print(f"[M3][{topic.name}] tail_refresh_days={label_tail_refresh_days}")
    print(f"[M3][{topic.name}] tail_refresh_dates={len(tail_refresh_dates)} span={_format_date_span(tail_refresh_dates)}")
    print(f"[M3][{topic.name}] planned_dates={len(planned_dates)} span={_format_date_span(planned_dates)}")
    return planned_dates


def _resolve_range_dates(
    inspector: DatabaseInspector,
    topic: M3Topic,
    start_date: date,
    end_date: date,
    resume_enabled: bool,
    replace_existing: bool,
) -> list[date]:
    # Range mode is manual repair/backfill mode. Label anchor dates intentionally follow
    # core trade dates directly; label service itself will mark near-end rows as censored.
    dates = inspector.list_trade_dates(start_date=start_date, end_date=end_date)

    if not replace_existing:
        dates = _filter_missing_dates(inspector, topic, dates)

    return _apply_resume_filter(topic=topic, dates=dates, resume_enabled=resume_enabled)


def _run_planned_dates(
    selected_topics: list[M3Topic],
    topic_dates: dict[str, list[date]],
    start_date: date | None,
    end_date: date | None,
    resume_enabled: bool,
    chunk_days: int,
) -> int:
    if _should_skip_seed():
        print("[M3] skip seed definitions once: true")
    else:
        print("[M3] seed definitions once before child workers")
        _seed_definitions_once()

    for topic in selected_topics:
        dates = _apply_resume_filter(topic=topic, dates=topic_dates.get(topic.name, []), resume_enabled=resume_enabled)
        print(f"[M3][{topic.name}] planned_dates_after_resume={len(dates)} span={_format_date_span(dates)}")
        if not dates:
            continue

        chunks = _chunked(dates, chunk_days)
        for chunk_idx, chunk_dates in enumerate(chunks, start=1):
            print(
                f"[M3][{topic.name}] chunk {chunk_idx}/{len(chunks)} "
                f"size={len(chunk_dates)} span={_format_date_span(chunk_dates)}"
            )
            for target_date in chunk_dates:
                idx = dates.index(target_date) + 1
                print(f"[M3][{topic.name}] ({idx}/{len(dates)}) {target_date.isoformat()} starting")
                rc = _run_module(topic.module_name, extra_env=_build_topic_env(topic, target_date))
                if rc != 0:
                    previous_index = idx - 2
                    last_success = dates[previous_index].isoformat() if previous_index >= 0 else None
                    _write_checkpoint(
                        {
                            "topic": topic.name,
                            "last_success_date": last_success,
                            "failed_date": target_date.isoformat(),
                            "start_date": start_date.isoformat() if start_date else None,
                            "end_date": end_date.isoformat() if end_date else None,
                            "updated_at": datetime.now().isoformat(),
                        }
                    )
                    print(f"[M3][{topic.name}] failed on {target_date.isoformat()} (exit_code={rc})")
                    return rc

                _write_checkpoint(
                    {
                        "topic": topic.name,
                        "last_success_date": target_date.isoformat(),
                        "failed_date": None,
                        "start_date": start_date.isoformat() if start_date else None,
                        "end_date": end_date.isoformat() if end_date else None,
                        "updated_at": datetime.now().isoformat(),
                    }
                )
                print(f"[M3][{topic.name}] {target_date.isoformat()} succeeded")

    _clear_checkpoint()
    return 0


def _run_latest_mode(
    inspector: DatabaseInspector,
    selected_topics: list[M3Topic],
    resume_enabled: bool,
    replace_existing: bool,
    chunk_days: int,
) -> int:
    latest_core_trade_date = inspector.latest_trade_date()
    if latest_core_trade_date is None:
        print("[M3] Failed to resolve latest core trade_date from core_daily_bar.")
        return 2

    label_tail_refresh_days = inspector.resolve_label_tail_refresh_days()
    print(f"[M3] latest_core_trade_date = {latest_core_trade_date.isoformat()}")
    print(f"[M3] label_tail_refresh_days = {label_tail_refresh_days}")

    topic_dates: dict[str, list[date]] = {}
    for topic in selected_topics:
        topic_dates[topic.name] = _resolve_latest_topic_dates(
            inspector=inspector,
            topic=topic,
            latest_core_trade_date=latest_core_trade_date,
            replace_existing=replace_existing,
            label_tail_refresh_days=label_tail_refresh_days,
        )

    return _run_planned_dates(
        selected_topics=selected_topics,
        topic_dates=topic_dates,
        start_date=None,
        end_date=latest_core_trade_date,
        resume_enabled=resume_enabled,
        chunk_days=chunk_days,
    )


def _run_range_mode(
    inspector: DatabaseInspector,
    selected_topics: list[M3Topic],
    start_date: date,
    end_date: date,
    resume_enabled: bool,
    replace_existing: bool,
    chunk_days: int,
) -> int:
    latest_core_trade_date = inspector.latest_trade_date()
    if latest_core_trade_date is not None and end_date > latest_core_trade_date:
        print(
            f"[M3] range end_date={end_date.isoformat()} is later than "
            f"latest_core_trade_date={latest_core_trade_date.isoformat()}, clipped."
        )
        end_date = latest_core_trade_date

    print(
        f"[M3] range/manual mode started: start_date={start_date.isoformat()}, "
        f"end_date={end_date.isoformat()}, chunk_days={chunk_days}, replace_existing={replace_existing}"
    )

    topic_dates: dict[str, list[date]] = {}
    for topic in selected_topics:
        dates = _resolve_range_dates(
            inspector=inspector,
            topic=topic,
            start_date=start_date,
            end_date=end_date,
            resume_enabled=resume_enabled,
            replace_existing=replace_existing,
        )
        print(f"[M3][{topic.name}] planned_dates={len(dates)} span={_format_date_span(dates)}")
        topic_dates[topic.name] = dates

    return _run_planned_dates(
        selected_topics=selected_topics,
        topic_dates=topic_dates,
        start_date=start_date,
        end_date=end_date,
        resume_enabled=resume_enabled,
        chunk_days=chunk_days,
    )


def run_m3_analytics_refresh_chain(
    mode: str = DEFAULT_MODE,
    indicator_only: bool = False,
    factor_only: bool = False,
    feature_only: bool = False,
    label_only: bool = False,
    target_date: date | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    resume_enabled: bool = True,
    replace_existing: bool = False,
    chunk_days: int = DEFAULT_CHUNK_DAYS,
) -> int:
    inspector = DatabaseInspector(str(settings.postgres_v2_url))
    try:
        print("[M3] Analytics refresh chain started.")
        print(f"[M3] mode = {mode}")
        print(f"[M3] replace_existing = {replace_existing}")
        print(f"[M3] resume_enabled = {resume_enabled}")
        print(f"[M3] chunk_days = {chunk_days}")

        selected_topics = _select_topics(indicator_only, factor_only, feature_only, label_only)
        print(f"[M3] selected_topics = {[t.name for t in selected_topics]}")

        if target_date is not None:
            mode = "range"
            start_date = target_date
            end_date = target_date

        if mode == "latest":
            return _run_latest_mode(
                inspector=inspector,
                selected_topics=selected_topics,
                resume_enabled=resume_enabled,
                replace_existing=replace_existing,
                chunk_days=chunk_days,
            )

        if mode != "range":
            print(f"[M3] Unsupported mode: {mode}")
            return 2

        if start_date is None or end_date is None:
            print("[M3] range mode requires start_date and end_date.")
            return 2

        if start_date > end_date:
            print(f"[M3] Invalid range: start_date={start_date.isoformat()} > end_date={end_date.isoformat()}")
            return 2

        return _run_range_mode(
            inspector=inspector,
            selected_topics=selected_topics,
            start_date=start_date,
            end_date=end_date,
            resume_enabled=resume_enabled,
            replace_existing=replace_existing,
            chunk_days=chunk_days,
        )
    finally:
        inspector.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the M3 analytics refresh chain. "
            "Latest mode automatically catches M3 up to the latest core_daily_bar trade_date."
        )
    )
    parser.add_argument("--mode", required=False, default=os.getenv("M3_REFRESH_MODE", DEFAULT_MODE), choices=["latest", "range"])
    parser.add_argument("--target-date", required=False, help="Optional single target date in YYYY-MM-DD.")
    parser.add_argument("--start-date", required=False, default=os.getenv("M3_START_DATE"), help="Range start date in YYYY-MM-DD.")
    parser.add_argument("--end-date", required=False, default=os.getenv("M3_END_DATE"), help="Range end date in YYYY-MM-DD.")
    parser.add_argument(
        "--resume-enabled",
        action="store_true",
        default=_normalize_bool(os.getenv("M3_RESUME_ENABLED"), default=True),
        help="Resume from tmp/m3_analytics_refresh_checkpoint.json when available.",
    )
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        default=_normalize_bool(os.getenv("M3_REPLACE_EXISTING"), default=False),
        help="Recompute dates even if snapshot rows already exist.",
    )
    parser.add_argument("--chunk-days", type=int, default=int(os.getenv("M3_CHUNK_DAYS", str(DEFAULT_CHUNK_DAYS))))
    parser.add_argument("--indicator-only", action="store_true", help="Run only indicator chain.")
    parser.add_argument("--factor-only", action="store_true", help="Run only factor chain.")
    parser.add_argument("--feature-only", action="store_true", help="Run only feature chain.")
    parser.add_argument("--label-only", action="store_true", help="Run only label chain.")

    args = parser.parse_args(argv)

    target_date = datetime.strptime(args.target_date, "%Y-%m-%d").date() if args.target_date else None
    start_date = datetime.strptime(args.start_date, "%Y-%m-%d").date() if args.start_date else None
    end_date = datetime.strptime(args.end_date, "%Y-%m-%d").date() if args.end_date else None

    return run_m3_analytics_refresh_chain(
        mode=args.mode,
        indicator_only=args.indicator_only,
        factor_only=args.factor_only,
        feature_only=args.feature_only,
        label_only=args.label_only,
        target_date=target_date,
        start_date=start_date,
        end_date=end_date,
        resume_enabled=args.resume_enabled,
        replace_existing=args.replace_existing,
        chunk_days=args.chunk_days,
    )


if __name__ == "__main__":
    raise SystemExit(main())
