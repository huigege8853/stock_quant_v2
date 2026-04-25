from __future__ import annotations

from sqlalchemy.orm import Session

from stock_quant_v2.db.models.research import ResearchBenchmarkDefinition
from stock_quant_v2.research_domain.repositories import BenchmarkRepository


class BenchmarkService:
    def __init__(self, session: Session):
        self.repo = BenchmarkRepository(session)

    def get_optional_benchmark(
        self,
        *,
        benchmark_code: str | None,
        version_code: str | None,
    ) -> ResearchBenchmarkDefinition | None:
        return self.repo.get_optional_by_code_version(
            benchmark_code=benchmark_code,
            version_code=version_code,
        )