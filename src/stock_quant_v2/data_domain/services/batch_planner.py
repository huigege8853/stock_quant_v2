from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(slots=True)
class BatchPlan:
    batch_no: int
    batch_key: str
    batch_type: str
    partition_date: date | None = None


def plan_daily_date_batches(start_date: date, end_date: date) -> list[BatchPlan]:
    plans: list[BatchPlan] = []
    current = start_date
    batch_no = 1

    while current <= end_date:
        plans.append(
            BatchPlan(
                batch_no=batch_no,
                batch_key=current.isoformat(),
                batch_type="DATE",
                partition_date=current,
            )
        )
        current += timedelta(days=1)
        batch_no += 1

    return plans