from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
import json
from typing import Any

from stock_quant_v2.data_domain.dto.daily_bar import DailyBarDTO


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def build_payload_hash(payload: dict) -> str:
    normalized = _json_safe(payload)
    raw = json.dumps(normalized, sort_keys=True, ensure_ascii=False, default=str)
    return sha256(raw.encode("utf-8")).hexdigest()


def dto_to_raw_daily_bar_dict(dto: DailyBarDTO, sync_run_id: int, batch_id: int) -> dict:
    payload_json = _json_safe(dto.raw_payload)

    return {
        "provider_name": dto.provider_name,
        "dataset_code": "daily_bar",
        "provider_record_key": dto.provider_record_key,
        "symbol": dto.vendor_symbol or dto.ticker,
        "trade_date": dto.trade_date,
        "batch_id": batch_id,
        "sync_run_id": sync_run_id,
        "request_params": None,
        "payload_json": payload_json,
        "payload_hash": build_payload_hash(payload_json),
        "provider_update_ts": None,
        "ingested_at": datetime.utcnow(),
    }


def dto_to_staging_daily_bar_dict(
    dto: DailyBarDTO,
    sync_run_id: int,
    batch_id: int,
    raw_record_id: int | None,
) -> dict:
    return {
        "sync_run_id": sync_run_id,
        "batch_id": batch_id,
        "provider_name": dto.provider_name,
        "dataset_code": "daily_bar",
        "market_code": dto.market_code,
        "exchange_code": dto.exchange_code,
        "ticker": dto.ticker,
        "vendor_symbol": dto.vendor_symbol,
        "trade_date": dto.trade_date,
        "price_adjust_type": dto.price_adjust_type,
        "open": dto.open,
        "high": dto.high,
        "low": dto.low,
        "close": dto.close,
        "pre_close": dto.pre_close,
        "volume": dto.volume,
        "turnover": dto.turnover,
        "amplitude": dto.amplitude,
        "pct_change": dto.pct_change,
        "price_change": dto.price_change,
        "turnover_rate": dto.turnover_rate,
        "suspended_flag": dto.suspended_flag,
        "provider_record_key": dto.provider_record_key,
        "raw_record_id": raw_record_id,
    }


def staging_to_core_daily_bar_dict(stg_row: dict, instrument_id: int, data_version_id: int) -> dict:
    now = datetime.utcnow()
    return {
        "instrument_id": instrument_id,
        "trade_date": stg_row["trade_date"],
        "price_adjust_type": stg_row["price_adjust_type"],
        "open": stg_row["open"],
        "high": stg_row["high"],
        "low": stg_row["low"],
        "close": stg_row["close"],
        "pre_close": stg_row.get("pre_close"),
        "pct_change": stg_row.get("pct_change"),
        "price_change": stg_row.get("price_change"),
        "volume": stg_row.get("volume"),
        "amount": stg_row.get("turnover"),
        "turnover_rate": stg_row.get("turnover_rate"),
        "is_suspended": stg_row.get("suspended_flag"),
        "source_provider": stg_row["provider_name"],
        "data_version_id": data_version_id,
        "created_at": now,
        "updated_at": now,
    }