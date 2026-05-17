from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


def _strip_env_inline_comment(value: str) -> str:
    in_single = False
    in_double = False
    for index, char in enumerate(value):
        if char == "'" and not in_double:
            in_single = not in_single
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            continue
        if char == "#" and not in_single and not in_double:
            if index == 0 or value[index - 1].isspace():
                return value[:index].rstrip()
    return value.strip()


def _normalize_env_value(value: str) -> str:
    value = _strip_env_inline_comment(value).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _load_env_file(project_root: Path, env_file: str | None) -> Path | None:
    requested = (env_file or os.getenv("SQV2_ENV_FILE") or ".env.research").strip()
    if not requested:
        return None

    path = Path(requested)
    if not path.is_absolute():
        path = project_root / path

    if not path.exists():
        if env_file or os.getenv("SQV2_ENV_FILE"):
            raise FileNotFoundError(f"env file does not exist: {path}")
        return None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        os.environ.setdefault(key, _normalize_env_value(raw_value))
    return path


def _detect_project_root(explicit_project_root: str | None) -> Path:
    if explicit_project_root:
        return Path(explicit_project_root).resolve()
    cwd = Path.cwd().resolve()
    if (cwd / "src").exists():
        return cwd
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "src").exists():
            return parent
    return cwd


def _parse_report_date(value: str | None):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def _json_default(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build production daily observation report for DailyRun."
    )
    parser.add_argument("--project-root", default=None)
    parser.add_argument("--env-file", default=None)
    parser.add_argument("--report-date", default=None, help="Report date in YYYY-MM-DD. Default: latest production snapshot/core data date.")
    parser.add_argument("--campaign-config", default="configs/paper_campaigns/active_campaigns.json")
    parser.add_argument("--execution-context", default="production_paper_campaign")
    parser.add_argument("--output-root", default="artifacts/production/daily_observation")
    parser.add_argument("--detail-limit", type=int, default=50)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    project_root = _detect_project_root(args.project_root)
    loaded_env_path = _load_env_file(project_root, args.env_file)

    # Import DB-bound modules after optional env loading so --help does not require V2_SQLALCHEMY_URL.
    from stock_quant_v2.db.session import SessionLocal
    from stock_quant_v2.platform_overview_domain.services.production_daily_observation_report_builder import (
        ProductionDailyObservationReportBuilder,
    )

    session = SessionLocal()
    try:
        payload = ProductionDailyObservationReportBuilder(session).build(
            project_root=project_root,
            report_date=_parse_report_date(args.report_date),
            campaign_config_path=Path(args.campaign_config),
            execution_context=args.execution_context,
            output_root=Path(args.output_root),
            detail_limit=int(args.detail_limit),
        )
    finally:
        session.close()

    result = {
        "module": "production_daily_observation_report",
        "overall_status": payload.get("overall_status"),
        "report_date": _json_default(payload.get("report_date")),
        "production_campaign_count": payload.get("production_campaign_count"),
        "files": payload.get("files"),
        "env_file": str(loaded_env_path) if loaded_env_path else None,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
