from __future__ import annotations

import json
import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any


def env_int(name: str, default: int | None = None) -> int | None:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def env_str(name: str, default: str | None = None) -> str | None:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw


def env_date(name: str, default: date | None = None) -> date | None:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return date.fromisoformat(raw)


def env_path(name: str, default: str) -> Path:
    raw = os.getenv(name)
    return Path(raw or default)


def json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=json_default))

def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y"}


def env_int_list(name: str) -> list[int] | None:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return None
    return [int(x.strip()) for x in raw.split(",") if x.strip()]