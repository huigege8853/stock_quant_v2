from __future__ import annotations

import os
from datetime import datetime

import stock_quant_v2.db.models.meta.instrument  # noqa: F401
import stock_quant_v2.db.models.ops.run  # noqa: F401
import stock_quant_v2.db.models.analytics  # noqa: F401

from stock_quant_v2.analytics_domain.tasks.build_label_snapshot import run as run_build_label_snapshot
from stock_quant_v2.analytics_domain.tasks.seed_label_definitions import run as run_seed_label_definitions
from stock_quant_v2.data_domain.repositories.run_repository import RunRepository
from stock_quant_v2.db.session import SessionLocal
from dotenv import load_dotenv

load_dotenv()

def main() -> None:
    anchor_date_str = os.getenv("M3_LABEL_ANCHOR_DATE")
    if not anchor_date_str:
        raise RuntimeError("Missing env: M3_LABEL_ANCHOR_DATE")

    anchor_date = datetime.strptime(anchor_date_str, "%Y-%m-%d").date()

    with SessionLocal() as session:
        run_repo = RunRepository()

        run_seed_label_definitions(session=session)

        run = run_repo.create_run(
            session=session,
            run_type="DATA_SYNC",
            run_name="bootstrap_m3_label_chain",
            trigger_type="MANUAL",
            parent_run_id=None,
            context_json={
                "anchor_date": anchor_date.isoformat(),
                "module": "M3",
                "task": "build_label_snapshot",
                "label_scope": [
                    "label_fwd_ret_5d",
                    "label_fwd_ret_10d",
                    "label_up_5d_ge_3pct",
                    "label_down_5d_le_m3pct",
                ],
            },
        )
        run_repo.mark_run_running(session=session, run=run)
        session.commit()

        try:
            result = run_build_label_snapshot(
                session=session,
                anchor_date=anchor_date,
                run_id=run.id,
                data_version_id=None,
            )
            run_repo.mark_run_finished(
                session=session,
                run=run,
                status="SUCCESS",
                error_message=None,
            )
            session.commit()
            print(result)
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            run_repo.mark_run_finished(
                session=session,
                run=run,
                status="FAILED",
                error_message=str(exc),
            )
            session.commit()
            raise


if __name__ == "__main__":
    main()