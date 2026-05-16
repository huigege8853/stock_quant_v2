"""Task entry point for M4 S3 preview -> strategy_signal contract/write adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

from stock_quant_v2.strategy_domain.services.regime_sector_industry_signal_preview_db_write_service import (
    DEFAULT_OUTPUT_DIR,
    DEFAULT_PREVIEW_ARTIFACT_DIR,
    DEFAULT_STRATEGY_VERSION_CODE,
    STRATEGY_CODE,
    RegimeSectorIndustrySignalPreviewDbWriteService,
    SignalPreviewDbWriteContractConfig,
    SignalPreviewDbWriteContractResult,
)


@dataclass(slots=True)
class BuildSignalPreviewDbWriteTaskResult:
    result: SignalPreviewDbWriteContractResult


def run_build_regime_sector_industry_signal_preview_db_write(
    *,
    engine,
    report_date: str,
    preview_artifact_dir: str | Path = DEFAULT_PREVIEW_ARTIFACT_DIR,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    strategy_code: str = STRATEGY_CODE,
    strategy_version_code: str = DEFAULT_STRATEGY_VERSION_CODE,
    effective_date: date | None = None,
    write_db: bool = False,
    write_confirmation: str = "",
    allow_existing_same_version_date: bool = False,
    max_rows: int | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> BuildSignalPreviewDbWriteTaskResult:
    config = SignalPreviewDbWriteContractConfig(
        report_date=report_date,
        preview_artifact_dir=Path(preview_artifact_dir),
        output_dir=Path(output_dir),
        strategy_code=strategy_code,
        strategy_version_code=strategy_version_code,
        effective_date=effective_date,
        write_db=write_db,
        write_confirmation=write_confirmation,
        allow_existing_same_version_date=allow_existing_same_version_date,
        max_rows=max_rows,
    )
    service = RegimeSectorIndustrySignalPreviewDbWriteService(engine)
    result = service.build_contract_or_write(config, progress_callback=progress_callback)
    return BuildSignalPreviewDbWriteTaskResult(result=result)
