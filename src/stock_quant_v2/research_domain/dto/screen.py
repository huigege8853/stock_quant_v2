from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class ScreenRequestDTO:
    strategy_code: str
    version_code: str
    as_of_date: date

    effective_date: date | None = None
    signal_lookup_mode: str = "EXISTING_SIGNAL"
    source_signal_run_id: int | None = None

    max_count: int | None = None
    min_score: Decimal | None = None

    include_reason_codes: list[str] = field(default_factory=list)
    exclude_reason_codes: list[str] = field(default_factory=list)

    universe_filter: dict[str, Any] = field(default_factory=dict)
    signal_filter: dict[str, Any] = field(default_factory=dict)
    parameter_values: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScreenResultDTO:
    run_id: int
    screen_request_id: int

    signal_run_id: int | None
    as_of_date: date
    effective_date: date | None

    eligible_universe_size: int | None
    selected_count: int

    score_min: Decimal | None = None
    score_max: Decimal | None = None
    score_avg: Decimal | None = None

    result_status: str = "SUCCESS"
    artifact_codes: list[str] = field(default_factory=list)