from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_quant_v2.db.models.research import ResearchBenchmarkDefinition


class BenchmarkRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_optional_by_code_version(
        self,
        *,
        benchmark_code: str | None,
        version_code: str | None,
    ) -> ResearchBenchmarkDefinition | None:
        if not benchmark_code:
            return None

        if not version_code:
            version_code = "v1"

        stmt = select(ResearchBenchmarkDefinition).where(
            ResearchBenchmarkDefinition.benchmark_code == benchmark_code,
            ResearchBenchmarkDefinition.version_code == version_code,
            ResearchBenchmarkDefinition.is_active.is_(True),
        )

        obj = self.session.execute(stmt).scalar_one_or_none()

        if obj is None:
            raise RuntimeError(
                "benchmark_definition not found or inactive: "
                f"{benchmark_code}:{version_code}"
            )

        return obj