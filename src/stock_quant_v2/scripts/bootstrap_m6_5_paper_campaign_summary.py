from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any



DEFAULT_PRODUCTION_PAPER_CAMPAIGN_CONTEXT = "production_paper_campaign"


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
    return value


def _normalize_env_value(value: str) -> str:
    value = _strip_env_inline_comment(value).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _load_env_file(project_root: Path, env_file: str | None) -> Path | None:
    """Load a simple env file before importing DB-bound services.

    Keep precedence as: already exported environment > env file > defaults.
    This makes --help usable without database settings while allowing normal
    execution to load .env.research or an explicit --env-file.
    """

    requested = (env_file or os.getenv("SQV2_ENV_FILE") or ".env.research").strip()
    if not requested:
        return None

    path = Path(requested)
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()

    if not path.exists():
        if env_file or os.getenv("SQV2_ENV_FILE"):
            raise FileNotFoundError(f"env file does not exist: {path}")
        return None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key or key.startswith("#"):
            continue
        os.environ.setdefault(key, _normalize_env_value(raw_value))

    return path


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
    parser.add_argument(
        "--env-file",
        default=None,
        help=(
            "Optional env file to load before resolving DB-bound services. "
            "Relative paths are resolved from project root. Default: SQV2_ENV_FILE or .env.research if it exists."
        ),
    )
    parser.add_argument("--config", default=None, help="Path to active_campaigns.json. Default: configs/paper_campaigns/active_campaigns.json")
    parser.add_argument(
        "--campaign-code",
        default=None,
        help="Build a summary for one campaign. Mutually exclusive with --all-active.",
    )
    parser.add_argument(
        "--all-active",
        action="store_true",
        help=(
            "Build summaries for all ACTIVE campaigns matching --execution-context. "
            "This is the production daily-runtime mode."
        ),
    )
    parser.add_argument(
        "--execution-context",
        default=DEFAULT_PRODUCTION_PAPER_CAMPAIGN_CONTEXT,
        help=(
            "Campaign metadata execution_context used with --all-active. "
            "Default: production_paper_campaign."
        ),
    )
    parser.add_argument(
        "--include-inactive",
        action="store_true",
        help="When used with --all-active, include non-ACTIVE campaigns too. Default: false.",
    )
    parser.add_argument("--python-executable", default=sys.executable)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if bool(args.campaign_code) == bool(args.all_active):
        raise SystemExit("Specify exactly one of --campaign-code or --all-active.")

    project_root = _detect_project_root(args.project_root)
    loaded_env_path = _load_env_file(project_root, args.env_file)
    if loaded_env_path is not None:
        print(f"[M6.5_SUMMARY] env_file = {loaded_env_path}", flush=True)

    # Lazy import: PaperCampaignRunner imports DB settings, so import only after
    # --help has been handled and the env file has been loaded.
    from stock_quant_v2.paper_campaign_domain.services.paper_campaign_runner import PaperCampaignRunner

    config_path = Path(args.config).resolve() if args.config else _default_config_path(project_root)
    runner = PaperCampaignRunner(project_root=project_root, python_executable=args.python_executable)

    if args.all_active:
        result = runner.build_summaries(
            config_path=config_path,
            execution_context=args.execution_context,
            only_active=not args.include_inactive,
        )
    else:
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
