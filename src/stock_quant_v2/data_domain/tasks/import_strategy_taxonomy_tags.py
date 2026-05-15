from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Sequence

from sqlalchemy.orm import Session

from stock_quant_v2.data_domain.services.taxonomy_tag_import_service import (
    DEFAULT_EFFECTIVE_FROM,
    SW_AKSHARE_SOURCE_PROVIDER,
    TaxonomyImportResult,
    TaxonomyTagImportService,
    fetch_sw_industry_rows_from_akshare,
    utc_now_iso,
    write_source_rows_csv,
    write_taxonomy_import_artifacts,
)


def run_import_strategy_taxonomy_tags(
    *,
    session: Session,
    run_id: int | None,
    report_date: str,
    output_dir: str | Path,
    sw_industry_csv: str | Path | None = None,
    fetch_sw_industry_akshare: bool = False,
    sw_industry_codes: Sequence[str] | None = None,
    max_sw_industries: int | None = None,
    concept_em_csv: str | Path | None = None,
    fetch_em_concepts: bool = False,
    concept_names: Sequence[str] | None = None,
    max_concepts: int | None = None,
    effective_from: date = DEFAULT_EFFECTIVE_FROM,
    effective_to: date | None = None,
    progress_callback: Callable[[str], None] | None = None,
    progress_every: int = 1,
    sw_fetch_delay_seconds: float = 0.0,
    sw_fallback_delay_seconds: float = 2.0,
    sw_fetch_retry_attempts: int = 3,
    sw_fetch_retry_backoff_seconds: float = 5.0,
    sw_fetch_timeout_seconds: float = 20.0,
    concept_import_progress_every: int = 2000,
    concept_import_commit_every: int = 5000,
) -> TaxonomyImportResult:
    service = TaxonomyTagImportService()
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    result = TaxonomyImportResult(run_id=run_id, started_at=utc_now_iso())

    if sw_industry_csv:
        if progress_callback:
            progress_callback(f"SW_CSV_IMPORT_START path={sw_industry_csv}")
        result.stats.append(
            service.import_sw_industry_csv(
                session=session,
                csv_path=sw_industry_csv,
                effective_from=effective_from,
                effective_to=effective_to,
                confidence=Decimal("1.0000"),
            )
        )
        if progress_callback:
            stat = result.stats[-1]
            progress_callback(f"SW_CSV_IMPORT_DONE input_rows={stat.input_rows} instrument_tag_upsert_rows={stat.instrument_tag_upsert_rows} missing_instruments={stat.missing_instruments}")

    if fetch_sw_industry_akshare:
        if progress_callback:
            progress_callback("SW_AKSHARE_IMPORT_START")
        try:
            import akshare as ak
        except ImportError as exc:  # pragma: no cover - depends on local env.
            raise RuntimeError("akshare is required for --fetch-sw-industry-akshare. Install project dependencies first.") from exc
        sw_rows = fetch_sw_industry_rows_from_akshare(
            ak_module=ak,
            industry_codes=sw_industry_codes,
            max_industries=max_sw_industries,
            progress_callback=progress_callback,
            progress_every=progress_every,
            sw_fetch_delay_seconds=sw_fetch_delay_seconds,
            sw_fallback_delay_seconds=sw_fallback_delay_seconds,
            sw_fetch_retry_attempts=sw_fetch_retry_attempts,
            sw_fetch_retry_backoff_seconds=sw_fetch_retry_backoff_seconds,
            sw_fetch_timeout_seconds=sw_fetch_timeout_seconds,
        )
        output_path = Path(output_dir) / "sw_industry_2021_mapping.csv"
        write_source_rows_csv(output_path, sw_rows)
        if progress_callback:
            progress_callback(f"SW_AKSHARE_SOURCE_CSV_WRITTEN path={output_path} rows={len(sw_rows)}")
        result.stats.append(
            service.import_sw_industry_rows(
                session=session,
                rows=sw_rows,
                source="akshare.sw_index_third_info + akshare_or_legulegu_sw_index_third_cons",
                source_provider=SW_AKSHARE_SOURCE_PROVIDER,
                effective_from=effective_from,
                effective_to=effective_to,
                confidence=Decimal("0.9000"),
                import_name="sw_industry_akshare",
            )
        )
        if progress_callback:
            stat = result.stats[-1]
            progress_callback(f"SW_AKSHARE_IMPORT_DONE input_rows={stat.input_rows} instrument_tag_upsert_rows={stat.instrument_tag_upsert_rows} missing_instruments={stat.missing_instruments} error_rows={stat.error_rows}")

    if concept_em_csv:
        if progress_callback:
            progress_callback(f"CONCEPT_CSV_IMPORT_START path={concept_em_csv}")
        result.stats.append(
            service.import_concept_em_csv(
                session=session,
                csv_path=concept_em_csv,
                effective_from=effective_from,
                effective_to=effective_to,
                confidence=Decimal("0.9500"),
            )
        )
        if progress_callback:
            stat = result.stats[-1]
            progress_callback(f"CONCEPT_CSV_IMPORT_DONE input_rows={stat.input_rows} instrument_tag_upsert_rows={stat.instrument_tag_upsert_rows} missing_instruments={stat.missing_instruments}")

    if fetch_em_concepts:
        if progress_callback:
            progress_callback("CONCEPT_AKSHARE_IMPORT_START")
        try:
            import akshare as ak
        except ImportError as exc:  # pragma: no cover - depends on local env.
            raise RuntimeError("akshare is required for --fetch-em-concepts. Install project dependencies first.") from exc
        result.stats.append(
            service.import_concept_em_from_akshare(
                session=session,
                ak_module=ak,
                concept_names=concept_names,
                max_concepts=max_concepts,
                progress_callback=progress_callback,
                progress_every=progress_every,
                effective_from=effective_from,
                effective_to=effective_to,
                confidence=Decimal("0.9000"),
                concept_import_progress_every=concept_import_progress_every,
                concept_import_commit_every=concept_import_commit_every,
            )
        )
        if progress_callback:
            stat = result.stats[-1]
            progress_callback(f"CONCEPT_AKSHARE_IMPORT_DONE input_rows={stat.input_rows} instrument_tag_upsert_rows={stat.instrument_tag_upsert_rows} missing_instruments={stat.missing_instruments} error_rows={stat.error_rows}")

    if not result.stats:
        raise ValueError("No taxonomy input was requested. Provide --sw-industry-csv, --fetch-sw-industry-akshare, --concept-em-csv, or --fetch-em-concepts.")

    result.status = "SUCCESS" if all(stat.instrument_tag_upsert_rows > 0 for stat in result.stats) else "PARTIAL"
    result.finished_at = utc_now_iso()
    artifact_paths = write_taxonomy_import_artifacts(output_dir=output_dir, report_date=report_date, result=result)
    result.artifact_paths = artifact_paths
    if progress_callback:
        progress_callback(f"ARTIFACTS_WRITTEN json={artifact_paths.get('json')} stats_csv={artifact_paths.get('stats_csv')} errors_csv={artifact_paths.get('errors_csv')}")
        progress_callback(f"TAXONOMY_IMPORT_DONE status={result.status}")
    return result
