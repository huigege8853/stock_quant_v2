from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class BacktestExecutionPlanDTO:
    run_id: int
    backtest_request_id: int

    start_date: date
    end_date: date

    engine_code: str
    execution_enabled: bool

    data_feed_plan: dict[str, Any] = field(default_factory=dict)
    strategy_bridge_plan: dict[str, Any] = field(default_factory=dict)
    analyzer_bridge_plan: dict[str, Any] = field(default_factory=dict)

    artifact_codes: list[str] = field(default_factory=list)