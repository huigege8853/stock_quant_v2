from __future__ import annotations

import os

from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.research_domain.tasks.run_backtest import (
    create_backtest_result_placeholder_first_chain,
)


def _env_int(name: str, default: int | None = None) -> int | None:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def main() -> None:
    backtest_request_id = _env_int("M5_BACKTEST_REQUEST_ID")

    with SessionLocal() as session:
        result = create_backtest_result_placeholder_first_chain(
            session,
            backtest_request_id=backtest_request_id,
        )

    print(result)


if __name__ == "__main__":
    main()