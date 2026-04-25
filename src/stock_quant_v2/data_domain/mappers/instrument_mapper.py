from __future__ import annotations

from datetime import date, datetime
from typing import Any


CN_A_MARKET_CODE = "CN_A"


def _normalize_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_ticker(value: Any) -> str | None:
    text = _normalize_str(value)
    if text is None:
        return None

    if "." in text:
        text = text.split(".", 1)[0].strip()

    if text.isdigit():
        return text.zfill(6)
    return text


def _parse_date(value: Any) -> date | None:
    if value in (None, "", "None"):
        return None

    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    text = str(value).strip()
    if not text:
        return None

    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    return None


def _normalize_exchange_code(value: Any) -> str | None:
    text = _normalize_str(value)
    if text is None:
        return None

    text = text.upper()
    mapping = {
        "SH": "SSE",
        "SSE": "SSE",
        "XSHG": "SSE",
        "SS": "SSE",
        "SZ": "SZSE",
        "SZSE": "SZSE",
        "XSHE": "SZSE",
        "BJ": "BSE",
        "BSE": "BSE",
    }
    return mapping.get(text, text)


def infer_exchange_code_from_ticker(ticker: str) -> str:
    if ticker.startswith(("600", "601", "603", "605", "688", "689")):
        return "SSE"

    if ticker.startswith(("000", "001", "002", "003", "300", "301")):
        return "SZSE"

    if ticker.startswith(("430", "830", "831", "832", "833", "835", "836", "837", "838", "839")):
        return "BSE"

    raise ValueError(f"cannot infer exchange_code from ticker: {ticker}")


def infer_instrument_type(ticker: str) -> str:
    # 当前 instrument 同步先只稳住股票
    return "EQUITY"


def is_supported_equity_ticker(ticker: str) -> bool:
    try:
        infer_exchange_code_from_ticker(ticker)
        return True
    except ValueError:
        return False


def _infer_is_active(raw_row: dict[str, Any], delist_date: date | None) -> bool:
    """
    彻底修复点：
    不再盲信 provider 传回来的 is_active。
    对股票主数据，优先按 delist_date 判断：
    - 有 delist_date -> False
    - 无 delist_date -> True
    """
    if delist_date is not None:
        return False
    return True


def normalize_instrument_row(raw_row: dict[str, Any]) -> dict[str, Any]:
    ticker = _normalize_ticker(
        raw_row.get("ticker")
        or raw_row.get("symbol")
        or raw_row.get("code")
        or raw_row.get("stock_code")
        or raw_row.get("ts_code")
    )
    if not ticker:
        raise ValueError(f"ticker missing in raw row: {raw_row}")

    # 当前 instrument 股票链路只接股票代码
    if not is_supported_equity_ticker(ticker):
        raise ValueError(f"unsupported ticker for equity instrument sync: {ticker}")

    exchange_code = _normalize_exchange_code(raw_row.get("exchange_code"))

    if exchange_code is None:
        ts_code = _normalize_str(raw_row.get("ts_code"))
        if ts_code and "." in ts_code:
            suffix = ts_code.split(".", 1)[1].upper()
            exchange_code = _normalize_exchange_code(suffix)

    inferred_exchange_code = infer_exchange_code_from_ticker(ticker)

    # 强制以前缀推断为准，杜绝 000001 -> SSE 这种脏数据再次落库
    if exchange_code is None or exchange_code != inferred_exchange_code:
        exchange_code = inferred_exchange_code

    name = _normalize_str(
        raw_row.get("name")
        or raw_row.get("display_name")
        or raw_row.get("instrument_name")
        or raw_row.get("stock_name")
        or raw_row.get("full_name")
    )
    if not name:
        raise ValueError(f"name missing for ticker={ticker}, raw row={raw_row}")

    instrument_type = _normalize_str(raw_row.get("instrument_type")) or infer_instrument_type(ticker)

    instrument_code = _normalize_str(raw_row.get("instrument_code"))
    if instrument_code is None:
        instrument_code = f"{ticker}.{exchange_code}"

    currency = _normalize_str(raw_row.get("currency")) or "CNY"
    list_date = _parse_date(raw_row.get("list_date") or raw_row.get("ipo_date"))
    delist_date = _parse_date(raw_row.get("delist_date"))

    is_active = _infer_is_active(raw_row, delist_date)

    return {
        "market_code": _normalize_str(raw_row.get("market_code")) or CN_A_MARKET_CODE,
        "exchange_code": exchange_code,
        "ticker": ticker,
        "name": name,
        "instrument_type": instrument_type,
        "instrument_code": instrument_code,
        "currency": currency,
        "list_date": list_date,
        "delist_date": delist_date,
        "is_active": is_active,
    }