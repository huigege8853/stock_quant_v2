from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from stock_quant_v2.research_domain.services.backtest_quality_check_service import (
    BacktestQualityCheckService,
)


def check_backtest_quality_first_chain(
    session: Session,
    *,
    run_id: int,
) -> dict[str, Any]:
    return BacktestQualityCheckService(session).check_backtest_run(run_id=run_id)