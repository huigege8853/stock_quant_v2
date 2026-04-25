from __future__ import annotations

from sqlalchemy.orm import Session

from stock_quant_v2.analytics_domain.services.factor_compute_service import FactorComputeService


def run(
    session: Session,
    trade_date,
    run_id: int,
    data_version_id: int | None = None,
) -> dict:
    service = FactorComputeService(session=session)
    result = service.compute_for_trade_date(
        trade_date=trade_date,
        run_id=run_id,
        data_version_id=data_version_id,
    )
    session.commit()
    return {
        "trade_date": str(result.trade_date),
        "deleted_rows": result.deleted_rows,
        "inserted_rows": result.inserted_rows,
    }