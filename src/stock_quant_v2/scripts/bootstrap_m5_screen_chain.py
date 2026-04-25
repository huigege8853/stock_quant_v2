from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.research_domain.dto.screen import ScreenRequestDTO
from stock_quant_v2.research_domain.enums import SignalLookupMode
from stock_quant_v2.research_domain.tasks.run_screen import run_screen_first_chain


def _env_date(name: str, default: str | None = None) -> date | None:
    value = os.getenv(name, default)
    if not value:
        return None
    return date.fromisoformat(value)


def _env_int(name: str, default: int | None = None) -> int | None:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def _env_decimal(name: str, default: str | None = None) -> Decimal | None:
    value = os.getenv(name, default)
    if value is None or value == "":
        return None
    return Decimal(value)


def _env_list(name: str, default: str = "") -> list[str]:
    value = os.getenv(name, default)
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def main() -> None:
    dto = ScreenRequestDTO(
        strategy_code=os.getenv("M5_SCREEN_STRATEGY_CODE", "alpha_selection"),
        version_code=os.getenv("M5_SCREEN_VERSION_CODE", "v1"),
        as_of_date=_env_date("M5_SCREEN_AS_OF_DATE", "2024-03-29"),
        effective_date=_env_date("M5_SCREEN_EFFECTIVE_DATE", "2024-04-01"),
        signal_lookup_mode=os.getenv(
            "M5_SCREEN_SIGNAL_LOOKUP_MODE",
            SignalLookupMode.EXISTING_SIGNAL.value,
        ),
        source_signal_run_id=_env_int("M5_SCREEN_SOURCE_SIGNAL_RUN_ID"),
        max_count=_env_int("M5_SCREEN_MAX_COUNT", 30),
        min_score=_env_decimal("M5_SCREEN_MIN_SCORE"),
        include_reason_codes=_env_list(
            "M5_SCREEN_INCLUDE_REASON_CODES",
            "TOP_N_SELECTED",
        ),
        exclude_reason_codes=_env_list("M5_SCREEN_EXCLUDE_REASON_CODES", ""),
        universe_filter={},
        signal_filter={},
        parameter_values={},
    )

    with SessionLocal() as session:
        result = run_screen_first_chain(session, dto)

    print(
        {
            "run_id": result.run_id,
            "screen_request_id": result.screen_request_id,
            "signal_run_id": result.signal_run_id,
            "as_of_date": str(result.as_of_date),
            "effective_date": str(result.effective_date)
            if result.effective_date
            else None,
            "eligible_universe_size": result.eligible_universe_size,
            "selected_count": result.selected_count,
            "score_min": str(result.score_min)
            if result.score_min is not None
            else None,
            "score_max": str(result.score_max)
            if result.score_max is not None
            else None,
            "score_avg": str(result.score_avg)
            if result.score_avg is not None
            else None,
            "result_status": result.result_status,
        }
    )


if __name__ == "__main__":
    main()