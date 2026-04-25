from __future__ import annotations

import io
import time
from contextlib import redirect_stderr, redirect_stdout


class BaoStockApiClientAdapter:
    def __init__(self, bs_module) -> None:
        self._bs = bs_module

    def query_stock_basic(self, *args, **kwargs):
        return self._bs.query_stock_basic(*args, **kwargs)

    def query_trade_dates(self, *args, **kwargs):
        return self._bs.query_trade_dates(*args, **kwargs)

    def query_history_k_data_plus(self, *args, **kwargs):
        return self._bs.query_history_k_data_plus(*args, **kwargs)

    def query_adjust_factor(self, *args, **kwargs):
        return self._bs.query_adjust_factor(*args, **kwargs)

    def login(self):
        return self._bs.login()

    def logout(self):
        return self._bs.logout()


def build_baostock_api_client(
    max_attempts: int = 3,
    sleep_seconds: float = 2.0,
):
    try:
        import baostock as bs
    except ImportError as exc:  # noqa: BLE001
        raise ImportError("baostock is not installed. Please add it to pyproject.toml") from exc

    last_error_code = None
    last_error_msg = None

    for attempt in range(1, max_attempts + 1):
        try:
            # 先尝试清理旧会话，避免上一次残留状态影响
            try:
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    bs.logout()
            except Exception:
                pass

            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                lg = bs.login()

            error_code = str(getattr(lg, "error_code", ""))
            error_msg = str(getattr(lg, "error_msg", ""))

            if error_code == "0":
                return BaoStockApiClientAdapter(bs)

            last_error_code = error_code
            last_error_msg = error_msg
        except Exception as exc:  # noqa: BLE001
            last_error_code = "EXCEPTION"
            last_error_msg = f"{type(exc).__name__}: {exc}"

        if attempt < max_attempts:
            time.sleep(sleep_seconds)

    raise ValueError(
        f"baostock login failed after {max_attempts} attempts: "
        f"error_code={last_error_code}, error_msg={last_error_msg}"
    )