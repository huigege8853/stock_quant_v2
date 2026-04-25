from __future__ import annotations

from stock_quant_v2.config.settings import settings


class TushareApiClientAdapter:
    """
    这里是一个轻适配层，统一包住真实 tushare pro client。
    后续如果你要做限流、重试、日志、缓存，都可以加在这里。
    """

    def __init__(self, pro_client) -> None:
        self._pro = pro_client

    def daily(self, **kwargs):
        return self._pro.daily(**kwargs)

    def daily_basic(self, **kwargs):
        return self._pro.daily_basic(**kwargs)

    def stock_basic(self, **kwargs):
        return self._pro.stock_basic(**kwargs)

    def trade_cal(self, **kwargs):
        return self._pro.trade_cal(**kwargs)


def build_tushare_api_client():
    if not settings.tushare_token:
        raise ValueError("TUSHARE_TOKEN is not configured")

    try:
        import tushare as ts
    except ImportError as exc:  # noqa: BLE001
        raise ImportError("tushare is not installed. Please add it to pyproject.toml") from exc

    ts.set_token(settings.tushare_token)
    pro = ts.pro_api()
    return TushareApiClientAdapter(pro)