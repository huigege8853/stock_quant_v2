from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable

from sqlalchemy.orm import Session

from stock_quant_v2.strategy_domain.services.regime_sector_industry_rule_validation_service import (
    DEFAULT_BENCHMARK_INDEX_CODE,
    DEFAULT_INDUSTRY_TAG_TYPE,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_MIN_PREVIEW_ROWS,
    DEFAULT_TOP_N,
    RuleValidationConfig,
    RegimeSectorIndustryRuleValidationService,
)


@dataclass(slots=True)
class RuleValidationTaskResult:
    status: str
    result: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "result": self.result}


def run_build_regime_sector_industry_rule_validation(
    *,
    session: Session,
    report_date: str,
    output_dir: str | Path,
    trade_date: date,
    feature_set_code: str = "fs_daily_alpha_v1",
    feature_set_version: str = "v1",
    industry_tag_type: str = DEFAULT_INDUSTRY_TAG_TYPE,
    benchmark_index_code: str = DEFAULT_BENCHMARK_INDEX_CODE,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    min_preview_rows: int = DEFAULT_MIN_PREVIEW_ROWS,
    top_n: int = DEFAULT_TOP_N,
    progress_callback: Callable[[str], None] | None = None,
) -> RuleValidationTaskResult:
    config = RuleValidationConfig(
        report_date=report_date,
        trade_date=trade_date,
        output_dir=Path(output_dir),
        feature_set_code=feature_set_code,
        feature_set_version=feature_set_version,
        industry_tag_type=industry_tag_type,
        benchmark_index_code=benchmark_index_code,
        lookback_days=lookback_days,
        min_preview_rows=min_preview_rows,
        top_n=top_n,
    )
    service = RegimeSectorIndustryRuleValidationService(session)
    result = service.validate(config, progress_callback=progress_callback)
    return RuleValidationTaskResult(status=result.status, result=result.to_dict(include_rows=False))
