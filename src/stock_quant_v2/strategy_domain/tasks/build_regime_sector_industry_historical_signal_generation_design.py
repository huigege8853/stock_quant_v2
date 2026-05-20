"""Task wrapper for M4 historical signal generation design dry-run."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from sqlalchemy.engine import Engine

from stock_quant_v2.strategy_domain.services.regime_sector_industry_historical_signal_generation_design_service import (
    RegimeSectorIndustryHistoricalSignalGenerationDesignConfig,
    RegimeSectorIndustryHistoricalSignalGenerationDesignService,
    RegimeSectorIndustryHistoricalSignalGenerationDesignTaskResult,
)


def run_build_regime_sector_industry_historical_signal_generation_design(
    *,
    engine: Engine | None,
    report_date: str,
    historical_request_artifact_dir: str | Path,
    output_dir: str | Path,
    strategy_code: str = "regime_sector_industry_selection_v1",
    strategy_version_code: str = "v1",
    research_backtest_request_id: int | None = None,
    benchmark_index_code: str = "000300.SH",
    target_top_n: int = 100,
    max_signal_batches: int = 120,
    min_signal_pairs: int = 20,
    progress_callback: Callable[[str], None] | None = None,
) -> RegimeSectorIndustryHistoricalSignalGenerationDesignTaskResult:
    config = RegimeSectorIndustryHistoricalSignalGenerationDesignConfig(
        report_date=report_date,
        historical_request_artifact_dir=Path(historical_request_artifact_dir),
        output_dir=Path(output_dir),
        strategy_code=strategy_code,
        strategy_version_code=strategy_version_code,
        research_backtest_request_id=research_backtest_request_id,
        benchmark_index_code=benchmark_index_code,
        target_top_n=target_top_n,
        max_signal_batches=max_signal_batches,
        min_signal_pairs=min_signal_pairs,
    )
    service = RegimeSectorIndustryHistoricalSignalGenerationDesignService(engine)
    result = service.design(config, progress_callback=progress_callback)
    return RegimeSectorIndustryHistoricalSignalGenerationDesignTaskResult(result=result)


# Historical signal generation preview dry-run is intentionally exposed from the
# existing design task module to avoid adding another task file while this M4
# historical pipeline is still being validated.
from stock_quant_v2.strategy_domain.services.regime_sector_industry_historical_signal_generation_design_service import (  # noqa: E402
    RegimeSectorIndustryHistoricalSignalGenerationPreviewConfig,
    RegimeSectorIndustryHistoricalSignalGenerationPreviewService,
    RegimeSectorIndustryHistoricalSignalGenerationPreviewTaskResult,
)


def run_build_regime_sector_industry_historical_signal_generation_preview(
    *,
    engine: Engine | None,
    report_date: str,
    design_artifact_dir: str | Path,
    output_dir: str | Path,
    strategy_code: str = "regime_sector_industry_selection_v1",
    strategy_version_code: str = "v1",
    research_backtest_request_id: int | None = None,
    benchmark_index_code: str = "000300.SH",
    target_top_n: int = 100,
    max_signal_batches: int = 120,
    min_preview_rows_per_batch: int = 50,
    feature_set_code: str = "fs_daily_alpha_v1",
    feature_set_version: str = "v1",
    industry_tag_type: str = "SW_INDUSTRY_L2",
    lookback_days: int = 20,
    preview_scoring_mode: str = "base",
    progress_callback: Callable[[str], None] | None = None,
) -> RegimeSectorIndustryHistoricalSignalGenerationPreviewTaskResult:
    config = RegimeSectorIndustryHistoricalSignalGenerationPreviewConfig(
        report_date=report_date,
        design_artifact_dir=Path(design_artifact_dir),
        output_dir=Path(output_dir),
        strategy_code=strategy_code,
        strategy_version_code=strategy_version_code,
        research_backtest_request_id=research_backtest_request_id,
        benchmark_index_code=benchmark_index_code,
        target_top_n=target_top_n,
        max_signal_batches=max_signal_batches,
        min_preview_rows_per_batch=min_preview_rows_per_batch,
        feature_set_code=feature_set_code,
        feature_set_version=feature_set_version,
        industry_tag_type=industry_tag_type,
        lookback_days=lookback_days,
        preview_scoring_mode=preview_scoring_mode,
    )
    service = RegimeSectorIndustryHistoricalSignalGenerationPreviewService(engine)
    result = service.preview(config, progress_callback=progress_callback)
    return RegimeSectorIndustryHistoricalSignalGenerationPreviewTaskResult(result=result)


# Historical signal DB write preview is also exposed from this existing task
# module to avoid adding another M4 historical task file.
from stock_quant_v2.strategy_domain.services.regime_sector_industry_historical_signal_generation_design_service import (  # noqa: E402
    RegimeSectorIndustryHistoricalSignalDbWritePreviewConfig,
    RegimeSectorIndustryHistoricalSignalDbWritePreviewService,
    RegimeSectorIndustryHistoricalSignalDbWritePreviewTaskResult,
)


def run_build_regime_sector_industry_historical_signal_db_write_preview(
    *,
    engine: Engine | None,
    report_date: str,
    preview_artifact_dir: str | Path,
    output_dir: str | Path,
    strategy_code: str = "regime_sector_industry_selection_v1",
    strategy_version_code: str = "v1",
    research_backtest_request_id: int | None = None,
    benchmark_index_code: str = "000300.SH",
    min_candidate_rows: int = 1000,
    max_rows: int | None = None,
    allow_existing_same_version_date: bool = False,
    progress_callback: Callable[[str], None] | None = None,
) -> RegimeSectorIndustryHistoricalSignalDbWritePreviewTaskResult:
    config = RegimeSectorIndustryHistoricalSignalDbWritePreviewConfig(
        report_date=report_date,
        preview_artifact_dir=Path(preview_artifact_dir),
        output_dir=Path(output_dir),
        strategy_code=strategy_code,
        strategy_version_code=strategy_version_code,
        research_backtest_request_id=research_backtest_request_id,
        benchmark_index_code=benchmark_index_code,
        min_candidate_rows=min_candidate_rows,
        max_rows=max_rows,
        allow_existing_same_version_date=allow_existing_same_version_date,
    )
    service = RegimeSectorIndustryHistoricalSignalDbWritePreviewService(engine)
    result = service.preview_write(config, progress_callback=progress_callback)
    return RegimeSectorIndustryHistoricalSignalDbWritePreviewTaskResult(result=result)


# Controlled historical strategy_signal DB write is exposed through the same
# task module to avoid adding another M4 historical task file.
from stock_quant_v2.strategy_domain.services.regime_sector_industry_historical_signal_generation_design_service import (  # noqa: E402
    RegimeSectorIndustryHistoricalSignalControlledDbWriteConfig,
    RegimeSectorIndustryHistoricalSignalControlledDbWriteService,
    RegimeSectorIndustryHistoricalSignalControlledDbWriteTaskResult,
)


def run_build_regime_sector_industry_historical_signal_controlled_db_write(
    *,
    engine: Engine | None,
    report_date: str,
    db_write_preview_artifact_dir: str | Path,
    output_dir: str | Path,
    strategy_code: str = "regime_sector_industry_selection_v1",
    strategy_version_code: str = "v1",
    research_backtest_request_id: int | None = None,
    benchmark_index_code: str = "000300.SH",
    min_inserted_rows: int = 1000,
    max_rows: int | None = None,
    existing_date_policy: str = "skip",
    dry_run: bool = False,
    progress_callback: Callable[[str], None] | None = None,
) -> RegimeSectorIndustryHistoricalSignalControlledDbWriteTaskResult:
    config = RegimeSectorIndustryHistoricalSignalControlledDbWriteConfig(
        report_date=report_date,
        db_write_preview_artifact_dir=Path(db_write_preview_artifact_dir),
        output_dir=Path(output_dir),
        strategy_code=strategy_code,
        strategy_version_code=strategy_version_code,
        research_backtest_request_id=research_backtest_request_id,
        benchmark_index_code=benchmark_index_code,
        min_inserted_rows=min_inserted_rows,
        max_rows=max_rows,
        existing_date_policy=existing_date_policy,
        dry_run=dry_run,
    )
    service = RegimeSectorIndustryHistoricalSignalControlledDbWriteService(engine)
    result = service.controlled_write(config, progress_callback=progress_callback)
    return RegimeSectorIndustryHistoricalSignalControlledDbWriteTaskResult(result=result)
