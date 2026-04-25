from __future__ import annotations

from sqlalchemy.orm import Session

from stock_quant_v2.db.models.research import ResearchExecutionAssumptionProfile
from stock_quant_v2.research_domain.repositories import ExecutionAssumptionRepository


class ExecutionAssumptionService:
    def __init__(self, session: Session):
        self.repo = ExecutionAssumptionRepository(session)

    def get_profile(
        self,
        *,
        profile_code: str,
        version_code: str,
    ) -> ResearchExecutionAssumptionProfile:
        return self.repo.get_by_code_version(
            profile_code=profile_code,
            version_code=version_code,
        )