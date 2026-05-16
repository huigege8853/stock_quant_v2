from __future__ import annotations

import csv
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from sqlalchemy.orm import Session

from stock_quant_v2.analytics_domain.services.industry_strength_feature_service import (
    DEFAULT_INDUSTRY_TAG_TYPE,
    DEFAULT_MIN_INDUSTRY_COUNT,
    DEFAULT_MIN_INDUSTRY_SIZE,
    DEFAULT_WINDOW_SIZE,
    IndustryStrengthBuildResult,
    IndustryStrengthFeatureService,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_default(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    if not fieldnames:
        fieldnames = ["empty"]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_md(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# M4 S1.2 Industry Strength Feature Build",
        "",
        f"- status: `{payload.get('status')}`",
        f"- report_date: `{payload.get('report_date')}`",
        f"- feature_set: `{payload.get('feature_set_code')}@{payload.get('feature_set_version')}`",
        f"- industry_tag_type: `{payload.get('industry_tag_type')}`",
        f"- window_size: `{payload.get('window_size')}`",
        f"- min_industry_size: `{payload.get('min_industry_size')}`",
        f"- min_industry_count: `{payload.get('min_industry_count')}`",
        f"- feature_codes: `{', '.join(payload.get('feature_codes') or [])}`",
        "",
        "## Scope Guard",
        "",
        "- Does not generate M4 strategy_signal.",
        "- Does not submit M5 backtest.",
        "- Does not touch paper trading or risk.",
        "- Writes only existing analytics_feature_snapshot.",
        "",
        "## Date Results",
        "",
        "| trade_date | status | inserted_rows | ready_rows | industry_count | min_industry_count | instrument_count | source_stock_return_rows | reason |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in payload.get("dates") or []:
        lines.append(
            "| {trade_date} | {status} | {inserted_rows} | {ready_rows} | {industry_count} | {min_industry_count} | {instrument_count} | {source_stock_return_rows} | {reason} |".format(
                trade_date=item.get("trade_date"),
                status=item.get("status"),
                inserted_rows=item.get("inserted_rows"),
                ready_rows=item.get("ready_rows"),
                industry_count=item.get("industry_count"),
                min_industry_count=item.get("min_industry_count"),
                instrument_count=item.get("instrument_count"),
                source_stock_return_rows=item.get("source_stock_return_rows"),
                reason=item.get("reason") or "",
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_industry_strength_artifacts(*, output_dir: str | Path, report_date: str, result: IndustryStrengthBuildResult) -> dict[str, str]:
    output_dir = Path(output_dir)
    payload = result.to_dict()
    paths = {
        "json": output_dir / f"m4_industry_strength_feature_s1_2_{report_date}.json",
        "md": output_dir / f"m4_industry_strength_feature_s1_2_{report_date}.md",
        "date_stats_csv": output_dir / f"m4_industry_strength_feature_s1_2_{report_date}_date_stats.csv",
    }
    _write_json(paths["json"], payload)
    _write_md(paths["md"], payload)
    _write_csv(paths["date_stats_csv"], [item.to_dict() for item in result.dates])
    return {key: str(value) for key, value in paths.items()}


def run_build_industry_strength_feature(
    *,
    session: Session,
    run_id: int | None,
    report_date: str,
    output_dir: str | Path,
    trade_date: date | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    window_size: int = DEFAULT_WINDOW_SIZE,
    industry_tag_type: str = DEFAULT_INDUSTRY_TAG_TYPE,
    min_industry_size: int = DEFAULT_MIN_INDUSTRY_SIZE,
    min_industry_count: int = DEFAULT_MIN_INDUSTRY_COUNT,
    commit_every: int = 1,
    progress_callback: Callable[[str], None] | None = None,
) -> IndustryStrengthBuildResult:
    service = IndustryStrengthFeatureService(session=session)
    result = IndustryStrengthBuildResult(
        run_id=run_id,
        started_at=utc_now_iso(),
        report_date=report_date,
        industry_tag_type=industry_tag_type,
        window_size=window_size,
        min_industry_size=min_industry_size,
        min_industry_count=min_industry_count,
    )

    trade_dates = service.resolve_trade_dates(trade_date=trade_date, start_date=start_date, end_date=end_date)
    if progress_callback:
        progress_callback(f"INDUSTRY_STRENGTH_DATES_RESOLVED count={len(trade_dates)} dates={','.join(str(item) for item in trade_dates[:5])}{'...' if len(trade_dates) > 5 else ''}")
    if not trade_dates:
        result.status = "SKIPPED"
        result.finished_at = utc_now_iso()
        result.artifact_paths = write_industry_strength_artifacts(output_dir=output_dir, report_date=report_date, result=result)
        return result

    result.dates = service.build_for_dates(
        trade_dates=trade_dates,
        run_id=int(run_id or 0),
        window_size=window_size,
        industry_tag_type=industry_tag_type,
        min_industry_size=min_industry_size,
        min_industry_count=min_industry_count,
        commit_every=commit_every,
        progress_callback=progress_callback,
    )
    if commit_every <= 0:
        session.commit()

    result.status = "SUCCESS" if result.dates and all(item.status == "SUCCESS" for item in result.dates) else "PARTIAL"
    result.finished_at = utc_now_iso()
    result.artifact_paths = write_industry_strength_artifacts(output_dir=output_dir, report_date=report_date, result=result)
    if progress_callback:
        progress_callback(f"INDUSTRY_STRENGTH_ARTIFACTS_WRITTEN json={result.artifact_paths.get('json')} date_stats_csv={result.artifact_paths.get('date_stats_csv')}")
        progress_callback(f"INDUSTRY_STRENGTH_BUILD_DONE status={result.status}")
    return result
