from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

from sqlalchemy import text

from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.research_domain.constants import (
    DEFAULT_EXECUTION_PROFILE_CODE,
    DEFAULT_EXECUTION_PROFILE_VERSION,
    DEFAULT_INITIAL_CASH,
    DEFAULT_PORTFOLIO_CONSTRUCTION_MODE,
    DEFAULT_PORTFOLIO_CONSTRUCTION_PAYLOAD,
    DEFAULT_REBALANCE_FREQUENCY,
    DEFAULT_SIGNAL_EFFECTIVE_MODE,
)
from stock_quant_v2.research_domain.dto.backtest import BacktestRequestDTO
from stock_quant_v2.research_domain.tasks.run_backtest import (
    create_backtest_request_first_chain,
)


def _env_date(name: str, default: str) -> date:
    return date.fromisoformat(os.getenv(name, default))


def _env_int(name: str, default: int | None = None) -> int | None:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def _env_decimal(name: str, default: Decimal) -> Decimal:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return Decimal(value)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _latest_success_screen_source() -> tuple[int | None, int | None]:
    """返回最近一次成功 screen 的 (screen_request_id, signal_run_id)。

    仅作为 bootstrap 默认值，避免脚本必须手动传 env。
    业务服务层不依赖这个默认行为。
    """
    with SessionLocal() as session:
        row = session.execute(
            text(
                """
                select screen_request_id, signal_run_id
                from research_screen_result
                where result_status = 'SUCCESS'
                order by id desc
                limit 1
                """
            )
        ).first()

    if not row:
        return None, None

    return int(row[0]) if row[0] is not None else None, int(row[1]) if row[1] is not None else None


def main() -> None:
    latest_screen_request_id, latest_signal_run_id = _latest_success_screen_source()

    source_signal_run_id = _env_int(
        "M5_BACKTEST_SOURCE_SIGNAL_RUN_ID",
        latest_signal_run_id,
    )
    screen_request_id = _env_int(
        "M5_BACKTEST_SCREEN_REQUEST_ID",
        latest_screen_request_id,
    )

    benchmark_code = os.getenv("M5_BACKTEST_BENCHMARK_CODE")
    benchmark_version = os.getenv("M5_BACKTEST_BENCHMARK_VERSION")

    historical_replay_enabled = _env_bool("M5_HISTORICAL_REPLAY_ENABLED", False)
    historical_replay_start_date = os.getenv("M5_HISTORICAL_REPLAY_START_DATE")
    historical_replay_end_date = os.getenv("M5_HISTORICAL_REPLAY_END_DATE")
    historical_replay_top_n = _env_int("M5_HISTORICAL_REPLAY_TOP_N", 30)

    portfolio_construction_payload = dict(DEFAULT_PORTFOLIO_CONSTRUCTION_PAYLOAD)
    engine_payload = {
        "execution_enabled": historical_replay_enabled,
        "note": (
            "M5.11 historical signal replay P1 request"
            if historical_replay_enabled
            else "M5.4 skeleton only; backtrader not started"
        ),
    }
    if historical_replay_enabled:
        portfolio_construction_payload.update(
            {
                "m5_historical_replay_enabled": True,
                "historical_replay_top_n": historical_replay_top_n,
            }
        )
        engine_payload.update(
            {
                "execution_mode": "HISTORICAL_SIGNAL_REPLAY_P1",
                "m5_historical_replay_enabled": True,
                "historical_replay_start_date": historical_replay_start_date,
                "historical_replay_end_date": historical_replay_end_date,
                "historical_replay_top_n": historical_replay_top_n,
            }
        )
    dto = BacktestRequestDTO(
        strategy_code=os.getenv("M5_BACKTEST_STRATEGY_CODE", "alpha_selection"),
        version_code=os.getenv("M5_BACKTEST_VERSION_CODE", "v1"),
        start_date=_env_date("M5_BACKTEST_START_DATE", "2024-04-01"),
        end_date=_env_date("M5_BACKTEST_END_DATE", "2024-12-31"),
        execution_assumption_profile_code=os.getenv(
            "M5_BACKTEST_EXEC_PROFILE_CODE",
            DEFAULT_EXECUTION_PROFILE_CODE,
        ),
        execution_assumption_profile_version=os.getenv(
            "M5_BACKTEST_EXEC_PROFILE_VERSION",
            DEFAULT_EXECUTION_PROFILE_VERSION,
        ),
        source_signal_run_id=source_signal_run_id,
        screen_request_id=screen_request_id,
        benchmark_code=benchmark_code if benchmark_code else None,
        benchmark_version=benchmark_version if benchmark_version else None,
        initial_cash=_env_decimal("M5_BACKTEST_INITIAL_CASH", DEFAULT_INITIAL_CASH),
        rebalance_frequency=os.getenv(
            "M5_BACKTEST_REBALANCE_FREQUENCY",
            DEFAULT_REBALANCE_FREQUENCY,
        ),
        signal_effective_mode=os.getenv(
            "M5_BACKTEST_SIGNAL_EFFECTIVE_MODE",
            DEFAULT_SIGNAL_EFFECTIVE_MODE,
        ),
        portfolio_construction_mode=os.getenv(
            "M5_BACKTEST_PORTFOLIO_CONSTRUCTION_MODE",
            DEFAULT_PORTFOLIO_CONSTRUCTION_MODE,
        ),
        portfolio_construction_payload=portfolio_construction_payload,
        data_feed_payload={
            "source": "core_daily_bar",
            "adjustment": "post_adjusted_or_platform_default",
            "m5_historical_replay_enabled": historical_replay_enabled,
        },
        engine_code=os.getenv("M5_BACKTEST_ENGINE_CODE", "backtrader"),
        engine_payload=engine_payload,
    )

    with SessionLocal() as session:
        result = create_backtest_request_first_chain(session, dto)

    print(result)


if __name__ == "__main__":
    main()