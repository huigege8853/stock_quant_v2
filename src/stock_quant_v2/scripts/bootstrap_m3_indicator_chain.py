from __future__ import annotations

import os
from datetime import datetime

# 显式加载已有模型，确保 Base.metadata 里能解析外键依赖
import stock_quant_v2.db.models.analytics  # noqa: F401
import stock_quant_v2.db.models.meta.instrument  # noqa: F401
import stock_quant_v2.db.models.ops.run  # noqa: F401
from dotenv import load_dotenv

from stock_quant_v2.analytics_domain.tasks.compute_indicator_snapshot import run as run_compute_indicator_snapshot
from stock_quant_v2.analytics_domain.tasks.seed_indicator_definitions import run as run_seed_indicator_definitions
from stock_quant_v2.data_domain.repositories.run_repository import RunRepository
from stock_quant_v2.db.session import SessionLocal

load_dotenv()


def _should_skip_seed() -> bool:
    return os.getenv("M3_SKIP_SEED", "false").strip().lower() in {"1", "true", "yes", "y"}


def main() -> None:
    trade_date_str = os.getenv("M3_INDICATOR_TRADE_DATE")
    if not trade_date_str:
        raise RuntimeError("Missing env: M3_INDICATOR_TRADE_DATE")

    trade_date = datetime.strptime(trade_date_str, "%Y-%m-%d").date()

    with SessionLocal() as session:
        run_repo = RunRepository()

        if not _should_skip_seed():
            run_seed_indicator_definitions(session=session)

        run = run_repo.create_run(
            session=session,
            run_type="DATA_SYNC",
            run_name="bootstrap_m3_indicator_chain",
            trigger_type="MANUAL",
            parent_run_id=None,
            context_json={
                "trade_date": trade_date.isoformat(),
                "module": "M3",
                "task": "compute_indicator_snapshot",
                "skip_seed": _should_skip_seed(),
                "indicator_scope": [
                    "adj_close",
                    "ret_1d",
                    "ret_20d",
                    "ma_20",
                    "volatility_20",
                    "tradable_flag",
                ],
            },
        )
        run_repo.mark_run_running(session=session, run=run)
        session.commit()

        try:
            result = run_compute_indicator_snapshot(
                session=session,
                trade_date=trade_date,
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
