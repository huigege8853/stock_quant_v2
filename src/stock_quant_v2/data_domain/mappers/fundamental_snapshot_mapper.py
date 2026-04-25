from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal

from stock_quant_v2.data_domain.dto.fundamental_snapshot import FundamentalSnapshotDTO


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _json_safe(value):
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _hash_payload(payload: dict) -> str:
    body = json.dumps(_json_safe(payload), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def dto_to_raw_fundamental_snapshot_dict(
    dto: FundamentalSnapshotDTO,
    sync_run_id: int,
    batch_id: int,
) -> dict:
    return {
        "provider_name": dto.provider_name,
        "dataset_code": "fundamental_snapshot",
        "provider_record_key": dto.provider_record_key,
        "symbol": dto.ticker,
        "trade_date": dto.trade_date,
        "batch_id": batch_id,
        "sync_run_id": sync_run_id,
        "request_params": {
            "exchange_code": dto.exchange_code,
            "ticker": dto.ticker,
            "trade_date": dto.trade_date.isoformat(),
            "snapshot_type": dto.snapshot_type,
        },
        "payload_json": _json_safe(dto.raw_payload),
        "payload_hash": _hash_payload(dto.raw_payload),
        "provider_update_ts": None,
        "ingested_at": utc_now(),
    }


def dto_to_staging_fundamental_snapshot_dict(
    dto: FundamentalSnapshotDTO,
    sync_run_id: int,
    batch_id: int,
    raw_record_id: int,
) -> dict:
    return {
        "sync_run_id": sync_run_id,
        "batch_id": batch_id,
        "provider_name": dto.provider_name,
        "dataset_code": "fundamental_snapshot",
        "market_code": dto.market_code,
        "exchange_code": dto.exchange_code,
        "ticker": dto.ticker,
        "vendor_symbol": dto.vendor_symbol,
        "trade_date": dto.trade_date,
        "snapshot_type": dto.snapshot_type,
        "pe_ttm": dto.pe_ttm,
        "pb": dto.pb,
        "ps_ttm": dto.ps_ttm,
        "dv_ttm": dto.dv_ttm,
        "total_mv": dto.total_mv,
        "circ_mv": dto.circ_mv,
        "roe": dto.roe,
        "roa": dto.roa,
        "gross_margin": dto.gross_margin,
        "net_profit_yoy": dto.net_profit_yoy,
        "report_period": dto.report_period,
        "announcement_date": dto.announcement_date,
        "provider_record_key": dto.provider_record_key,
        "raw_record_id": raw_record_id,
    }


def staging_to_core_fundamental_snapshot_dict(
    stg_row: dict,
    instrument_id: int,
    data_version_id: int,
    source_provider: str,
) -> dict:
    return {
        "instrument_id": instrument_id,
        "trade_date": stg_row["trade_date"],
        "snapshot_type": stg_row["snapshot_type"],
        "pe_ttm": stg_row.get("pe_ttm"),
        "pb": stg_row.get("pb"),
        "ps_ttm": stg_row.get("ps_ttm"),
        "dv_ttm": stg_row.get("dv_ttm"),
        "total_mv": stg_row.get("total_mv"),
        "circ_mv": stg_row.get("circ_mv"),
        "roe": stg_row.get("roe"),
        "roa": stg_row.get("roa"),
        "gross_margin": stg_row.get("gross_margin"),
        "net_profit_yoy": stg_row.get("net_profit_yoy"),
        "report_period": stg_row.get("report_period"),
        "announcement_date": stg_row.get("announcement_date"),
        "source_provider": source_provider,
        "data_version_id": data_version_id,
    }