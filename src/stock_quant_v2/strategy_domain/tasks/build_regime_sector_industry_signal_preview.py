"""Task entry point for M4 S3 signal preview artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

from stock_quant_v2.strategy_domain.services.regime_sector_industry_signal_preview_service import (
    DEFAULT_REPORT_DIR,
    DEFAULT_S2_ARTIFACT_DIR,
    SignalPreviewConfig,
    SignalPreviewResult,
    RegimeSectorIndustrySignalPreviewService,
)


@dataclass(slots=True)
class BuildSignalPreviewTaskResult:
    result: SignalPreviewResult


def run_build_regime_sector_industry_signal_preview(
    *,
    report_date: str,
    s2_artifact_dir: str | Path = DEFAULT_S2_ARTIFACT_DIR,
    output_dir: str | Path = DEFAULT_REPORT_DIR,
    effective_date: date | None = None,
    max_preview_rows: int | None = None,
    strategy_version_ref: str = "regime_sector_industry_selection_v1/S3_PREVIEW",
    project_root: str | Path = ".",
    env_file: str | Path | None = None,
    database_url: str | None = None,
    enable_v1_1_scoring_preview: bool = True,
    progress_callback: Callable[[str], None] | None = None,
) -> BuildSignalPreviewTaskResult:
    config = SignalPreviewConfig(
        report_date=report_date,
        s2_artifact_dir=Path(s2_artifact_dir),
        output_dir=Path(output_dir),
        effective_date=effective_date,
        max_preview_rows=max_preview_rows,
        strategy_version_ref=strategy_version_ref,
        project_root=Path(project_root),
        env_file=env_file,
        database_url=database_url,
        enable_v1_1_scoring_preview=enable_v1_1_scoring_preview,
    )
    service = RegimeSectorIndustrySignalPreviewService()
    result = service.build_preview(config, progress_callback=progress_callback)
    return BuildSignalPreviewTaskResult(result=result)
