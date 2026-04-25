from __future__ import annotations

from collections.abc import Generator

from sqlalchemy.orm import Session

from stock_quant_v2.db.session import SessionLocal


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()