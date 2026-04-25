from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any

import requests


class SinaClient:
    def __init__(self, api_client: Any = None) -> None:
        self.api_client = api_client
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Referer": "https://finance.sina.com.cn/",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/123.0.0.0 Safari/537.36"
                ),
            }
        )

    def fetch_daily_bar_by_symbol(
        self,
        exchange_code: str,
        ticker: str,
        trade_date: date,
    ) -> list[dict[str, Any]]:
        _ = exchange_code, ticker, trade_date
        return []

    def fetch_market_index_bar_by_symbol(
            self,
            index_code: str,
            trade_date: date,
    ) -> list[dict[str, Any]]:
        symbol = self._to_sina_symbol(index_code)

        url = "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
        params = {
            "symbol": symbol,
            "scale": "240",
            "ma": "no",
            "datalen": "1023",
        }

        response = self.session.get(url, params=params, timeout=20)
        response.raise_for_status()
        text = response.text.strip()

        if text in ("", "null", "NULL"):
            return []

        try:
            data = json.loads(text)
        except Exception:
            normalized = re.sub(r'([{,])\s*([A-Za-z_][A-Za-z0-9_]*)\s*:', r'\1"\2":', text)
            normalized = normalized.replace("'", '"')
            data = json.loads(normalized)

        if not isinstance(data, list):
            return []

        target = trade_date.isoformat()
        rows = []
        for item in data:
            day_text = str(item.get("day", "")).strip()[:10]
            if day_text != target:
                continue

            rows.append(
                {
                    "index_code": index_code,
                    "exchange_code": self._infer_exchange_code(index_code),
                    "trade_date": trade_date,
                    "open": self._to_number(item.get("open")),
                    "high": self._to_number(item.get("high")),
                    "low": self._to_number(item.get("low")),
                    "close": self._to_number(item.get("close")),
                    "volume": self._to_number(item.get("volume")),
                    "turnover": self._to_number(item.get("amount") or item.get("turnover")),
                    "index_name": None,
                    "index_type": None,
                    "provider_update_ts": None,
                    "raw_payload": item,
                }
            )
        return rows

    def _http_get_json_like(self, url: str, params: dict[str, Any]) -> Any:
        response = self.session.get(url, params=params, timeout=20)
        response.raise_for_status()
        text = response.text.strip()

        if text in ("null", "NULL", ""):
            return []

        # 兼容某些接口返回非标准 JSON 的情况
        try:
            return json.loads(text)
        except Exception:
            pass

        # 给未加引号的 key 补引号；常见于旧新浪接口
        normalized = re.sub(r'([{,])\s*([A-Za-z_][A-Za-z0-9_]*)\s*:', r'\\1"\\2":', text)
        normalized = normalized.replace("'", '"')
        try:
            return json.loads(normalized)
        except Exception:
            return []

    @staticmethod
    def _to_sina_symbol(index_code: str) -> str:
        code = index_code.strip().upper()
        if code.endswith(".SH"):
            return "sh" + code[:6]
        if code.endswith(".SZ"):
            return "sz" + code[:6]
        if code.startswith(("sh", "sz")):
            return code.lower()
        raise ValueError(f"unsupported index_code format: {index_code}")

    @staticmethod
    def _infer_exchange_code(index_code: str) -> str | None:
        code = index_code.upper()
        if code.endswith(".SH") or code.startswith("SH"):
            return "SSE"
        if code.endswith(".SZ") or code.startswith("SZ"):
            return "SZSE"
        return None

    @staticmethod
    def _extract_trade_date(item: dict[str, Any]) -> str | None:
        for key in ("day", "date"):
            value = item.get(key)
            if not value:
                continue
            text = str(value).strip()
            # 兼容 2024-01-03 00:00:00
            if len(text) >= 10:
                return text[:10]
        return None

    @staticmethod
    def _to_number(value):
        if value in (None, "", "null", "-", "--"):
            return None
        try:
            return float(value)
        except Exception:
            return None


def _utcnow():
    return datetime.utcnow()
