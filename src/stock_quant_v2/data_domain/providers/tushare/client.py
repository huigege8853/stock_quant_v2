from __future__ import annotations

from datetime import date, datetime
from typing import Any


def _format_trade_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def _parse_ts_code(ts_code: str) -> tuple[str, str]:
    """
    600000.SH -> ("600000", "SSE")
    000001.SZ -> ("000001", "SZSE")
    430001.BJ -> ("430001", "BSE")
    """
    code, suffix = ts_code.split(".")
    exchange_map = {
        "SH": "SSE",
        "SZ": "SZSE",
        "BJ": "BSE",
    }
    return code, exchange_map.get(suffix.upper(), suffix.upper())


class TushareClient:
    def __init__(self, api_client: Any) -> None:
        self.api_client = api_client

    def fetch_daily_bar(self, trade_date: date) -> list[dict[str, Any]]:
        """
        输出统一原始行字段：
        - ticker
        - exchange_code
        - ts_code
        - open/high/low/close/pre_close
        - volume
        - turnover
        - amplitude
        - pct_change
        - price_change
        - turnover_rate
        - suspended_flag
        """
        if self.api_client is None:
            return []

        trade_date_str = _format_trade_date(trade_date)

        # 方案说明：
        # 1. daily：日线 OHLCV
        # 2. daily_basic：换手率等扩展指标
        # 3. 按 ts_code 合并
        #
        # 真实接入时请按你自己的 tushare client 实现改造。
        daily_rows: list[dict[str, Any]] = []
        daily_basic_rows: list[dict[str, Any]] = []

        # TODO: 替换为真实 SDK 调用
        # daily_df = self.api_client.daily(trade_date=trade_date_str)
        # daily_basic_df = self.api_client.daily_basic(trade_date=trade_date_str)

        # 示例：兼容 DataFrame / list[dict]
        if hasattr(self.api_client, "daily"):
            daily_df = self.api_client.daily(trade_date=trade_date_str)
            daily_rows = daily_df.to_dict("records") if hasattr(daily_df, "to_dict") else list(daily_df)

        if hasattr(self.api_client, "daily_basic"):
            daily_basic_df = self.api_client.daily_basic(trade_date=trade_date_str)
            daily_basic_rows = daily_basic_df.to_dict("records") if hasattr(daily_basic_df, "to_dict") else list(daily_basic_df)

        basic_by_ts_code = {str(row["ts_code"]): row for row in daily_basic_rows if row.get("ts_code")}

        merged_rows: list[dict[str, Any]] = []
        for row in daily_rows:
            ts_code = str(row["ts_code"])
            ticker, exchange_code = _parse_ts_code(ts_code)
            basic = basic_by_ts_code.get(ts_code, {})

            merged_rows.append(
                {
                    "ticker": ticker,
                    "exchange_code": exchange_code,
                    "ts_code": ts_code,
                    "trade_date": trade_date,
                    "open": row.get("open"),
                    "high": row.get("high"),
                    "low": row.get("low"),
                    "close": row.get("close"),
                    "pre_close": row.get("pre_close"),
                    # tushare daily 常见字段 vol/amount
                    # vol 单位依 provider 可能不同，V2 首期先原样入标准层
                    "volume": row.get("vol"),
                    "turnover": row.get("amount"),
                    "amplitude": None,  # tushare 原生未必直接给
                    "pct_change": row.get("pct_chg"),
                    "price_change": row.get("change"),
                    "turnover_rate": basic.get("turnover_rate"),
                    # 首期简单规则：close 缺失且成交量为 0 时视作可能停牌
                    "suspended_flag": bool(
                        (row.get("close") in (None, 0) and (row.get("vol") in (None, 0)))
                    ),
                    "provider_fetched_at": datetime.utcnow(),
                }
            )

        return merged_rows

    def fetch_instruments(self) -> list[dict[str, Any]]:
        """
        输出统一 instrument 原始行字段：
        - market_code
        - exchange_code
        - ticker
        - name
        - full_name
        - instrument_type
        - currency
        - lot_size
        - list_date
        - delist_date
        - board_code
        - is_active
        """
        if self.api_client is None:
            return []

        rows: list[dict[str, Any]] = []

        if hasattr(self.api_client, "stock_basic"):
            df = self.api_client.stock_basic(exchange="", list_status="L,D,P", fields="ts_code,symbol,name,area,industry,market,list_date,delist_date")
            records = df.to_dict("records") if hasattr(df, "to_dict") else list(df)
            for row in records:
                ticker, exchange_code = _parse_ts_code(str(row["ts_code"]))
                rows.append(
                    {
                        "market_code": "CN_A",
                        "exchange_code": exchange_code,
                        "ticker": ticker,
                        "name": row.get("name"),
                        "full_name": row.get("name"),
                        "instrument_type": "EQUITY",
                        "currency": "CNY",
                        "lot_size": 100,
                        "list_date": _parse_yyyymmdd(row.get("list_date")),
                        "delist_date": _parse_yyyymmdd(row.get("delist_date")),
                        "board_code": _map_board_code(row.get("market")),
                        "is_active": not bool(row.get("delist_date")),
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

        exchange_map = {"SSE": "SSE", "SZSE": "SZSE", "BSE": "BSE"}
        rows: list[dict[str, Any]] = []

        if hasattr(self.api_client, "trade_cal"):
            df = self.api_client.trade_cal(
                exchange=exchange_map[exchange_code],
                start_date=_format_trade_date(start_date),
                end_date=_format_trade_date(end_date),
            )
            records = df.to_dict("records") if hasattr(df, "to_dict") else list(df)

            for row in records:
                trade_date = _parse_yyyymmdd(row.get("cal_date"))
                is_open = str(row.get("is_open", "0")) == "1"
                rows.append(
                    {
                        "exchange_code": exchange_code,
                        "trade_date": trade_date,
                        "is_open": is_open,
                        "session_type": "FULL" if is_open else "CLOSED",
                        "previous_trade_date": _parse_yyyymmdd(row.get("pretrade_date")),
                        "next_trade_date": None,
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

        suffix_map = {
            "SSE": "SH",
            "SZSE": "SZ",
            "BSE": "BJ",
        }
        suffix = suffix_map.get(exchange_code)
        if suffix is None:
            return []

        ts_code = f"{ticker}.{suffix}"
        trade_date_str = _format_trade_date(trade_date)

        if not hasattr(self.api_client, "adj_factor"):
            return []

        df = self.api_client.adj_factor(ts_code=ts_code, trade_date=trade_date_str)

        records = df.to_dict("records") if hasattr(df, "to_dict") else list(df)
        rows: list[dict[str, Any]] = []

        for row in records:
            row_trade_date = _parse_yyyymmdd(row.get("trade_date"))
            if row_trade_date != trade_date:
                continue

            rows.append(
                {
                    "ticker": ticker,
                    "exchange_code": exchange_code,
                    "vendor_symbol": ts_code,
                    "trade_date": trade_date,
                    "adjust_factor": row.get("adj_factor"),
                    "provider_fetched_at": datetime.utcnow(),
                }
            )

        return rows


def _parse_yyyymmdd(value: Any) -> date | None:
    if value in (None, "", "None"):
        return None
    text = str(value)
    if len(text) != 8:
        return None
    return datetime.strptime(text, "%Y%m%d").date()


def _map_board_code(market: Any) -> str | None:
    if market is None:
        return None
    market_str = str(market).upper()
    mapping = {
        "主板": "MAIN",
        "中小板": "SME",
        "创业板": "CHINEXT",
        "科创板": "STAR",
        "北交所": "BSE",
    }
    return mapping.get(market_str)