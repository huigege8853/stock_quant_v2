from __future__ import annotations

from sqlalchemy.orm import Session

from stock_quant_v2.analytics_domain.services.label_build_service import LabelBuildService


def run(
    session: Session,
    anchor_date,
    run_id: int,
    data_version_id: int | None = None,
) -> dict:
    service = LabelBuildService(session=session)
    result = service.build_for_anchor_date(
        anchor_date=anchor_date,
        run_id=run_id,
        data_version_id=data_version_id,
    )
    session.commit()
    return {
        "anchor_date": str(result.anchor_date),
        "deleted_rows": result.deleted_rows,
        "inserted_rows": result.inserted_rows,
    }