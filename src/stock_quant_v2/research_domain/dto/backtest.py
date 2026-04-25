from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from stock_quant_v2.research_domain.constants import (
    DEFAULT_BACKTEST_ENGINE_CODE,
    DEFAULT_INITIAL_CASH,
    DEFAULT_PORTFOLIO_CONSTRUCTION_MODE,
    DEFAULT_PORTFOLIO_CONSTRUCTION_PAYLOAD,
    DEFAULT_REBALANCE_FREQUENCY,
    DEFAULT_SIGNAL_EFFECTIVE_MODE,
)


@dataclass(frozen=True)
class BacktestRequestDTO:
    strategy_code: str
    version_code: str
    start_date: date
    end_date: date

    execution_assumption_profile_code: str
    execution_assumption_profile_version: str

    source_signal_run_id: int | None = None
    screen_request_id: int | None = None

    benchmark_code: str | None = None
    benchmark_version: str | None = None

    initial_cash: Decimal = DEFAULT_INITIAL_CASH

    rebalance_frequency: str = DEFAULT_REBALANCE_FREQUENCY
    signal_effective_mode: str = DEFAULT_SIGNAL_EFFECTIVE_MODE

    portfolio_construction_mode: str = DEFAULT_PORTFOLIO_CONSTRUCTION_MODE
    portfolio_construction_payload: dict[str, Any] = field(
        default_factory=lambda: dict(DEFAULT_PORTFOLIO_CONSTRUCTION_PAYLOAD)
    )

    data_feed_payload: dict[str, Any] = field(default_factory=dict)

    engine_code: str = DEFAULT_BACKTEST_ENGINE_CODE
    engine_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BacktestResultDTO:
    run_id: int
    backtest_request_id: int
    result_status: str

    start_date: date
    end_date: date

    trading_days: int | None = None

    initial_cash: Decimal | None = None
    final_equity: Decimal | None = None

    total_return: Decimal | None = None
    annual_return: Decimal | None = None
    benchmark_return: Decimal | None = None
    excess_return: Decimal | None = None

    max_drawdown: Decimal | None = None
    sharpe_ratio: Decimal | None = None
    volatility: Decimal | None = None
    win_rate: Decimal | None = None
    turnover_avg: Decimal | None = None

    order_count: int | None = None
    trade_count: int | None = None

    artifact_codes: list[str] = field(default_factory=list)