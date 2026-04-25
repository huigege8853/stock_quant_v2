from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Iterable

from sqlalchemy import create_engine, text


DEFAULT_PLAN_FILE = "tmp/m7_6_daily_plans.json"


ENV_KEYS = [
    "DATABASE_URL",
    "STOCK_QUANT_V2_DATABASE_URL",
    "STOCK_QUANT_V2_DB_URL",
    "SQLALCHEMY_DATABASE_URL",
    "DB_URL",
    "POSTGRES_URL",
    "V2_SQLALCHEMY_URL",
]


def _strip_inline_comment(value: str) -> str:
    """Strip unquoted # comments from .env style values."""
    value = value.strip().strip('"').strip("'")
    if "#" not in value:
        return value.strip()
    # URLs should not contain spaces before a real fragment in this project.
    # The .env has: postgresql+psycopg://.../stock_quant_v2  # comment
    return re.split(r"\s+#", value, maxsplit=1)[0].strip().strip('"').strip("'")


def _load_dotenv() -> None:
    for env_path in [Path(".env"), Path(".env.local")]:
        if not env_path.exists():
            continue
        try:
            lines = env_path.read_text(encoding="utf-8-sig").splitlines()
        except UnicodeDecodeError:
            lines = env_path.read_text(encoding="gbk", errors="ignore").splitlines()
        for raw_line in lines:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key in ENV_KEYS and key not in os.environ:
                os.environ[key] = _strip_inline_comment(value)


def _get_database_url() -> str:
    _load_dotenv()
    for key in ENV_KEYS:
        value = os.environ.get(key)
        if value:
            return _strip_inline_comment(value)
    raise RuntimeError(
        "Missing database url. Set DATABASE_URL / V2_SQLALCHEMY_URL, "
        "or add one of them to .env."
    )


def _int_list(values: Iterable[int | str | None]) -> list[int]:
    result: list[int] = []
    for value in values:
        if value is None:
            continue
        ivalue = int(value)
        if ivalue > 0 and ivalue not in result:
            result.append(ivalue)
    return result


def _sql_in(values: list[int]) -> str:
    if not values:
        raise ValueError("values is empty")
    return ", ".join(str(int(v)) for v in values)


def _table_exists(conn, table_name: str) -> bool:
    row = conn.execute(
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
    return row is not None


def _columns(conn, table_name: str) -> set[str]:
    rows = conn.execute(
        text(
            """
            select column_name
            from information_schema.columns
            where table_schema = 'public'
              and table_name = :table_name
            """
        ),
        {"table_name": table_name},
    ).all()
    return {str(row[0]) for row in rows}


def _delete_by_run_ids(
    conn,
    *,
    table_name: str,
    run_ids: list[int],
    portfolio_ids: list[int],
) -> int:
    if not run_ids or not _table_exists(conn, table_name):
        return 0

    cols = _columns(conn, table_name)
    if "run_id" not in cols:
        return 0

    where = [f"run_id in ({_sql_in(run_ids)})"]
    if portfolio_ids and "portfolio_id" in cols:
        where.append(f"portfolio_id in ({_sql_in(portfolio_ids)})")

    stmt = text(f"delete from {table_name} where " + " and ".join(where))
    result = conn.execute(stmt)
    return int(result.rowcount or 0)


def _load_plans() -> list[dict]:
    plan_file = os.environ.get("M7_DAILY_PLANS_FILE") or DEFAULT_PLAN_FILE
    path = Path(plan_file)
    if not path.exists():
        raise RuntimeError(f"plan file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list):
        raise RuntimeError("M7 daily plans file must be a JSON array")
    return [dict(item) for item in data]


def main() -> None:
    plans = _load_plans()

    portfolio_ids = _int_list(plan.get("portfolio_id") for plan in plans)
    order_run_ids = _int_list(plan.get("order_run_id") for plan in plans)
    fill_run_ids = _int_list(plan.get("fill_run_id") for plan in plans)
    snapshot_run_ids = _int_list(plan.get("snapshot_run_id") for plan in plans)
    position_run_ids = _int_list(
        value
        for plan in plans
        for value in [plan.get("carry_position_run_id"), plan.get("position_run_id")]
    )
    all_run_ids = _int_list(order_run_ids + fill_run_ids + snapshot_run_ids + position_run_ids)

    if not portfolio_ids:
        raise RuntimeError("No portfolio_id found in M7 daily plans")

    engine = create_engine(_get_database_url(), future=True)

    with engine.begin() as conn:
        # Important FK order:
        # ledger references order/fill/position/snapshot; fill references order.
        deleted_ledger = _delete_by_run_ids(
            conn,
            table_name="trading_paper_trade_ledger",
            run_ids=all_run_ids,
            portfolio_ids=portfolio_ids,
        )
        deleted_snapshots = _delete_by_run_ids(
            conn,
            table_name="trading_paper_portfolio_snapshot",
            run_ids=snapshot_run_ids,
            portfolio_ids=portfolio_ids,
        )
        deleted_positions = _delete_by_run_ids(
            conn,
            table_name="trading_paper_position",
            run_ids=position_run_ids,
            portfolio_ids=portfolio_ids,
        )
        deleted_fills = _delete_by_run_ids(
            conn,
            table_name="trading_paper_fill",
            run_ids=fill_run_ids,
            portfolio_ids=portfolio_ids,
        )
        deleted_orders = _delete_by_run_ids(
            conn,
            table_name="trading_paper_order",
            run_ids=order_run_ids,
            portfolio_ids=portfolio_ids,
        )

    print(
        json.dumps(
            {
                "status": "SUCCESS",
                "portfolio_ids": portfolio_ids,
                "order_run_ids": order_run_ids,
                "fill_run_ids": fill_run_ids,
                "position_run_ids": position_run_ids,
                "snapshot_run_ids": snapshot_run_ids,
                "deleted": {
                    "ledger": deleted_ledger,
                    "snapshots": deleted_snapshots,
                    "positions": deleted_positions,
                    "fills": deleted_fills,
                    "orders": deleted_orders,
                },
                "note": "ops_run rows are intentionally kept so FK placeholders can be reused.",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
