from __future__ import annotations

import json
import os
import uuid
from datetime import date, timedelta
from typing import Any

import psycopg
from psycopg.types.json import Jsonb


PROD_DSN = os.getenv(
    "PROD_DSN",
    "postgresql://research_reader:stock_read@127.0.0.1:54322/stock_quant_v2",
)
RESEARCH_DSN = os.getenv(
    "RESEARCH_DSN",
    "postgresql://sqv2_research_user:sqv2_research_user@127.0.0.1:54322/stock_quant_v2_research",
)

BATCH_SIZE = int(os.getenv("SYNC_BATCH_SIZE", "2000"))
MARKET_SCOPE = os.getenv("RESEARCH_MARKET_SCOPE", "CN_A")
DAILY_BAR_WINDOW_DAYS = int(os.getenv("DAILY_BAR_WINDOW_DAYS", "30"))
ADJUST_FACTOR_WINDOW_DAYS = int(os.getenv("ADJUST_FACTOR_WINDOW_DAYS", "90"))
MARKET_INDEX_BAR_WINDOW_DAYS = int(os.getenv("MARKET_INDEX_BAR_WINDOW_DAYS", "30"))
MARKET_BREADTH_WINDOW_DAYS = int(os.getenv("MARKET_BREADTH_WINDOW_DAYS", "30"))

RUN_DATASETS = [
    "meta_instrument",
    "meta_trading_calendar",
    "meta_dataset",
    "meta_data_vendor",
    "ops_run",
    "meta_data_version",
    "market_index",
    "core_daily_bar",
    "core_adjust_factor",
    "market_index_bar",
    "core_market_breadth",
]

READINESS_DATASETS = [
    "meta_instrument",
    "meta_trading_calendar",
    "core_daily_bar",
    "core_adjust_factor",
    "market_index_bar",
    "core_market_breadth",
]


def append_unique(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)


def get_latest_closed_trade_date(prod_conn: psycopg.Connection) -> date:
    with prod_conn.cursor() as cur:
        cur.execute(
            """
            SELECT max(trade_date)
            FROM public.meta_trading_calendar
            WHERE is_open = true
              AND trade_date < CURRENT_DATE
            """
        )
        row = cur.fetchone()

    if not row or row[0] is None:
        raise RuntimeError("cannot determine latest_closed_trade_date from meta_trading_calendar")

    return row[0]


def get_table_columns(conn: psycopg.Connection, table_name: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table_name,),
        )
        rows = cur.fetchall()

    cols = [r[0] for r in rows]
    if not cols:
        raise RuntimeError(f"table public.{table_name} not found")
    return cols


def make_upsert_sql(table_name: str, columns: list[str], conflict_cols: list[str]) -> str:
    insert_cols = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    conflict_clause = ", ".join(conflict_cols)

    update_cols = [c for c in columns if c not in conflict_cols]
    if not update_cols:
        raise RuntimeError(f"no update columns for {table_name}")

    update_clause = ",\n            ".join([f"{c} = EXCLUDED.{c}" for c in update_cols])

    return f"""
        INSERT INTO public.{table_name} ({insert_cols})
        VALUES ({placeholders})
        ON CONFLICT ({conflict_clause}) DO UPDATE SET
            {update_clause}
    """


def normalize_value_for_psycopg(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return Jsonb(value)
    return value


def normalize_rows_for_psycopg(rows: list[tuple[Any, ...]]) -> list[tuple[Any, ...]]:
    return [
        tuple(normalize_value_for_psycopg(v) for v in row)
        for row in rows
    ]


def stream_upsert(
    prod_conn: psycopg.Connection,
    research_conn: psycopg.Connection,
    select_sql: str,
    upsert_sql: str,
    params: tuple[Any, ...] = (),
) -> tuple[int, int]:
    scanned = 0
    upserted = 0
    cursor_name = f"prod_stream_{uuid.uuid4().hex[:8]}"

    with prod_conn.cursor(name=cursor_name) as pcur:
        pcur.execute(select_sql, params)

        while True:
            rows = pcur.fetchmany(BATCH_SIZE)
            if not rows:
                break

            normalized_rows = normalize_rows_for_psycopg(rows)

            with research_conn.cursor() as rcur:
                rcur.executemany(upsert_sql, normalized_rows)

            research_conn.commit()
            scanned += len(rows)
            upserted += len(rows)

    return scanned, upserted


def query_scalar_list(conn: psycopg.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[Any]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [r[0] for r in rows]


def create_run(research_conn: psycopg.Connection, target_date: date, trigger_mode: str) -> int:
    run_code = f"research_publish_{target_date}_{uuid.uuid4().hex[:8]}"

    with research_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO research_ops.research_sync_run
            (run_code, trigger_mode, target_watermark_date, status, datasets_planned)
            VALUES (%s, %s, %s, 'RUNNING', %s::jsonb)
            RETURNING run_id
            """,
            (run_code, trigger_mode, target_date, json.dumps(RUN_DATASETS)),
        )
        run_id = cur.fetchone()[0]

    research_conn.commit()
    return run_id


def finish_run(
    research_conn: psycopg.Connection,
    run_id: int,
    status: str,
    datasets_finished: list[str],
    error_message: str | None = None,
) -> None:
    with research_conn.cursor() as cur:
        cur.execute(
            """
            UPDATE research_ops.research_sync_run
            SET finished_at = now(),
                status = %s,
                datasets_finished = %s::jsonb,
                error_message = %s,
                updated_at = now()
            WHERE run_id = %s
            """,
            (status, json.dumps(datasets_finished), error_message, run_id),
        )
    research_conn.commit()


def create_batch(
    research_conn: psycopg.Connection,
    run_id: int,
    dataset_code: str,
    batch_type: str,
    window_start_date: date | None = None,
    window_end_date: date | None = None,
    chunk_key: str | None = None,
) -> int:
    with research_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO research_ops.research_sync_batch
            (run_id, dataset_code, batch_type, window_start_date, window_end_date, chunk_key, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'RUNNING')
            RETURNING batch_id
            """,
            (run_id, dataset_code, batch_type, window_start_date, window_end_date, chunk_key),
        )
        batch_id = cur.fetchone()[0]

    research_conn.commit()
    return batch_id


def finish_batch(
    research_conn: psycopg.Connection,
    batch_id: int,
    status: str,
    rows_scanned: int,
    rows_upserted: int,
    error_message: str | None = None,
) -> None:
    note = f"rows_upserted={rows_upserted}"

    with research_conn.cursor() as cur:
        cur.execute(
            """
            UPDATE research_ops.research_sync_batch
            SET finished_at = now(),
                status = %s,
                rows_scanned = %s,
                note = %s,
                error_message = %s,
                updated_at = now()
            WHERE batch_id = %s
            """,
            (status, rows_scanned, note, error_message, batch_id),
        )

    research_conn.commit()


def update_watermark(
    research_conn: psycopg.Connection,
    dataset_code: str,
    watermark_date: date,
    run_id: int,
    status: str = "READY",
) -> None:
    with research_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO research_ops.data_watermark
            (dataset_code, market_scope, watermark_date, status, last_run_id, gap_count, updated_at)
            VALUES (%s, %s, %s, %s, %s, 0, now())
            ON CONFLICT (dataset_code, market_scope)
            DO UPDATE SET
                watermark_date = EXCLUDED.watermark_date,
                status = EXCLUDED.status,
                last_run_id = EXCLUDED.last_run_id,
                updated_at = now()
            """,
            (dataset_code, MARKET_SCOPE, watermark_date, status, run_id),
        )

    research_conn.commit()


def build_readiness_report(research_conn: psycopg.Connection, as_of_date: date, run_id: int) -> None:
    with research_conn.cursor() as cur:
        cur.execute(
            """
            SELECT dataset_code, watermark_date, status
            FROM research_ops.data_watermark
            WHERE market_scope = %s
              AND dataset_code = ANY(%s)
            """,
            (MARKET_SCOPE, READINESS_DATASETS),
        )
        rows = cur.fetchall()

    status_map = {r[0]: {"watermark_date": r[1], "status": r[2]} for r in rows}
    ready: list[str] = []
    warn: list[str] = []
    missing: list[str] = []

    for ds in READINESS_DATASETS:
        info = status_map.get(ds)
        if not info:
            missing.append(ds)
        elif info["watermark_date"] < as_of_date or info["status"] != "READY":
            warn.append(ds)
        else:
            ready.append(ds)

    final_status = "PASS"
    if missing:
        final_status = "FAIL"
    elif warn:
        final_status = "PASS_WITH_WARN"

    detail = {
        "as_of_date": str(as_of_date),
        "market_scope": MARKET_SCOPE,
        "dataset_status": {
            ds: {
                "watermark_date": str(info["watermark_date"]),
                "status": info["status"],
            }
            for ds, info in status_map.items()
        },
    }

    with research_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO research_ops.research_readiness_report
            (as_of_date, market_scope, status, required_datasets, ready_datasets,
             warning_datasets, missing_datasets, detail_json, source_run_id)
            VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s)
            ON CONFLICT (as_of_date, market_scope)
            DO UPDATE SET
                status = EXCLUDED.status,
                required_datasets = EXCLUDED.required_datasets,
                ready_datasets = EXCLUDED.ready_datasets,
                warning_datasets = EXCLUDED.warning_datasets,
                missing_datasets = EXCLUDED.missing_datasets,
                detail_json = EXCLUDED.detail_json,
                source_run_id = EXCLUDED.source_run_id,
                generated_at = now()
            """,
            (
                as_of_date,
                MARKET_SCOPE,
                final_status,
                json.dumps(READINESS_DATASETS),
                json.dumps(ready),
                json.dumps(warn),
                json.dumps(missing),
                json.dumps(detail),
                run_id,
            ),
        )

    research_conn.commit()


def sync_full_table_by_id(
    prod_conn: psycopg.Connection,
    research_conn: psycopg.Connection,
    table_name: str,
) -> tuple[int, int]:
    cols = get_table_columns(prod_conn, table_name)
    select_sql = f"SELECT {', '.join(cols)} FROM public.{table_name} ORDER BY id"
    upsert_sql = make_upsert_sql(table_name, cols, ["id"])
    return stream_upsert(prod_conn, research_conn, select_sql, upsert_sql)


def sync_table_by_ids(
    prod_conn: psycopg.Connection,
    research_conn: psycopg.Connection,
    table_name: str,
    ids: list[int],
) -> tuple[int, int]:
    if not ids:
        return 0, 0

    cols = get_table_columns(prod_conn, table_name)
    select_sql = f"SELECT {', '.join(cols)} FROM public.{table_name} WHERE id = ANY(%s) ORDER BY id"
    upsert_sql = make_upsert_sql(table_name, cols, ["id"])
    return stream_upsert(prod_conn, research_conn, select_sql, upsert_sql, (ids,))


def sync_ops_run_recursive(
    prod_conn: psycopg.Connection,
    research_conn: psycopg.Connection,
    run_ids: list[int],
) -> tuple[int, int]:
    if not run_ids:
        return 0, 0

    cols = get_table_columns(prod_conn, "ops_run")
    select_cols = ", ".join([f"o.{c}" for c in cols])

    select_sql = f"""
        WITH RECURSIVE needed_runs AS (
            SELECT o.id, o.parent_run_id
            FROM public.ops_run o
            WHERE o.id = ANY(%s)

            UNION

            SELECT p.id, p.parent_run_id
            FROM public.ops_run p
            JOIN needed_runs nr
              ON p.id = nr.parent_run_id
        )
        SELECT DISTINCT {select_cols}
        FROM public.ops_run o
        JOIN needed_runs nr
          ON o.id = nr.id
        ORDER BY o.id
    """

    upsert_sql = make_upsert_sql("ops_run", cols, ["id"])
    return stream_upsert(prod_conn, research_conn, select_sql, upsert_sql, (run_ids,))


def sync_meta_instrument(prod_conn: psycopg.Connection, research_conn: psycopg.Connection) -> tuple[int, int]:
    return sync_full_table_by_id(prod_conn, research_conn, "meta_instrument")


def sync_meta_trading_calendar(prod_conn: psycopg.Connection, research_conn: psycopg.Connection) -> tuple[int, int]:
    return sync_full_table_by_id(prod_conn, research_conn, "meta_trading_calendar")


def sync_market_index_by_ids(
    prod_conn: psycopg.Connection,
    research_conn: psycopg.Connection,
    market_index_ids: list[int],
) -> tuple[int, int]:
    return sync_table_by_ids(prod_conn, research_conn, "market_index", market_index_ids)


def sync_meta_dependencies_for_window(
    prod_conn: psycopg.Connection,
    research_conn: psycopg.Connection,
    run_id: int,
    source_table: str,
    start_date: date,
    end_date: date,
    finished: list[str],
    extra_dependency_table: str | None = None,
    extra_dependency_ids_sql: str | None = None,
) -> None:
    data_version_ids = query_scalar_list(
        prod_conn,
        f"""
        SELECT DISTINCT data_version_id
        FROM public.{source_table}
        WHERE trade_date BETWEEN %s AND %s
          AND data_version_id IS NOT NULL
        ORDER BY data_version_id
        """,
        (start_date, end_date),
    )

    dataset_ids = query_scalar_list(
        prod_conn,
        """
        SELECT DISTINCT dataset_id
        FROM public.meta_data_version
        WHERE id = ANY(%s)
          AND dataset_id IS NOT NULL
        ORDER BY dataset_id
        """,
        (data_version_ids or [0],),
    ) if data_version_ids else []

    vendor_ids = query_scalar_list(
        prod_conn,
        """
        SELECT DISTINCT vendor_id
        FROM public.meta_data_version
        WHERE id = ANY(%s)
          AND vendor_id IS NOT NULL
        ORDER BY vendor_id
        """,
        (data_version_ids or [0],),
    ) if data_version_ids else []

    ops_run_ids = query_scalar_list(
        prod_conn,
        """
        SELECT DISTINCT run_id
        FROM public.meta_data_version
        WHERE id = ANY(%s)
          AND run_id IS NOT NULL
        ORDER BY run_id
        """,
        (data_version_ids or [0],),
    ) if data_version_ids else []

    dep_chunk_key = f"{source_table}_deps"

    batch_id = create_batch(research_conn, run_id, "meta_dataset", "FULL_UPSERT", None, None, dep_chunk_key)
    try:
        scanned, upserted = sync_table_by_ids(prod_conn, research_conn, "meta_dataset", dataset_ids)
        finish_batch(research_conn, batch_id, "SUCCESS", scanned, upserted)
        append_unique(finished, "meta_dataset")
    except Exception as e:
        research_conn.rollback()
        finish_batch(research_conn, batch_id, "FAILED", 0, 0, str(e))
        raise

    batch_id = create_batch(research_conn, run_id, "meta_data_vendor", "FULL_UPSERT", None, None, dep_chunk_key)
    try:
        scanned, upserted = sync_table_by_ids(prod_conn, research_conn, "meta_data_vendor", vendor_ids)
        finish_batch(research_conn, batch_id, "SUCCESS", scanned, upserted)
        append_unique(finished, "meta_data_vendor")
    except Exception as e:
        research_conn.rollback()
        finish_batch(research_conn, batch_id, "FAILED", 0, 0, str(e))
        raise

    batch_id = create_batch(research_conn, run_id, "ops_run", "FULL_UPSERT", None, None, dep_chunk_key)
    try:
        scanned, upserted = sync_ops_run_recursive(prod_conn, research_conn, ops_run_ids)
        finish_batch(research_conn, batch_id, "SUCCESS", scanned, upserted)
        append_unique(finished, "ops_run")
    except Exception as e:
        research_conn.rollback()
        finish_batch(research_conn, batch_id, "FAILED", 0, 0, str(e))
        raise

    batch_id = create_batch(research_conn, run_id, "meta_data_version", "FULL_UPSERT", None, None, dep_chunk_key)
    try:
        scanned, upserted = sync_table_by_ids(prod_conn, research_conn, "meta_data_version", data_version_ids)
        finish_batch(research_conn, batch_id, "SUCCESS", scanned, upserted)
        append_unique(finished, "meta_data_version")
    except Exception as e:
        research_conn.rollback()
        finish_batch(research_conn, batch_id, "FAILED", 0, 0, str(e))
        raise

    if extra_dependency_table and extra_dependency_ids_sql:
        extra_ids = query_scalar_list(prod_conn, extra_dependency_ids_sql, (start_date, end_date))
        batch_id = create_batch(
            research_conn,
            run_id,
            extra_dependency_table,
            "FULL_UPSERT",
            None,
            None,
            dep_chunk_key,
        )
        try:
            if extra_dependency_table == "market_index":
                scanned, upserted = sync_market_index_by_ids(prod_conn, research_conn, extra_ids)
            else:
                scanned, upserted = sync_table_by_ids(prod_conn, research_conn, extra_dependency_table, extra_ids)
            finish_batch(research_conn, batch_id, "SUCCESS", scanned, upserted)
            append_unique(finished, extra_dependency_table)
        except Exception as e:
            research_conn.rollback()
            finish_batch(research_conn, batch_id, "FAILED", 0, 0, str(e))
            raise


def sync_core_daily_bar_window(
    prod_conn: psycopg.Connection,
    research_conn: psycopg.Connection,
    start_date: date,
    end_date: date,
) -> tuple[int, int]:
    select_sql = """
        SELECT
            instrument_id, trade_date, open, high, low, close, pre_close,
            pct_change, price_change, volume, amount, turnover_rate, is_suspended, data_version_id,
            created_at, updated_at, price_adjust_type, source_provider
        FROM public.core_daily_bar
        WHERE trade_date BETWEEN %s AND %s
        ORDER BY instrument_id, trade_date, price_adjust_type
    """

    upsert_sql = """
        INSERT INTO public.core_daily_bar (
            instrument_id, trade_date, open, high, low, close, pre_close,
            pct_change, price_change, volume, amount, turnover_rate, is_suspended, data_version_id,
            created_at, updated_at, price_adjust_type, source_provider
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT ON CONSTRAINT uq_core_daily_bar__instrument_id_trade_date DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            pre_close = EXCLUDED.pre_close,
            pct_change = EXCLUDED.pct_change,
            price_change = EXCLUDED.price_change,
            volume = EXCLUDED.volume,
            amount = EXCLUDED.amount,
            turnover_rate = EXCLUDED.turnover_rate,
            is_suspended = EXCLUDED.is_suspended,
            data_version_id = EXCLUDED.data_version_id,
            updated_at = EXCLUDED.updated_at,
            price_adjust_type = EXCLUDED.price_adjust_type,
            source_provider = EXCLUDED.source_provider
    """

    return stream_upsert(prod_conn, research_conn, select_sql, upsert_sql, (start_date, end_date))


def sync_core_adjust_factor_window(
    prod_conn: psycopg.Connection,
    research_conn: psycopg.Connection,
    start_date: date,
    end_date: date,
) -> tuple[int, int]:
    select_sql = """
        SELECT
            instrument_id, trade_date, forward_factor, backward_factor,
            data_version_id, created_at, updated_at
        FROM public.core_adjust_factor
        WHERE trade_date BETWEEN %s AND %s
        ORDER BY instrument_id, trade_date
    """

    upsert_sql = """
        INSERT INTO public.core_adjust_factor (
            instrument_id, trade_date, forward_factor, backward_factor,
            data_version_id, created_at, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT ON CONSTRAINT uq_core_adjust_factor__instrument_id_trade_date DO UPDATE SET
            forward_factor = EXCLUDED.forward_factor,
            backward_factor = EXCLUDED.backward_factor,
            data_version_id = EXCLUDED.data_version_id,
            updated_at = EXCLUDED.updated_at
    """

    return stream_upsert(prod_conn, research_conn, select_sql, upsert_sql, (start_date, end_date))


def sync_market_index_bar_window(
    prod_conn: psycopg.Connection,
    research_conn: psycopg.Connection,
    start_date: date,
    end_date: date,
) -> tuple[int, int]:
    select_sql = """
        SELECT
            market_index_id, trade_date, open, high, low, close, volume,
            turnover, source_provider, data_version_id
        FROM public.market_index_bar
        WHERE trade_date BETWEEN %s AND %s
        ORDER BY market_index_id, trade_date
    """

    upsert_sql = """
        INSERT INTO public.market_index_bar (
            market_index_id, trade_date, open, high, low, close, volume,
            turnover, source_provider, data_version_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT ON CONSTRAINT uq_market_index_bar_idx_date DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            turnover = EXCLUDED.turnover,
            source_provider = EXCLUDED.source_provider,
            data_version_id = EXCLUDED.data_version_id
    """

    return stream_upsert(prod_conn, research_conn, select_sql, upsert_sql, (start_date, end_date))


def sync_core_market_breadth_window(
    prod_conn: psycopg.Connection,
    research_conn: psycopg.Connection,
    start_date: date,
    end_date: date,
) -> tuple[int, int]:
    select_sql = """
        SELECT
            market_scope, trade_date, universe_count, bar_count, advancers,
            decliners, unchanged, suspended_count, total_turnover_amount_cny,
            mean_return, median_return, data_version_id, created_at, updated_at
        FROM public.core_market_breadth
        WHERE trade_date BETWEEN %s AND %s
        ORDER BY market_scope, trade_date
    """

    upsert_sql = """
        INSERT INTO public.core_market_breadth (
            market_scope, trade_date, universe_count, bar_count, advancers,
            decliners, unchanged, suspended_count, total_turnover_amount_cny,
            mean_return, median_return, data_version_id, created_at, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT ON CONSTRAINT uq_core_market_breadth__market_scope_trade_date DO UPDATE SET
            universe_count = EXCLUDED.universe_count,
            bar_count = EXCLUDED.bar_count,
            advancers = EXCLUDED.advancers,
            decliners = EXCLUDED.decliners,
            unchanged = EXCLUDED.unchanged,
            suspended_count = EXCLUDED.suspended_count,
            total_turnover_amount_cny = EXCLUDED.total_turnover_amount_cny,
            mean_return = EXCLUDED.mean_return,
            median_return = EXCLUDED.median_return,
            data_version_id = EXCLUDED.data_version_id,
            updated_at = EXCLUDED.updated_at
    """

    return stream_upsert(prod_conn, research_conn, select_sql, upsert_sql, (start_date, end_date))


def main() -> None:
    finished: list[str] = []

    with psycopg.connect(PROD_DSN) as prod_conn, psycopg.connect(RESEARCH_DSN) as research_conn:
        target_date = get_latest_closed_trade_date(prod_conn)
        run_id = create_run(research_conn, target_date, trigger_mode="manual")

        try:
            batch_id = create_batch(research_conn, run_id, "meta_instrument", "FULL_UPSERT")
            try:
                scanned, upserted = sync_meta_instrument(prod_conn, research_conn)
                finish_batch(research_conn, batch_id, "SUCCESS", scanned, upserted)
                update_watermark(research_conn, "meta_instrument", target_date, run_id, "READY")
                append_unique(finished, "meta_instrument")
            except Exception as e:
                research_conn.rollback()
                finish_batch(research_conn, batch_id, "FAILED", 0, 0, str(e))
                raise

            batch_id = create_batch(research_conn, run_id, "meta_trading_calendar", "FULL_UPSERT")
            try:
                scanned, upserted = sync_meta_trading_calendar(prod_conn, research_conn)
                finish_batch(research_conn, batch_id, "SUCCESS", scanned, upserted)
                update_watermark(research_conn, "meta_trading_calendar", target_date, run_id, "READY")
                append_unique(finished, "meta_trading_calendar")
            except Exception as e:
                research_conn.rollback()
                finish_batch(research_conn, batch_id, "FAILED", 0, 0, str(e))
                raise

            daily_bar_start = target_date - timedelta(days=DAILY_BAR_WINDOW_DAYS)
            sync_meta_dependencies_for_window(
                prod_conn=prod_conn,
                research_conn=research_conn,
                run_id=run_id,
                source_table="core_daily_bar",
                start_date=daily_bar_start,
                end_date=target_date,
                finished=finished,
            )

            batch_id = create_batch(
                research_conn,
                run_id,
                "core_daily_bar",
                "WINDOW_REFRESH",
                daily_bar_start,
                target_date,
            )
            try:
                scanned, upserted = sync_core_daily_bar_window(prod_conn, research_conn, daily_bar_start, target_date)
                finish_batch(research_conn, batch_id, "SUCCESS", scanned, upserted)
                update_watermark(research_conn, "core_daily_bar", target_date, run_id, "READY")
                append_unique(finished, "core_daily_bar")
            except Exception as e:
                research_conn.rollback()
                finish_batch(research_conn, batch_id, "FAILED", 0, 0, str(e))
                raise

            adjust_factor_start = target_date - timedelta(days=ADJUST_FACTOR_WINDOW_DAYS)
            sync_meta_dependencies_for_window(
                prod_conn=prod_conn,
                research_conn=research_conn,
                run_id=run_id,
                source_table="core_adjust_factor",
                start_date=adjust_factor_start,
                end_date=target_date,
                finished=finished,
            )

            batch_id = create_batch(
                research_conn,
                run_id,
                "core_adjust_factor",
                "WINDOW_REFRESH",
                adjust_factor_start,
                target_date,
            )
            try:
                scanned, upserted = sync_core_adjust_factor_window(prod_conn, research_conn, adjust_factor_start, target_date)
                finish_batch(research_conn, batch_id, "SUCCESS", scanned, upserted)
                update_watermark(research_conn, "core_adjust_factor", target_date, run_id, "READY")
                append_unique(finished, "core_adjust_factor")
            except Exception as e:
                research_conn.rollback()
                finish_batch(research_conn, batch_id, "FAILED", 0, 0, str(e))
                raise

            market_index_bar_start = target_date - timedelta(days=MARKET_INDEX_BAR_WINDOW_DAYS)
            sync_meta_dependencies_for_window(
                prod_conn=prod_conn,
                research_conn=research_conn,
                run_id=run_id,
                source_table="market_index_bar",
                start_date=market_index_bar_start,
                end_date=target_date,
                finished=finished,
                extra_dependency_table="market_index",
                extra_dependency_ids_sql="""
                    SELECT DISTINCT market_index_id
                    FROM public.market_index_bar
                    WHERE trade_date BETWEEN %s AND %s
                      AND market_index_id IS NOT NULL
                    ORDER BY market_index_id
                """,
            )

            batch_id = create_batch(
                research_conn,
                run_id,
                "market_index_bar",
                "WINDOW_REFRESH",
                market_index_bar_start,
                target_date,
            )
            try:
                scanned, upserted = sync_market_index_bar_window(prod_conn, research_conn, market_index_bar_start, target_date)
                finish_batch(research_conn, batch_id, "SUCCESS", scanned, upserted)
                update_watermark(research_conn, "market_index_bar", target_date, run_id, "READY")
                append_unique(finished, "market_index_bar")
            except Exception as e:
                research_conn.rollback()
                finish_batch(research_conn, batch_id, "FAILED", 0, 0, str(e))
                raise

            market_breadth_start = target_date - timedelta(days=MARKET_BREADTH_WINDOW_DAYS)
            sync_meta_dependencies_for_window(
                prod_conn=prod_conn,
                research_conn=research_conn,
                run_id=run_id,
                source_table="core_market_breadth",
                start_date=market_breadth_start,
                end_date=target_date,
                finished=finished,
            )

            batch_id = create_batch(
                research_conn,
                run_id,
                "core_market_breadth",
                "WINDOW_REFRESH",
                market_breadth_start,
                target_date,
            )
            try:
                scanned, upserted = sync_core_market_breadth_window(prod_conn, research_conn, market_breadth_start, target_date)
                finish_batch(research_conn, batch_id, "SUCCESS", scanned, upserted)
                update_watermark(research_conn, "core_market_breadth", target_date, run_id, "READY")
                append_unique(finished, "core_market_breadth")
            except Exception as e:
                research_conn.rollback()
                finish_batch(research_conn, batch_id, "FAILED", 0, 0, str(e))
                raise

            build_readiness_report(research_conn, target_date, run_id)
            finish_run(research_conn, run_id, "SUCCESS", finished)

        except Exception as e:
            research_conn.rollback()
            finish_run(research_conn, run_id, "FAILED", finished, str(e))
            raise


if __name__ == "__main__":
    main()