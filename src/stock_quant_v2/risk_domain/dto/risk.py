from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class ApplyRiskToTargetRequestDTO:
    source_target_run_id: int
    adjusted_target_run_id: int
    risk_run_id: int
    portfolio_id: int
    risk_profile_code: str
    as_of_date: date | None = None
    effective_date: date | None = None
    current_position_run_id: int | None = None
    replace_existing: bool = False


@dataclass(frozen=True)
class ApplyRiskToTargetResultDTO:
    risk_run_id: int
    source_target_run_id: int
    adjusted_target_run_id: int
    portfolio_id: int
    risk_profile_code: str
    source_target_count: int
    adjusted_target_count: int
    decision_count: int
    pass_count: int
    warn_count: int
    reject_count: int
    adjust_count: int
    source_target_quantity_total: str
    adjusted_target_quantity_total: str
    status: str
    diagnostics: dict[str, Any]
