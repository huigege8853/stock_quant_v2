from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_quant_v2.db.models.research import ResearchExecutionAssumptionProfile


class ExecutionAssumptionRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_code_version(
        self,
        *,
        profile_code: str,
        version_code: str,
    ) -> ResearchExecutionAssumptionProfile:
        stmt = select(ResearchExecutionAssumptionProfile).where(
            ResearchExecutionAssumptionProfile.profile_code == profile_code,
            ResearchExecutionAssumptionProfile.version_code == version_code,
            ResearchExecutionAssumptionProfile.is_active.is_(True),
        )

        obj = self.session.execute(stmt).scalar_one_or_none()

        if obj is None:
            raise RuntimeError(
                "execution_assumption_profile not found or inactive: "
                f"{profile_code}:{version_code}"
            )

        return obj