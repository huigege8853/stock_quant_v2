from __future__ import annotations

from datetime import date, datetime
from typing import Any


class AkshareClient:
    def __init__(self, api_client: Any = None) -> None:
        self.api_client = api_client

    def fetch_instruments(self) -> list[dict[str, Any]]:
        """
        输出统一字段：
        - market_code
        - exchange_code
        - ticker
        - instrument_code
        - name
        - instrument_type
        - currency
        - list_date
        - delist_date
        - is_active
        """
        try:
            import akshare as ak
        except ImportError:
            return []

        rows: list[dict[str, Any]] = []

        try:
            df = ak.stock_info_a_code_name()
            records = df.to_dict("records")
        except Exception:
            return []

        for row in records:
            code = str(row.get("code") or row.get("证券代码") or "")
            name = row.get("name") or row.get("证券简称") or row.get("名称")
            if not code:
                continue

            exchange_code = _infer_exchange_code(code)
            rows.append(
                {
                    "market_code": "CN_A",
                    "exchange_code": exchange_code,
                    "ticker": code,
                    "instrument_code": f"{code}.{exchange_code}",
                    "name": name or code,
                    "instrument_type": "EQUITY",
                    "currency": "CNY",
                    "list_date": None,
                    "delist_date": None,
                    "is_active": True,
                }
            )

        return rows

    def fetch_trading_calendar(
        self,
        exchange_code: str,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        try:
            import akshare as ak
        except ImportError:
            return []

        try:
            _ = ak, exchange_code, start_date, end_date
            return []
        except Exception:
            return []

    def fetch_daily_bar_by_symbol(
        self,
        exchange_code: str,
        ticker: str,
        trade_date: date,
    ) -> list[dict[str, Any]]:
        try:
            import akshare as ak
        except ImportError:
            return []

        try:
            df = ak.stock_zh_a_hist(
                symbol=ticker,
                period="daily",
                start_date=trade_date.strftime("%Y%m%d"),
                end_date=trade_date.strftime("%Y%m%d"),
                adjust="",
            )
        except Exception:
            return []

        records = df.to_dict("records") if hasattr(df, "to_dict") else list(df)
        rows: list[dict[str, Any]] = []

        for row in records:
            rows.append(
                {
                    "ticker": ticker,
                    "exchange_code": exchange_code,
                    "ts_code": None,
                    "trade_date": trade_date,
                    "open": _to_number(row.get("开盘")),
                    "high": _to_number(row.get("最高")),
                    "low": _to_number(row.get("最低")),
                    "close": _to_number(row.get("收盘")),
                    "pre_close": _to_number(row.get("昨收")),
                    "volume": _to_number(row.get("成交量")),
                    "turnover": _to_number(row.get("成交额")),
                    "amplitude": _to_number(row.get("振幅")),
                    "pct_change": _to_number(row.get("涨跌幅")),
                    "price_change": _to_number(row.get("涨跌额")),
                    "turnover_rate": _to_number(row.get("换手率")),
                    "suspended_flag": False,
                    "provider_fetched_at": datetime.utcnow(),
                }
            )

        return rows

    def fetch_adjust_factor_by_symbol(
        self,
        exchange_code: str,
        ticker: str,
        trade_date: date,
    ) -> list[dict[str, Any]]:
        _ = exchange_code

        try:
            import akshare as ak
        except ImportError:
            return []

        try:
            df = ak.stock_zh_a_daily(
                symbol=ticker,
                start_date=trade_date.strftime("%Y%m%d"),
                end_date=trade_date.strftime("%Y%m%d"),
                adjust="qfq-factor",
            )
        except Exception:
            return []

        records = df.to_dict("records") if hasattr(df, "to_dict") else list(df)
        rows: list[dict[str, Any]] = []

        for row in records:
            row_date = row.get("date") or row.get("日期")
            if row_date is None:
                continue

            row_date_text = str(row_date)[:10]
            if row_date_text != trade_date.isoformat():
                continue

            factor = (
                row.get("qfq_factor")
                or row.get("hfq_factor")
                or row.get("adjust_factor")
                or row.get("复权因子")
            )

            rows.append(
                {
                    "ticker": ticker,
                    "exchange_code": exchange_code,
                    "vendor_symbol": ticker,
                    "trade_date": trade_date,
                    "adjust_factor": _to_number(factor),
                    "provider_fetched_at": datetime.utcnow().isoformat(),
                }
            )

        return rows

    def fetch_fundamental_snapshot_by_symbol(
        self,
        exchange_code: str,
        ticker: str,
        trade_date: date,
    ) -> list[dict[str, Any]]:
        try:
            import akshare as ak
        except ImportError:
            return []

        valuation_symbols = [
            ticker,
            _to_akshare_prefixed_symbol(exchange_code, ticker),
        ]

        for symbol in valuation_symbols:
            if not symbol:
                continue
            try:
                df = ak.stock_zh_valuation_baidu(symbol=symbol)
                records = df.to_dict("records") if hasattr(df, "to_dict") else list(df)
            except Exception:
                continue

            rows: list[dict[str, Any]] = []

            for row in records:
                row_date = (
                    row.get("date")
                    or row.get("日期")
                    or row.get("交易日")
                    or row.get("trade_date")
                )
                if row_date is None:
                    continue

                row_date_text = str(row_date)[:10]
                if row_date_text != trade_date.isoformat():
                    continue

                rows.append(
                    {
                        "ticker": ticker,
                        "exchange_code": exchange_code,
                        "vendor_symbol": symbol,
                        "trade_date": trade_date,
                        "snapshot_type": "valuation_daily",
                        "pe_ttm": _to_number(
                            row.get("pe_ttm")
                            or row.get("市盈率TTM")
                            or row.get("市盈率")
                            or row.get("PE")
                        ),
                        "pb": _to_number(
                            row.get("pb")
                            or row.get("市净率")
                            or row.get("PB")
                        ),
                        "ps_ttm": _to_number(
                            row.get("ps_ttm")
                            or row.get("市销率TTM")
                            or row.get("市销率")
                            or row.get("PS")
                        ),
                        "dv_ttm": _to_number(
                            row.get("dv_ttm")
                            or row.get("股息率TTM")
                            or row.get("股息率")
                            or row.get("DV")
                        ),
                        "total_mv": _to_number(
                            row.get("total_mv")
                            or row.get("总市值")
                        ),
                        "circ_mv": _to_number(
                            row.get("circ_mv")
                            or row.get("流通市值")
                        ),
                        "roe": _to_number(row.get("roe") or row.get("ROE")),
                        "roa": _to_number(row.get("roa") or row.get("ROA")),
                        "gross_margin": _to_number(
                            row.get("gross_margin")
                            or row.get("销售毛利率")
                        ),
                        "net_profit_yoy": _to_number(
                            row.get("net_profit_yoy")
                            or row.get("净利润同比")
                        ),
                        "report_period": row.get("report_period") or row.get("报告期"),
                        "announcement_date": row.get("announcement_date") or row.get("公告日期"),
                        "provider_fetched_at": datetime.utcnow().isoformat(),
                    }
                )

            if rows:
                return rows

        try:
            df = ak.stock_individual_info_em(symbol=ticker)
            records = df.to_dict("records") if hasattr(df, "to_dict") else list(df)
        except Exception:
            return []

        if not records:
            return []

        kv: dict[str, Any] = {}
        for row in records:
            key = str(
                row.get("item")
                or row.get("项目")
                or row.get("指标")
                or ""
            ).strip()
            value = row.get("value") or row.get("值")
            if key:
                kv[key] = value

        result = {
            "ticker": ticker,
            "exchange_code": exchange_code,
            "vendor_symbol": ticker,
            "trade_date": trade_date,
            "snapshot_type": "valuation_daily",
            "pe_ttm": _to_number(
                kv.get("市盈率")
                or kv.get("市盈率(动)")
                or kv.get("PE")
            ),
            "pb": _to_number(
                kv.get("市净率")
                or kv.get("PB")
            ),
            "ps_ttm": _to_number(
                kv.get("市销率")
                or kv.get("PS")
            ),
            "dv_ttm": _to_number(
                kv.get("股息率")
                or kv.get("DV")
            ),
            "total_mv": _to_number(kv.get("总市值")),
            "circ_mv": _to_number(kv.get("流通市值")),
            "roe": None,
            "roa": None,
            "gross_margin": None,
            "net_profit_yoy": None,
            "report_period": None,
            "announcement_date": None,
            "provider_fetched_at": datetime.utcnow().isoformat(),
        }

        if all(
            result[field] is None
            for field in ["pe_ttm", "pb", "ps_ttm", "dv_ttm", "total_mv", "circ_mv"]
        ):
            return []

        return [result]


def _to_akshare_prefixed_symbol(exchange_code: str, ticker: str) -> str:
    exchange_code = str(exchange_code).upper()
    if exchange_code == "SSE":
        return f"sh{ticker}"
    if exchange_code == "SZSE":
        return f"sz{ticker}"
    if exchange_code == "BSE":
        return f"bj{ticker}"
    return ticker


def _infer_exchange_code(ticker: str) -> str:
    if ticker.startswith(("600", "601", "603", "605", "688", "689")):
        return "SSE"
    if ticker.startswith(("000", "001", "002", "003", "300", "301")):
        return "SZSE"
    if ticker.startswith(("430", "830", "831", "832", "833", "835", "836", "837", "838", "839")):
        return "BSE"
    return "SZSE"


def _to_number(value):
    if value in (None, "", "null", "-", "--"):
        return None
    try:
        text = str(value).replace(",", "").replace("%", "")
        return float(text)
    except Exception:
        return None