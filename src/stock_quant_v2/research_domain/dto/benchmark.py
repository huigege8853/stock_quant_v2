from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BenchmarkDefinitionDTO:
    benchmark_code: str
    version_code: str
    benchmark_name: str
    benchmark_type: str

    market_code: str | None = None
    market_index_id: int | None = None
    currency: str | None = None
    rebalance_rule: str | None = None

    config_payload: dict[str, Any] = field(default_factory=dict)
    is_active: bool = True