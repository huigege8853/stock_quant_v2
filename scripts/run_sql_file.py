from __future__ import annotations

import argparse
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

from sqlalchemy import create_engine, text


def load_env() -> None:
    root = Path(__file__).resolve().parents[1]
    env_file = root / ".env.research"
    if load_dotenv is not None and env_file.exists():
        load_dotenv(env_file, override=False)


def clean_env_value(value: str | None) -> str | None:
    if not value:
        return None

    cleaned = value.strip()
    cleaned = cleaned.splitlines()[0].strip()

    if " #" in cleaned:
        cleaned = cleaned.split(" #", 1)[0].strip()

    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
        cleaned = cleaned[1:-1].strip()

    return cleaned or None


def resolve_database_url(cli_db_url: str | None) -> str:
    if cli_db_url:
        return cli_db_url

    candidates = [
        "V2_SQLALCHEMY_URL",
        "DATABASE_URL",
        "SQLALCHEMY_DATABASE_URI",
        "POSTGRES_DSN",
        "DB_URL",
    ]

    for key in candidates:
        raw = os.getenv(key)
        value = clean_env_value(raw)
        if value:
            return value

    host = clean_env_value(os.getenv("POSTGRES_HOST")) or "localhost"
    port = clean_env_value(os.getenv("POSTGRES_PORT")) or "5432"
    user = clean_env_value(os.getenv("POSTGRES_USER")) or "postgres"
    password = clean_env_value(os.getenv("POSTGRES_PASSWORD")) or "postgres"
    db = clean_env_value(os.getenv("POSTGRES_DB")) or "stock_quant_v2"

    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"


def split_sql_statements(sql_text: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single = False
    in_double = False

    for ch in sql_text:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double

        if ch == ";" and not in_single and not in_double:
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
        else:
            current.append(ch)

    tail = "".join(current).strip()
    if tail:
        statements.append(tail)

    return statements


def print_result(cursor_result, index: int) -> None:
    if not cursor_result.returns_rows:
        rowcount = cursor_result.rowcount
        print(f"\n--- Statement {index}: OK (rowcount={rowcount}) ---")
        return

    rows = cursor_result.fetchall()
    columns = list(cursor_result.keys())

    print(f"\n--- Statement {index}: RESULT ({len(rows)} rows) ---")
    if not rows:
        print("(no rows)")
        return

    print(" | ".join(columns))
    print("-" * max(20, len(" | ".join(columns))))

    for row in rows:
        print(" | ".join("" if v is None else str(v) for v in row))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("sql_file", help="Path to SQL file")
    parser.add_argument("--db-url", default=None, help="Explicit database URL")
    args = parser.parse_args()

    sql_file = Path(args.sql_file).resolve()
    if not sql_file.exists():
        print(f"SQL file not found: {sql_file}")
        return 1

    load_env()
    database_url = resolve_database_url(args.db_url)

    print(f"Using SQL file: {sql_file}")
    print(f"Using database URL: {database_url}")

    sql_text = sql_file.read_text(encoding="utf-8")
    statements = split_sql_statements(sql_text)

    if not statements:
        print("No SQL statements found.")
        return 1

    engine = create_engine(database_url)

    try:
        with engine.connect() as conn:
            for i, stmt in enumerate(statements, start=1):
                stmt_clean = stmt.strip()
                if not stmt_clean:
                    continue

                try:
                    result = conn.execute(text(stmt_clean))
                    print_result(result, i)
                except Exception as e:
                    print(f"\n--- Statement {i}: ERROR ---")
                    print(stmt_clean[:500])
                    print(f"\n{type(e).__name__}: {e}")
                    return 2
    finally:
        engine.dispose()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
