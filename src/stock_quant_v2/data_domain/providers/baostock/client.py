from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from typing import Any


def _to_bs_code(exchange_code: str, ticker: str) -> str:
    mapping = {
        "SSE": "sh",
        "SZSE": "sz",
        "BSE": "bj",
    }
    return f"{mapping[exchange_code]}.{ticker}"


def _parse_bs_code(code: str) -> tuple[str, str]:
    prefix, ticker = code.split(".")
    exchange_map = {
        "sh": "SSE",
        "sz": "SZSE",
        "bj": "BSE",
    }
    return ticker, exchange_map[prefix.lower()]


def _is_baostock_connection_error_message(message: str | None) -> bool:
    if not message:
        return False

    text = str(message).lower()
    keywords = [
        "10054",
        "接收数据异常",
        "远程主机强迫关闭了一个现有的连接",
        "forcibly closed",
        "connection aborted",
        "connection reset",
        "broken pipe",
        "please reconnect",
        "socket",
    ]
    return any(keyword.lower() in text for keyword in keywords)


class BaoStockClient:
    def __init__(self, api_client: Any) -> None:
        self.api_client = api_client

    def _safe_logout(self) -> None:
        if self.api_client is None:
            return
        try:
            logout = getattr(self.api_client, "logout", None)
            if callable(logout):
                logout()
        except Exception:
            pass

    def _reconnect(self) -> None:
        if self.api_client is None:
            raise RuntimeError("baostock api_client is None; cannot reconnect")

        self._safe_logout()

        login = getattr(self.api_client, "login", None)
        if not callable(login):
            raise RuntimeError("baostock api_client does not support login()")

        lg = login()
        if getattr(lg, "error_code", "0") != "0":
            raise RuntimeError(
                f"baostock reconnect failed: "
                f"error_code={getattr(lg, 'error_code', None)} "
                f"error_msg={getattr(lg, 'error_msg', None)}"
            )

    def _run_with_reconnect(self, action, *, max_retries: int = 2, retry_sleep_seconds: float = 0.3):
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                return action()
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt >= max_retries:
                    raise

                if not _is_baostock_connection_error_message(str(exc)):
                    raise

                self._reconnect()
                time.sleep(retry_sleep_seconds)

        if last_error is not None:
            raise last_error

        raise RuntimeError("baostock action failed without explicit error")

    def _query_history_k_data_plus_once(
        self,
        code: str,
        trade_date: date,
    ):
        if self.api_client is None:
            raise RuntimeError("baostock api_client is None")

        rs = self.api_client.query_history_k_data_plus(
            code,
            "date,code,open,high,low,close,preclose,volume,amount,pctChg",
            start_date=trade_date.isoformat(),
            end_date=trade_date.isoformat(),
            frequency="d",
            adjustflag="3",
        )

        error_code = getattr(rs, "error_code", None)
        error_msg = getattr(rs, "error_msg", None)

        if error_code != "0":
            raise RuntimeError(
                f"baostock query_history_k_data_plus failed: "
                f"error_code={error_code}, error_msg={error_msg}"
            )

        return rs

    def _query_adjust_factor_once(
        self,
        code: str,
        start_date: date,
        end_date: date,
    ):
        if self.api_client is None:
            raise RuntimeError("baostock api_client is None")

        rs = self.api_client.query_adjust_factor(
            code=code,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
        )

        error_code = getattr(rs, "error_code", None)
        error_msg = getattr(rs, "error_msg", None)

        if error_code != "0":
            raise RuntimeError(
                f"baostock query_adjust_factor failed: "
                f"error_code={error_code}, error_msg={error_msg}"
            )

        return rs

    def fetch_instruments(self) -> list[dict[str, Any]]:
        if self.api_client is None:
            return []

        rs = self.api_client.query_stock_basic()
        error_code = getattr(rs, "error_code", None)
        error_msg = getattr(rs, "error_msg", None)
        if error_code != "0":
            raise RuntimeError(
                f"baostock query_stock_basic failed: "
                f"error_code={error_code}, error_msg={error_msg}"
            )

        rows: list[dict[str, Any]] = []

        while rs.error_code == "0" and rs.next():
            row = rs.get_row_data()
            code = row[0]
            code_name = row[1]
            ipo_date = row[2]
            out_date = row[3]
            status = row[5] if len(row) > 5 else "1"

            ticker, exchange_code = _parse_bs_code(code)

            rows.append(
                {
                    "market_code": "CN_A",
                    "exchange_code": exchange_code,
                    "ticker": ticker,
                    "instrument_code": f"{ticker}.{exchange_code}",
                    "name": code_name,
                    "instrument_type": "UNKNOWN",
                    "currency": "CNY",
                    "list_date": _parse_date(ipo_date),
                    "delist_date": _parse_date(out_date),
                    "is_active": str(status) == "1",
                }
            )

        return rows

    def fetch_trading_calendar(
        self,
        exchange_code: str,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        if self.api_client is None:
            return []

        rs = self.api_client.query_trade_dates(
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
        )

        error_code = getattr(rs, "error_code", None)
        error_msg = getattr(rs, "error_msg", None)
        if error_code != "0":
            raise RuntimeError(
                f"baostock query_trade_dates failed: "
                f"error_code={error_code}, error_msg={error_msg}"
            )

        rows: list[dict[str, Any]] = []
        previous_open_date: date | None = None

        while rs.error_code == "0" and rs.next():
            row = rs.get_row_data()
            trade_date = _parse_date(row[0])
            is_open = str(row[1]) == "1"

            rows.append(
                {
                    "exchange_code": exchange_code,
                    "trade_date": trade_date,
                    "is_open": is_open,
                    "previous_trade_date": previous_open_date if is_open else None,
                    "next_trade_date": None,
                }
            )
            if is_open:
                previous_open_date = trade_date

        return rows

    def fetch_daily_bar(self, trade_date: date) -> list[dict[str, Any]]:
        if self.api_client is None:
            return []

        _ = trade_date
        return []

    def fetch_daily_bar_by_symbol(
        self,
        exchange_code: str,
        ticker: str,
        trade_date: date,
    ) -> list[dict[str, Any]]:
        if self.api_client is None:
            return []

        code = _to_bs_code(exchange_code, ticker)

        rs = self._run_with_reconnect(
            lambda: self._query_history_k_data_plus_once(code=code, trade_date=trade_date),
            max_retries=2,
            retry_sleep_seconds=0.3,
        )

        rows: list[dict[str, Any]] = []
        while rs.error_code == "0" and rs.next():
            row = rs.get_row_data()
            rows.append(
                {
                    "ticker": ticker,
                    "exchange_code": exchange_code,
                    "ts_code": None,
                    "trade_date": trade_date,
                    "open": _to_number(row[2]),
                    "high": _to_number(row[3]),
                    "low": _to_number(row[4]),
                    "close": _to_number(row[5]),
                    "pre_close": _to_number(row[6]),
                    "volume": _to_number(row[7]),
                    "turnover": _to_number(row[8]),
                    "amplitude": None,
                    "pct_change": _to_number(row[9]),
                    "price_change": None,
                    "turnover_rate": None,
                    "suspended_flag": False,
                    "provider_fetched_at": datetime.utcnow().isoformat(),
                }
            )

        return rows

    def fetch_adjust_factor_by_symbol(
        self,
        exchange_code: str,
        ticker: str,
        trade_date: date,
    ) -> list[dict[str, Any]]:
        if self.api_client is None:
            return []

        code = _to_bs_code(exchange_code, ticker)
        start_date = trade_date - timedelta(days=365 * 2)

        rs = self._run_with_reconnect(
            lambda: self._query_adjust_factor_once(
                code=code,
                start_date=start_date,
                end_date=trade_date,
            ),
            max_retries=2,
            retry_sleep_seconds=0.3,
        )

        candidates: list[dict[str, Any]] = []

        while rs.error_code == "0" and rs.next():
            row = rs.get_row_data()

            row_trade_date = None
            if len(row) > 1:
                row_trade_date = _parse_date(row[1])

            if row_trade_date is None:
                continue

            if row_trade_date > trade_date:
                continue

            adjust_factor = None
            if len(row) > 4:
                adjust_factor = _to_number(row[4])
            elif len(row) > 3:
                adjust_factor = _to_number(row[3])
            elif len(row) > 2:
                adjust_factor = _to_number(row[2])

            candidates.append(
                {
                    "ticker": ticker,
                    "exchange_code": exchange_code,
                    "vendor_symbol": code,
                    "trade_date": row_trade_date,
                    "adjust_factor": adjust_factor,
                    "provider_fetched_at": datetime.utcnow().isoformat(),
                }
            )

        if not candidates:
            return []

        latest = max(candidates, key=lambda x: x["trade_date"])

        final_rows = [
            {
                "ticker": ticker,
                "exchange_code": exchange_code,
                "vendor_symbol": code,
                "trade_date": trade_date,
                "adjust_factor": latest["adjust_factor"],
                "provider_fetched_at": datetime.utcnow().isoformat(),
                "factor_source_trade_date": latest["trade_date"].isoformat(),
            }
        ]

        return final_rows


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def _to_number(value: str | None):
    if value in (None, "", "null"):
        return None
    try:
        return float(value)
    except Exception:
        return None