from __future__ import annotations

import argparse
import csv
import json
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable


def _load_env_file(env_path: Path) -> bool:
    if not env_path.exists():
        return False

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not ((value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'"))):
            value = value.split(" #", 1)[0].strip()
        value = value.strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
    return True


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


@dataclass
class StageResult:
    stage: str
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None


@dataclass
class RepairResult:
    status: str
    generated_at: str
    report_date: str
    trade_date: str
    stages: list[StageResult]
    feature_quality: list[dict[str, Any]]
    artifacts: dict[str, str]
    action_items: list[dict[str, str]]


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _progress(message: str) -> None:
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"[M3_TRADABILITY_REPAIR][{timestamp}] {message}", flush=True)


def _run_stage(
    *,
    session_factory: Callable[[], Any],
    stage_name: str,
    trade_date: date,
    task_func: Callable[..., dict[str, Any]],
) -> StageResult:
    from stock_quant_v2.data_domain.repositories.run_repository import RunRepository

    with session_factory() as session:
        run_repo = RunRepository()
        run = run_repo.create_run(
            session=session,
            run_type="DATA_SYNC",
            run_name=f"bootstrap_m3_tradability_feature_repair_s2_blocker_{stage_name}",
            trigger_type="MANUAL",
            parent_run_id=None,
            context_json={
                "module": "M3",
                "task": "tradability_feature_repair_s2_blocker",
                "stage": stage_name,
                "trade_date": trade_date.isoformat(),
                "stage_boundary": "M3 repair only; no strategy_signal generated",
            },
        )
        run_repo.mark_run_running(session=session, run=run)
        session.commit()

        try:
            _progress(f"STAGE_START stage={stage_name} trade_date={trade_date.isoformat()}")
            result = task_func(session=session, trade_date=trade_date, run_id=run.id, data_version_id=None)
            run_repo.mark_run_finished(session=session, run=run, status="SUCCESS", error_message=None)
            session.commit()
            _progress(f"STAGE_DONE stage={stage_name} status=SUCCESS result={result}")
            return StageResult(stage=stage_name, status="SUCCESS", result=result)
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            run_repo.mark_run_finished(session=session, run=run, status="FAILED", error_message=str(exc))
            session.commit()
            _progress(f"STAGE_FAILED stage={stage_name} error={type(exc).__name__}: {exc}")
            return StageResult(stage=stage_name, status="FAILED", error=f"{type(exc).__name__}: {exc}")


def _load_feature_quality(engine: Any, trade_date: date) -> list[dict[str, Any]]:
    from sqlalchemy import text

    sql = text(
        """
        SELECT
            feature_code,
            count(*) AS row_count,
            count(*) FILTER (WHERE sample_status = 'ready') AS ready_rows,
            count(*) FILTER (WHERE feature_value_numeric IS NULL) AS null_rows,
            count(*) FILTER (WHERE feature_value_numeric = 0) AS zero_rows,
            count(*) FILTER (WHERE feature_value_numeric > 0) AS positive_rows,
            min(feature_value_numeric) AS min_value,
            max(feature_value_numeric) AS max_value,
            avg(feature_value_numeric) AS avg_value
        FROM analytics_feature_snapshot
        WHERE trade_date = :trade_date
          AND feature_set_code = 'fs_daily_alpha_v1'
          AND feature_set_version = 'v1'
          AND feature_code IN ('feat_tradable_flag', 'feat_tradability_score')
        GROUP BY feature_code
        ORDER BY feature_code
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, {"trade_date": trade_date}).mappings().all()
    return [dict(row) for row in rows]


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return
    fields: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fields})


def _status_from_quality(stages: list[StageResult], quality_rows: list[dict[str, Any]]) -> tuple[str, list[dict[str, str]]]:
    action_items: list[dict[str, str]] = []
    failed_stages = [stage for stage in stages if stage.status != "SUCCESS"]
    if failed_stages:
        for stage in failed_stages:
            action_items.append(
                {
                    "severity": "BLOCKER",
                    "item": f"stage_failed:{stage.stage}",
                    "reason": stage.error or "M3 stage failed.",
                    "next_step": "Inspect the traceback and rerun only after the stage succeeds.",
                }
            )
        return "FAIL", action_items

    by_code = {str(row.get("feature_code")): row for row in quality_rows}
    for feature_code in ("feat_tradable_flag", "feat_tradability_score"):
        row = by_code.get(feature_code)
        if row is None:
            action_items.append(
                {
                    "severity": "BLOCKER",
                    "item": f"missing_feature:{feature_code}",
                    "reason": "Expected repaired M3 feature was not found in analytics_feature_snapshot.",
                    "next_step": "Rerun indicator -> factor -> feature repair and check M3 task logs.",
                }
            )
            continue
        positive_rows = int(row.get("positive_rows") or 0)
        max_value = Decimal(str(row.get("max_value") or "0"))
        if positive_rows <= 0 or max_value <= 0:
            action_items.append(
                {
                    "severity": "BLOCKER",
                    "item": f"feature_still_all_zero:{feature_code}",
                    "reason": f"{feature_code} still has no positive samples after repair.",
                    "next_step": "Inspect core_instrument_status_daily fallback and current-day core_daily_bar volume/amount.",
                }
            )

    if action_items:
        return "FAIL", action_items

    action_items.append(
        {
            "severity": "INFO",
            "item": "m3_tradability_repair_ready_for_s2_rerun",
            "reason": "feat_tradable_flag and feat_tradability_score now have positive samples.",
            "next_step": "Rerun S2 rule validation; do not generate strategy_signal yet.",
        }
    )
    return "PASS", action_items


def _write_artifacts(result: RepairResult, output_dir: Path, report_date: str) -> RepairResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"m3_tradability_feature_repair_s2_blocker_{report_date}.json"
    md_path = output_dir / f"m3_tradability_feature_repair_s2_blocker_{report_date}.md"
    quality_csv_path = output_dir / f"tradability_feature_quality_after_repair_{report_date}.csv"

    _write_csv(quality_csv_path, result.feature_quality)

    result.artifacts = {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "feature_quality_csv_path": str(quality_csv_path),
    }

    json_path.write_text(
        json.dumps(asdict(result), ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )

    lines = [
        f"# M3 Tradability Feature Repair S2 Blocker - {report_date}",
        "",
        f"- status: `{result.status}`",
        f"- trade_date: `{result.trade_date}`",
        "",
        "## Stages",
    ]
    for stage in result.stages:
        lines.append(f"- {stage.stage}: `{stage.status}`")
        if stage.error:
            lines.append(f"  - error: `{stage.error}`")
    lines.extend(["", "## Feature Quality"])
    for row in result.feature_quality:
        lines.append(
            "- {feature_code}: rows={row_count}, ready={ready_rows}, positive={positive_rows}, max={max_value}".format(
                **{k: str(v) for k, v in row.items()}
            )
        )
    lines.extend(["", "## Action Items"])
    for item in result.action_items:
        lines.append(f"- [{item['severity']}] {item['item']}: {item['next_step']}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair M3 tradability features for S2 blocker validation.")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--report-date", required=True)
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--output-dir", default="artifacts/m4/strategy_rule_validation_tradability_repair")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    env_path = project_root / ".env.research"
    env_loaded = _load_env_file(env_path)
    print(f"ENV_LOADED={env_path if env_loaded else False}")

    # Import DB models after environment loading so settings can resolve DB URL safely.
    import stock_quant_v2.db.models.analytics  # noqa: F401
    import stock_quant_v2.db.models.meta.instrument  # noqa: F401
    import stock_quant_v2.db.models.ops.run  # noqa: F401
    from stock_quant_v2.analytics_domain.tasks.build_feature_snapshot import run as run_build_feature_snapshot
    from stock_quant_v2.analytics_domain.tasks.compute_factor_snapshot import run as run_compute_factor_snapshot
    from stock_quant_v2.analytics_domain.tasks.compute_indicator_snapshot import run as run_compute_indicator_snapshot
    from stock_quant_v2.db.session import SessionLocal, engine

    trade_date = _parse_date(args.trade_date)
    output_dir = (project_root / args.output_dir).resolve()

    _progress(
        "START trade_date={trade_date} report_date={report_date} output_dir={output_dir}".format(
            trade_date=trade_date.isoformat(),
            report_date=args.report_date,
            output_dir=output_dir,
        )
    )

    stages: list[StageResult] = []
    stage_plan = [
        ("indicator", run_compute_indicator_snapshot),
        ("factor", run_compute_factor_snapshot),
        ("feature", run_build_feature_snapshot),
    ]
    for stage_name, task_func in stage_plan:
        stage_result = _run_stage(
            session_factory=SessionLocal,
            stage_name=stage_name,
            trade_date=trade_date,
            task_func=task_func,
        )
        stages.append(stage_result)
        if stage_result.status != "SUCCESS":
            break

    feature_quality = _load_feature_quality(engine, trade_date=trade_date)
    status, action_items = _status_from_quality(stages=stages, quality_rows=feature_quality)

    result = RepairResult(
        status=status,
        generated_at=datetime.now(timezone.utc).isoformat(),
        report_date=args.report_date,
        trade_date=trade_date.isoformat(),
        stages=stages,
        feature_quality=feature_quality,
        artifacts={},
        action_items=action_items,
    )
    result = _write_artifacts(result, output_dir=output_dir, report_date=args.report_date)

    _progress(
        "DONE status={status} feature_quality_rows={rows} json={json_path}".format(
            status=result.status,
            rows=len(result.feature_quality),
            json_path=result.artifacts["json_path"],
        )
    )
    if result.status != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
