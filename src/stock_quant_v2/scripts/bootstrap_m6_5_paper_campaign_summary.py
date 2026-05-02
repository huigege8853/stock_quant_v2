from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from stock_quant_v2.paper_campaign_domain.services.paper_campaign_runner import PaperCampaignRunner


def _detect_project_root(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    cwd = Path.cwd().resolve()
    if (cwd / "src").exists():
        return cwd
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "src").exists():
            return parent
    return cwd


def _default_config_path(project_root: Path) -> Path:
    return project_root / "configs" / "paper_campaigns" / "active_campaigns.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build M6.5 Forward Paper Campaign summary artifact.")
    parser.add_argument("--project-root", default=None)
    parser.add_argument("--config", default=None, help="Path to active_campaigns.json. Default: configs/paper_campaigns/active_campaigns.json")
    parser.add_argument("--campaign-code", required=True)
    parser.add_argument("--python-executable", default=sys.executable)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_root = _detect_project_root(args.project_root)
    config_path = Path(args.config).resolve() if args.config else _default_config_path(project_root)
    runner = PaperCampaignRunner(project_root=project_root, python_executable=args.python_executable)
    result = runner.build_summary(config_path=config_path, campaign_code=args.campaign_code)
    print(json.dumps(_jsonable(result), ensure_ascii=False, indent=2))
    return 0


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
