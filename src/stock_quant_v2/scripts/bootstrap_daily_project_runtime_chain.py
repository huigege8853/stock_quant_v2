from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Sequence

from sqlalchemy import text



PROGRESS_BAR_WIDTH = 32
PROGRESS_BUCKETS = (0, 25, 50, 75, 100)

_TQDM_PROGRESS_RE = re.compile(
    r"^(?P<task>.*?)\s+(?P<percent>\d{1,3})%\s*\|(?P<bar>[^|]*)\|\s*"
    r"(?P<current>\d+)\s*/\s*(?P<total>\d+)(?P<rest>.*)$"
)
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

PROFILE_CHOICES = ("runtime", "research", "full")
PAPER_MODE_CHOICES = ("auto", "m6", "m7", "skip", "off")
_TRUE_VALUES = {"1", "true", "t", "yes", "y", "on"}
_FALSE_VALUES = {"0", "false", "f", "no", "n", "off"}
DEFAULT_RESEARCH_STRATEGY_CODE = "regime_sector_industry_selection_v1"
DEFAULT_RESEARCH_STRATEGY_VERSION_CODE = "v1_regime_state_machine"


@dataclass(frozen=True)
class ChainStep:
    name: str
    module_name: str
    extra_args: tuple[str, ...] = ()
    extra_env: dict[str, str] = field(default_factory=dict)
    optional: bool = False
    soft_fail: bool = False


@dataclass(frozen=True)
class ParsedProgress:
    task: str
    percent: int
    current: int
    total: int
    stats: str = ""


def _strip_ansi(value: str) -> str:
    return _ANSI_RE.sub("", value).strip()


def _progress_bar(percent: int, width: int = PROGRESS_BAR_WIDTH) -> str:
    percent = max(0, min(100, int(percent)))
    filled = int(width * percent / 100)
    return "█" * filled + "░" * (width - filled)


def _progress_bucket(percent: int) -> int:
    percent = max(0, min(100, int(percent)))
    if percent >= 100:
        return 100
    if percent >= 75:
        return 75
    if percent >= 50:
        return 50
    if percent >= 25:
        return 25
    return 0


def _extract_progress_stats(rest: str) -> str:
    """Keep useful tqdm postfix stats and drop speed/ETA noise."""
    rest = _strip_ansi(rest)
    if not rest:
        return ""

    # tqdm postfix usually appears after the last comma separated segment.
    # Examples:
    #   [00:10<01:30, 55.0it/s, core=10, err=0, skip=0]
    #   , core=10, err=0, skip=0
    stat_match = re.search(r"(core\s*=.*)$", rest)
    if stat_match:
        return stat_match.group(1).strip(" ]")

    # Fallback: only keep short postfix-like fragments.
    if "=" in rest and len(rest) <= 120:
        return rest.strip(" []|,")
    return ""


def _parse_progress_line(line: str) -> ParsedProgress | None:
    clean_line = _strip_ansi(line)
    if not clean_line:
        return None

    match = _TQDM_PROGRESS_RE.match(clean_line)
    if not match:
        return None

    task = match.group("task").strip()
    if not task:
        return None

    try:
        percent = int(match.group("percent"))
        current = int(match.group("current"))
        total = int(match.group("total"))
    except ValueError:
        return None

    return ParsedProgress(
        task=task,
        percent=max(0, min(100, percent)),
        current=current,
        total=total,
        stats=_extract_progress_stats(match.group("rest")),
    )


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
    """Load a simple env file without overriding already exported variables.

    Precedence is intentionally: CLI args > process environment > env file > defaults.
    This keeps Docker/cron/shell exports authoritative in production while still
    allowing local development to fall back to .env.research when present.
    """
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
        value = _normalize_env_value(raw_value)
        os.environ.setdefault(key, value)

    return path


def _env_first(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip() != "":
            return value.strip()
    return None


def _parse_bool(value: object, *, option_name: str) -> bool:
    if isinstance(value, bool):
        return value

    normalized = str(value).strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False

    raise ValueError(
        f"Invalid boolean value for {option_name}: {value!r}. "
        "Use true/false, yes/no, on/off, or 1/0."
    )


def _resolve_bool_option(
    cli_value: bool | None,
    env_names: Sequence[str],
    default: bool,
) -> bool:
    if cli_value is not None:
        return bool(cli_value)

    value = _env_first(*env_names)
    if value is None:
        return default

    return _parse_bool(value, option_name="/".join(env_names))


def _resolve_choice_option(
    cli_value: str | None,
    env_names: Sequence[str],
    choices: Sequence[str],
    default: str,
) -> str:
    value = cli_value if cli_value is not None else _env_first(*env_names)
    if value is None:
        return default

    normalized = str(value).strip().lower()
    if normalized not in choices:
        raise ValueError(
            f"Invalid value for {'/'.join(env_names)}: {value!r}. "
            f"Allowed values: {', '.join(choices)}."
        )
    return normalized


def _resolve_int_option(
    cli_value: int | None,
    env_names: Sequence[str],
    default: int | None = None,
) -> int | None:
    if cli_value is not None:
        return int(cli_value)

    value = _env_first(*env_names)
    if value is None:
        return default

    return int(value)


def _resolve_string_option(
    cli_value: str | None,
    env_names: Sequence[str],
    default: str,
) -> str:
    value = cli_value if cli_value is not None else _env_first(*env_names)
    if value is None:
        return default

    normalized = str(value).strip()
    if not normalized:
        return default
    return normalized


def _safe_artifact_label(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    normalized = normalized.strip("._-")
    return normalized or "research_strategy"


def _resolve_report_date(cli_value: str | None) -> str | None:
    value = cli_value or _env_first("SQV2_DAILY_REPORT_DATE", "M8_REPORT_DATE", "M9_REPORT_DATE")
    if value is None:
        return None

    normalized = value.strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
        raise ValueError(f"Invalid report date: {value!r}. Expected YYYY-MM-DD.")
    return normalized


def _normalize_paper_mode(value: str) -> str:
    if value == "off":
        return "skip"
    return value


def _resolve_options_from_env(args: argparse.Namespace) -> argparse.Namespace:
    args.profile = _resolve_choice_option(
        args.profile,
        ("SQV2_DAILY_PROFILE",),
        PROFILE_CHOICES,
        "runtime",
    )
    args.report_date = _resolve_report_date(args.report_date)
    args.continue_on_error = _resolve_bool_option(
        args.continue_on_error,
        ("SQV2_DAILY_CONTINUE_ON_ERROR",),
        False,
    )
    args.skip_m5 = _resolve_bool_option(
        args.skip_m5,
        ("SQV2_DAILY_SKIP_M5",),
        False,
    )
    args.paper_mode = _normalize_paper_mode(
        _resolve_choice_option(
            args.paper_mode,
            ("SQV2_PAPER_MODE", "SQV2_DAILY_PAPER_MODE"),
            PAPER_MODE_CHOICES,
            "auto",
        )
    )
    args.paper_portfolio_id = _resolve_int_option(
        args.paper_portfolio_id,
        ("SQV2_PAPER_PORTFOLIO_ID", "M7_PORTFOLIO_ID", "M6_PAPER_PORTFOLIO_ID"),
        None,
    )
    args.skip_m8_daily_ops = _resolve_bool_option(
        args.skip_m8_daily_ops,
        ("SQV2_DAILY_SKIP_M8_DAILY_OPS",),
        False,
    )
    args.enable_m8_ops_master = _resolve_bool_option(
        args.enable_m8_ops_master,
        ("SQV2_RESEARCH_ENABLE_M8_OPS_MASTER", "SQV2_ENABLE_M8_OPS_MASTER"),
        True,
    )
    args.enable_regime_state_machine_research = _resolve_bool_option(
        args.enable_regime_state_machine_research,
        ("SQV2_RESEARCH_ENABLE_REGIME_STATE_MACHINE",),
        False,
    )
    args.research_strategy_code = _resolve_string_option(
        args.research_strategy_code,
        ("SQV2_RESEARCH_STRATEGY_CODE",),
        DEFAULT_RESEARCH_STRATEGY_CODE,
    )
    args.research_strategy_version_code = _resolve_string_option(
        args.research_strategy_version_code,
        ("SQV2_RESEARCH_STRATEGY_VERSION_CODE",),
        DEFAULT_RESEARCH_STRATEGY_VERSION_CODE,
    )
    args.research_target_top_n = _resolve_int_option(
        args.research_target_top_n,
        ("SQV2_RESEARCH_TARGET_TOP_N",),
        100,
    )
    args.research_max_signal_batches = _resolve_int_option(
        args.research_max_signal_batches,
        ("SQV2_RESEARCH_MAX_SIGNAL_BATCHES",),
        120,
    )
    args.research_min_candidate_rows = _resolve_int_option(
        args.research_min_candidate_rows,
        ("SQV2_RESEARCH_MIN_CANDIDATE_ROWS",),
        1000,
    )
    args.enable_m6_5_campaign = _resolve_bool_option(
        args.enable_m6_5_campaign,
        ("SQV2_DAILY_ENABLE_M6_5_CAMPAIGN", "SQV2_ENABLE_M6_5_CAMPAIGN"),
        False,
    )
    args.m6_5_campaign_config = (
        args.m6_5_campaign_config
        or _env_first("SQV2_M6_5_CAMPAIGN_CONFIG", "M6_5_CAMPAIGN_CONFIG")
    )
    args.enable_m6_5_campaign_summary = _resolve_bool_option(
        args.enable_m6_5_campaign_summary,
        ("SQV2_DAILY_ENABLE_M6_5_CAMPAIGN_SUMMARY", "SQV2_ENABLE_M6_5_CAMPAIGN_SUMMARY"),
        bool(args.enable_m6_5_campaign),
    )
    args.m6_5_campaign_summary_execution_context = _resolve_string_option(
        args.m6_5_campaign_summary_execution_context,
        ("SQV2_M6_5_CAMPAIGN_SUMMARY_EXECUTION_CONTEXT",),
        "production_paper_campaign",
    )
    args.enable_production_daily_observation_report = _resolve_bool_option(
        args.enable_production_daily_observation_report,
        ("SQV2_DAILY_ENABLE_PRODUCTION_DAILY_OBSERVATION_REPORT",),
        True,
    )
    args.production_daily_observation_output_root = _resolve_string_option(
        args.production_daily_observation_output_root,
        ("SQV2_PRODUCTION_DAILY_OBSERVATION_OUTPUT_ROOT",),
        "artifacts/production/daily_observation",
    )
    args.production_daily_observation_execution_context = _resolve_string_option(
        args.production_daily_observation_execution_context,
        ("SQV2_PRODUCTION_DAILY_OBSERVATION_EXECUTION_CONTEXT",),
        "production_paper_campaign",
    )
    return args


def _module_file_exists(project_root: Path, module_name: str) -> bool:
    module_path = Path(*module_name.split(".")).with_suffix(".py")
    return (project_root / "src" / module_path).exists()


class DailyOutputEmitter:
    """
    Convert child-process stdout/stderr into DailyRun logs.

    tqdm uses carriage-return refreshes. When DailyRun is executed with nohup and
    redirected to a log file, writing every refresh will flood the log. This
    emitter therefore keeps normal lines unchanged, but compresses tqdm progress
    to 0/25/50/75/100 buckets per task.
    """

    def __init__(self, step_name: str):
        self.step_name = step_name
        self._last_progress_bucket_by_task: dict[str, int] = {}

    def handle_line(self, raw_line: str) -> None:
        line = raw_line.strip("\r\n")
        if not line:
            return

        progress = _parse_progress_line(line)
        if progress is not None:
            self._emit_progress(progress)
            return

        print(f"[DAILY][{self.step_name}] {_strip_ansi(line)}", flush=True)

    def _emit_progress(self, progress: ParsedProgress) -> None:
        bucket = _progress_bucket(progress.percent)
        last_bucket = self._last_progress_bucket_by_task.get(progress.task)

        if last_bucket == bucket:
            return
        if last_bucket is not None and bucket < last_bucket:
            return

        self._last_progress_bucket_by_task[progress.task] = bucket
        bucketed = ParsedProgress(
            task=progress.task,
            percent=bucket,
            current=progress.current,
            total=progress.total,
            stats=progress.stats,
        )
        print(f"[DAILY][{self.step_name}] {self._format_progress(bucketed)}", flush=True)

    @staticmethod
    def _format_progress(progress: ParsedProgress) -> str:
        text = (
            f"{progress.task} {progress.percent:3d}% "
            f"|{_progress_bar(progress.percent)}| "
            f"{progress.current}/{progress.total}"
        )
        if progress.stats:
            text += f" | {progress.stats}"
        return text


def _detect_project_root(explicit_project_root: str | None) -> Path:
    if explicit_project_root:
        root = Path(explicit_project_root).resolve()
        if not root.exists():
            raise FileNotFoundError(f"project root does not exist: {root}")
        return root

    cwd = Path.cwd().resolve()
    if (cwd / "src").exists():
        return cwd

    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "src").exists():
            return parent

    raise RuntimeError(
        "Cannot detect project root. Please run from project root or pass --project-root."
    )


def _build_runtime_env(project_root: Path, report_date: str | None) -> dict[str, str]:
    env = os.environ.copy()

    src_dir = project_root / "src"
    old_pythonpath = env.get("PYTHONPATH", "").strip()

    if old_pythonpath:
        env["PYTHONPATH"] = f"{src_dir}{os.pathsep}{old_pythonpath}"
    else:
        env["PYTHONPATH"] = str(src_dir)

    if report_date:
        env["M8_REPORT_DATE"] = report_date

    # Keep tqdm parseable for the DailyRun log compressor.
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("TQDM_MININTERVAL", "1.0")

    return env


def _run_module(
    *,
    step_name: str,
    module_name: str,
    extra_args: Sequence[str],
    extra_env: dict[str, str],
    env: dict[str, str],
    cwd: Path,
    python_executable: str,
) -> int:
    merged_env = env.copy()
    if extra_env:
        merged_env.update(extra_env)

    cmd = [python_executable, "-u", "-m", module_name, *extra_args]

    print(f"[DAILY][{step_name}] cmd = {' '.join(cmd)}", flush=True)
    started = time.perf_counter()
    emitter = DailyOutputEmitter(step_name=step_name)

    with subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=merged_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    ) as proc:
        assert proc.stdout is not None

        buffer: list[str] = []
        while True:
            char = proc.stdout.read(1)
            if char == "":
                break
            if char in ("\n", "\r"):
                if buffer:
                    emitter.handle_line("".join(buffer))
                    buffer.clear()
                continue
            buffer.append(char)

        if buffer:
            emitter.handle_line("".join(buffer))

        rc = proc.wait()

    elapsed = time.perf_counter() - started
    print(
        f"[DAILY][{step_name}] finished in {elapsed:.1f}s with exit_code={rc}",
        flush=True,
    )
    return int(rc)


class DatabaseInspector:
    """
    使用项目自己的 SessionLocal 探测数据库状态，
    避免 daily auto-route 额外依赖显式 DB URL 环境变量。
    """

    def latest_trading_day(self) -> date | None:
        candidates = [
            ("meta_trading_calendar", "trade_date", "is_open"),
            ("meta_trading_calendar", "calendar_date", "is_open"),
            ("meta_trading_calendar", "trade_date", "is_trading_day"),
            ("meta_trading_calendar", "calendar_date", "is_trading_day"),
        ]

        from stock_quant_v2.db.session import SessionLocal

        with SessionLocal() as session:
            for table_name, date_col, open_col in candidates:
                sql = f"""
                SELECT MAX({date_col})
                FROM {table_name}
                WHERE {open_col} = TRUE
                  AND {date_col} <= CURRENT_DATE
                """
                value = self._safe_scalar(session, sql)
                coerced = self._coerce_to_date(value)
                if coerced is not None:
                    return coerced

            fallback = self._safe_scalar(session, "SELECT MAX(trade_date) FROM core_daily_bar")
            return self._coerce_to_date(fallback)

    def has_previous_snapshot(self, portfolio_id: int, effective_date: date) -> bool:
        sql = """
        select 1
        from trading_paper_portfolio_snapshot
        where portfolio_id = :portfolio_id
          and snapshot_date < :effective_date
        limit 1
        """
        from stock_quant_v2.db.session import SessionLocal

        with SessionLocal() as session:
            value = self._safe_scalar(
                session,
                sql,
                {
                    "portfolio_id": portfolio_id,
                    "effective_date": effective_date,
                },
            )
            return value is not None

    @staticmethod
    def _safe_scalar(session, sql: str, params: dict | None = None):
        try:
            return session.execute(text(sql), params or {}).scalar()
        except Exception:
            return None

    @staticmethod
    def _coerce_to_date(value):
        if value is None:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            return datetime.strptime(value, "%Y-%m-%d").date()
        return None


def _resolve_portfolio_id(args: argparse.Namespace) -> int:
    if args.paper_portfolio_id is not None:
        return int(args.paper_portfolio_id)

    env_id = os.getenv("M7_PORTFOLIO_ID") or os.getenv("M6_PAPER_PORTFOLIO_ID")
    if env_id:
        return int(env_id)

    return 1


def _resolve_paper_step(args: argparse.Namespace) -> ChainStep | None:
    if args.paper_mode == "skip":
        return None

    inspector = DatabaseInspector()

    latest_day = inspector.latest_trading_day()
    if latest_day is None:
        raise RuntimeError("Cannot resolve latest trading day for paper routing.")

    portfolio_id = _resolve_portfolio_id(args)
    has_snapshot = inspector.has_previous_snapshot(
        portfolio_id=portfolio_id,
        effective_date=latest_day,
    )

    if args.paper_mode == "m6":
        route = "m6"
    elif args.paper_mode == "m7":
        route = "m7"
    else:
        route = "m7" if has_snapshot else "m6"

    if route == "m6":
        return ChainStep(
            "m6_paper_trading_refresh",
            "stock_quant_v2.scripts.bootstrap_m6_paper_trading_refresh_chain",
            extra_env={
                "M6_PAPER_PORTFOLIO_ID": str(portfolio_id),
            },
        )

    return ChainStep(
        "m7_daily_refresh",
        "stock_quant_v2.scripts.bootstrap_m7_daily_refresh_chain",
        extra_env={
            "M7_PORTFOLIO_ID": str(portfolio_id),
        },
    )


def _build_taxonomy_daily_refresh_args(report_date: str | None) -> tuple[str, ...]:
    args: list[str] = [
        "--daily-refresh",
        "--fail-safe",
        "--fetch-sw-industry-akshare",
        "--fetch-em-concepts",
        "--output-dir",
        "artifacts/m4/taxonomy_daily_refresh",
        "--progress-every",
        "20",
        "--sw-fetch-delay-seconds",
        "1.5",
        "--sw-fallback-delay-seconds",
        "2",
        "--sw-fetch-retry-attempts",
        "3",
        "--sw-fetch-retry-backoff-seconds",
        "5",
        "--sw-fetch-timeout-seconds",
        "30",
        "--concept-import-progress-every",
        "5000",
        "--concept-import-commit-every",
        "5000",
    ]
    if report_date:
        args.extend(["--report-date", report_date])
    return tuple(args)


def _build_runtime_steps(args: argparse.Namespace) -> list[ChainStep]:
    steps: list[ChainStep] = [
        ChainStep("m2_data_refresh", "stock_quant_v2.scripts.bootstrap_m2_data_refresh_chain"),
        ChainStep("m3_analytics_refresh", "stock_quant_v2.scripts.bootstrap_m3_analytics_refresh_chain"),
        ChainStep(
            "m4_taxonomy_daily_refresh",
            "stock_quant_v2.scripts.bootstrap_m4_taxonomy_inputs_p0",
            extra_args=_build_taxonomy_daily_refresh_args(args.report_date),
            optional=True,
            soft_fail=True,
        ),
        ChainStep("m4_strategy_refresh", "stock_quant_v2.scripts.bootstrap_m4_strategy_refresh_chain"),
    ]

    if not args.skip_m5:
        steps.append(
            ChainStep("m5_daily_refresh", "stock_quant_v2.scripts.bootstrap_m5_research_refresh_chain")
        )

    paper_step = _resolve_paper_step(args)
    if paper_step is not None:
        steps.append(paper_step)

    if getattr(args, "enable_m6_5_campaign", False):
        extra_args: tuple[str, ...] = ()
        if getattr(args, "m6_5_campaign_config", None):
            extra_args = ("--config", str(args.m6_5_campaign_config))
        steps.append(
            ChainStep(
                "m6_5_paper_campaign_daily",
                "stock_quant_v2.scripts.bootstrap_m6_5_paper_campaign_daily",
                extra_args=extra_args,
                optional=True,
                soft_fail=True,
            )
        )

        if getattr(args, "enable_m6_5_campaign_summary", False):
            summary_args: list[str] = [
                "--all-active",
                "--execution-context",
                str(args.m6_5_campaign_summary_execution_context),
            ]
            if getattr(args, "m6_5_campaign_config", None):
                summary_args.extend(["--config", str(args.m6_5_campaign_config)])
            steps.append(
                ChainStep(
                    "m6_5_production_paper_campaign_summary",
                    "stock_quant_v2.scripts.bootstrap_m6_5_paper_campaign_summary",
                    extra_args=tuple(summary_args),
                    optional=True,
                    soft_fail=True,
                )
            )

    if not args.skip_m8_daily_ops:
        steps.append(
            ChainStep(
                "m8_daily_ops_entrypoint",
                "stock_quant_v2.scripts.m8_daily_ops_entrypoint",
                extra_env={
                    # Production daily observation is generated by DailyRun itself;
                    # keep M8 daily ops from triggering legacy M9 research finalizers.
                    "M8_DAILY_FINALIZER_PROFILE": "off",
                },
            )
        )

    if getattr(args, "enable_production_daily_observation_report", True):
        observation_args: list[str] = [
            "--project-root",
            ".",
            "--output-root",
            str(args.production_daily_observation_output_root),
            "--execution-context",
            str(args.production_daily_observation_execution_context),
        ]
        if getattr(args, "m6_5_campaign_config", None):
            observation_args.extend(["--campaign-config", str(args.m6_5_campaign_config)])
        if args.report_date:
            observation_args.extend(["--report-date", args.report_date])
        steps.append(
            ChainStep(
                "production_daily_observation_report",
                "stock_quant_v2.platform_overview_domain.tasks.build_production_daily_observation_report",
                extra_args=tuple(observation_args),
                optional=True,
                soft_fail=True,
            )
        )

    return steps


def _report_date_args(report_date: str | None) -> tuple[str, ...]:
    if report_date:
        return ("--report-date", report_date)
    return ()


def _build_regime_state_machine_research_steps(args: argparse.Namespace) -> list[ChainStep]:
    strategy_code = str(args.research_strategy_code)
    strategy_version_code = str(args.research_strategy_version_code)
    label = _safe_artifact_label(strategy_version_code)
    base_dir = f"artifacts/m4/research_chain_{label}"
    design_dir = f"{base_dir}/historical_signal_generation_design"
    preview_dir = f"{base_dir}/historical_signal_generation_preview"
    db_write_preview_dir = f"{base_dir}/historical_signal_db_write_preview"
    report_date_args = _report_date_args(args.report_date)

    common_strategy_args = (
        "--project-root",
        ".",
        *report_date_args,
        "--strategy-code",
        strategy_code,
        "--strategy-version-code",
        strategy_version_code,
    )

    return [
        ChainStep(
            "m4_regime_sm_historical_design",
            "stock_quant_v2.scripts.bootstrap_m4_historical_signal_generation_design",
            extra_args=(
                *common_strategy_args,
                "--mode",
                "design",
                "--output-dir",
                design_dir,
            ),
        ),
        ChainStep(
            "m4_regime_sm_historical_preview",
            "stock_quant_v2.scripts.bootstrap_m4_historical_signal_generation_design",
            extra_args=(
                *common_strategy_args,
                "--mode",
                "preview_dry_run",
                "--design-artifact-dir",
                design_dir,
                "--output-dir",
                preview_dir,
                "--target-top-n",
                str(args.research_target_top_n),
                "--max-signal-batches",
                str(args.research_max_signal_batches),
            ),
        ),
        ChainStep(
            "m4_regime_sm_db_write_preview",
            "stock_quant_v2.scripts.bootstrap_m4_historical_signal_generation_design",
            extra_args=(
                *common_strategy_args,
                "--mode",
                "db_write_preview",
                "--preview-artifact-dir",
                preview_dir,
                "--output-dir",
                db_write_preview_dir,
                "--min-candidate-rows",
                str(args.research_min_candidate_rows),
            ),
        ),
        ChainStep(
            "m5_m9_bridge_refresh",
            "stock_quant_v2.platform_overview_domain.tasks.build_upstream_readiness_summaries",
            extra_args=report_date_args,
        ),
        ChainStep(
            "m9_research_portfolio_daily_report",
            "stock_quant_v2.platform_overview_domain.tasks.build_research_portfolio_daily_report",
            extra_args=report_date_args,
        ),
        ChainStep(
            "m9_platform_overview_report",
            "stock_quant_v2.platform_overview_domain.tasks.build_platform_overview_report",
            extra_args=report_date_args,
        ),
    ]


def _build_research_steps(
    args: argparse.Namespace,
    *,
    include_m5_refresh: bool,
) -> list[ChainStep]:
    steps: list[ChainStep] = []

    # Optional heavy/research modules are skipped when the current branch does
    # not contain them yet. This lets the production runtime profile stay stable
    # while research capabilities are introduced incrementally.
    steps.extend(
        [
            ChainStep(
                "m3_historical_feature_backfill_p1",
                "stock_quant_v2.scripts.bootstrap_m3_historical_feature_backfill_p1",
                optional=True,
            ),
            ChainStep(
                "m5_historical_signal_backfill_p1",
                "stock_quant_v2.scripts.bootstrap_m5_historical_signal_backfill_p1",
                optional=True,
            ),
        ]
    )

    if include_m5_refresh and not args.skip_m5:
        steps.append(
            ChainStep("m5_research_refresh", "stock_quant_v2.scripts.bootstrap_m5_research_refresh_chain")
        )

    if args.enable_regime_state_machine_research:
        steps.extend(_build_regime_state_machine_research_steps(args))

    if args.enable_m8_ops_master:
        steps.append(
            ChainStep(
                "m8_ops_master_chain",
                "stock_quant_v2.scripts.bootstrap_m8_ops_master_chain",
                extra_args=("--continue-on-error",),
                soft_fail=True,
            )
        )

    return steps

def _build_steps(args: argparse.Namespace) -> list[ChainStep]:
    if args.profile == "runtime":
        return _build_runtime_steps(args)

    if args.profile == "research":
        return _build_research_steps(args, include_m5_refresh=True)

    if args.profile == "full":
        return [
            *_build_runtime_steps(args),
            *_build_research_steps(args, include_m5_refresh=False),
        ]

    raise ValueError(f"Unsupported daily profile: {args.profile!r}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Daily master chain with profile routing. "
            "runtime = production daily path with production_daily_observation_report and M8 daily ops entrypoint; "
            "research = heavy/research path that may run bootstrap_m8_ops_master_chain; "
            "full = runtime + research. Runtime does not require M8 full ops PASS."
        )
    )
    parser.add_argument(
        "--project-root",
        default=None,
        help="Project root that contains src/. Default: auto-detect.",
    )
    parser.add_argument(
        "--env-file",
        default=None,
        help=(
            "Optional env file to load before resolving DailyRun controls. "
            "Production Docker should use exported/docker-compose env values; local development may fall back to .env.research. "
            "Relative paths are resolved from project root. Default: SQV2_ENV_FILE or .env.research if it exists."
        ),
    )
    parser.add_argument(
        "--python-executable",
        default=sys.executable,
        help="Python executable used for child modules. Default: current interpreter.",
    )
    parser.add_argument(
        "--profile",
        choices=PROFILE_CHOICES,
        default=None,
        help="Daily profile. CLI > SQV2_DAILY_PROFILE > runtime.",
    )
    parser.add_argument(
        "--report-date",
        default=None,
        help="Optional override for M8_REPORT_DATE, format YYYY-MM-DD. Env: SQV2_DAILY_REPORT_DATE.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        default=None,
        help="Continue remaining steps after a failed module. Env: SQV2_DAILY_CONTINUE_ON_ERROR.",
    )
    parser.add_argument(
        "--skip-m5",
        action="store_true",
        default=None,
        help="Skip the M5 daily refresh step in the selected DailyRun profile. Env: SQV2_DAILY_SKIP_M5.",
    )
    parser.add_argument(
        "--paper-mode",
        choices=PAPER_MODE_CHOICES,
        default=None,
        help=(
            "Paper trading route. auto = no previous snapshot -> M6, existing snapshot -> M7; "
            "skip/off = no paper step. Env: SQV2_PAPER_MODE."
        ),
    )
    parser.add_argument(
        "--paper-portfolio-id",
        type=int,
        default=None,
        help="Portfolio id used for paper routing. Env: SQV2_PAPER_PORTFOLIO_ID, M7_PORTFOLIO_ID, or M6_PAPER_PORTFOLIO_ID.",
    )
    parser.add_argument(
        "--skip-m8-daily-ops",
        action="store_true",
        default=None,
        help="Skip M8 daily ops entrypoint. Env: SQV2_DAILY_SKIP_M8_DAILY_OPS.",
    )
    parser.add_argument(
        "--enable-m8-ops-master",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Enable M8 ops master chain for research/full profiles only. "
            "This is not required for production runtime daily observation. "
            "Use --no-enable-m8-ops-master to disable. Env: SQV2_RESEARCH_ENABLE_M8_OPS_MASTER."
        ),
    )
    parser.add_argument(
        "--enable-regime-state-machine-research",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Enable optional research-only regime state machine candidate chain. "
            "Default is disabled. Env: SQV2_RESEARCH_ENABLE_REGIME_STATE_MACHINE."
        ),
    )
    parser.add_argument(
        "--research-strategy-code",
        default=None,
        help=(
            "Strategy code for optional research candidate chain. "
            "Env: SQV2_RESEARCH_STRATEGY_CODE."
        ),
    )
    parser.add_argument(
        "--research-strategy-version-code",
        default=None,
        help=(
            "Strategy version code for optional research candidate chain. "
            "Env: SQV2_RESEARCH_STRATEGY_VERSION_CODE."
        ),
    )
    parser.add_argument(
        "--research-target-top-n",
        type=int,
        default=None,
        help="Target top-N for optional research historical preview. Env: SQV2_RESEARCH_TARGET_TOP_N.",
    )
    parser.add_argument(
        "--research-max-signal-batches",
        type=int,
        default=None,
        help=(
            "Maximum historical signal batches for optional research preview. "
            "Env: SQV2_RESEARCH_MAX_SIGNAL_BATCHES."
        ),
    )
    parser.add_argument(
        "--research-min-candidate-rows",
        type=int,
        default=None,
        help=(
            "Minimum candidate rows for optional research DB-write preview. "
            "Env: SQV2_RESEARCH_MIN_CANDIDATE_ROWS."
        ),
    )
    parser.add_argument(
        "--enable-m6-5-campaign",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Enable optional M6.5 Forward Paper Campaign daily runner in runtime/full profiles. "
            "Default is disabled. Env: SQV2_DAILY_ENABLE_M6_5_CAMPAIGN."
        ),
    )
    parser.add_argument(
        "--m6-5-campaign-config",
        default=None,
        help=(
            "Optional path to active_campaigns.json for M6.5. "
            "Env: SQV2_M6_5_CAMPAIGN_CONFIG."
        ),
    )
    parser.add_argument(
        "--enable-m6-5-campaign-summary",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Enable automatic M6.5 production paper-campaign summary after the daily campaign runner. "
            "Default follows --enable-m6-5-campaign. Env: SQV2_DAILY_ENABLE_M6_5_CAMPAIGN_SUMMARY."
        ),
    )
    parser.add_argument(
        "--m6-5-campaign-summary-execution-context",
        default=None,
        help=(
            "Campaign execution_context filter for automatic M6.5 summary. "
            "Default: production_paper_campaign. Env: SQV2_M6_5_CAMPAIGN_SUMMARY_EXECUTION_CONTEXT."
        ),
    )
    parser.add_argument(
        "--enable-production-daily-observation-report",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Enable production daily observation report at the end of runtime/full profiles. "
            "Default: enabled. Env: SQV2_DAILY_ENABLE_PRODUCTION_DAILY_OBSERVATION_REPORT."
        ),
    )
    parser.add_argument(
        "--production-daily-observation-output-root",
        default=None,
        help=(
            "Output root for production daily observation reports. "
            "Default: artifacts/production/daily_observation. "
            "Env: SQV2_PRODUCTION_DAILY_OBSERVATION_OUTPUT_ROOT."
        ),
    )
    parser.add_argument(
        "--production-daily-observation-execution-context",
        default=None,
        help=(
            "Campaign execution_context included in production daily observation report. "
            "Default: production_paper_campaign. "
            "Env: SQV2_PRODUCTION_DAILY_OBSERVATION_EXECUTION_CONTEXT."
        ),
    )
    return parser


def run_daily_project_runtime_chain(args: argparse.Namespace) -> int:
    project_root = _detect_project_root(args.project_root)
    loaded_env_path = _load_env_file(project_root, args.env_file)
    args = _resolve_options_from_env(args)

    env = _build_runtime_env(project_root, args.report_date)
    steps = _build_steps(args)

    print(f"[DAILY] Project {args.profile} chain started.", flush=True)
    print(f"[DAILY] project_root = {project_root}", flush=True)
    if loaded_env_path is not None:
        print(f"[DAILY] env_file = {loaded_env_path}", flush=True)
    print(f"[DAILY] profile = {args.profile}", flush=True)
    print(f"[DAILY] continue_on_error = {args.continue_on_error}", flush=True)
    print(f"[DAILY] python_executable = {args.python_executable}", flush=True)
    print(f"[DAILY] PYTHONPATH = {env.get('PYTHONPATH', '')}", flush=True)
    print(f"[DAILY] paper_mode = {args.paper_mode}", flush=True)
    if args.paper_portfolio_id is not None:
        print(f"[DAILY] paper_portfolio_id = {args.paper_portfolio_id}", flush=True)
    if args.skip_m5:
        print("[DAILY] skip_m5 = True", flush=True)
    if args.skip_m8_daily_ops:
        print("[DAILY] skip_m8_daily_ops = True", flush=True)
    if args.profile in {"research", "full"}:
        print(f"[DAILY] enable_m8_ops_master = {args.enable_m8_ops_master}", flush=True)
        print(
            f"[DAILY] enable_regime_state_machine_research = {args.enable_regime_state_machine_research}",
            flush=True,
        )
        if args.enable_regime_state_machine_research:
            print(f"[DAILY] research_strategy_code = {args.research_strategy_code}", flush=True)
            print(
                f"[DAILY] research_strategy_version_code = {args.research_strategy_version_code}",
                flush=True,
            )
            print(f"[DAILY] research_target_top_n = {args.research_target_top_n}", flush=True)
            print(
                f"[DAILY] research_max_signal_batches = {args.research_max_signal_batches}",
                flush=True,
            )
            print(
                f"[DAILY] research_min_candidate_rows = {args.research_min_candidate_rows}",
                flush=True,
            )
    if getattr(args, "enable_m6_5_campaign", False):
        print("[DAILY] enable_m6_5_campaign = True", flush=True)
        if getattr(args, "m6_5_campaign_config", None):
            print(f"[DAILY] m6_5_campaign_config = {args.m6_5_campaign_config}", flush=True)
        print(
            f"[DAILY] enable_m6_5_campaign_summary = {args.enable_m6_5_campaign_summary}",
            flush=True,
        )
        if getattr(args, "enable_m6_5_campaign_summary", False):
            print(
                "[DAILY] m6_5_campaign_summary_execution_context = "
                f"{args.m6_5_campaign_summary_execution_context}",
                flush=True,
            )
    if getattr(args, "enable_production_daily_observation_report", True):
        print("[DAILY] enable_production_daily_observation_report = True", flush=True)
        print(
            "[DAILY] production_daily_observation_output_root = "
            f"{args.production_daily_observation_output_root}",
            flush=True,
        )
        print(
            "[DAILY] production_daily_observation_execution_context = "
            f"{args.production_daily_observation_execution_context}",
            flush=True,
        )
    if env.get("M8_REPORT_DATE"):
        print(f"[DAILY] M8_REPORT_DATE = {env['M8_REPORT_DATE']}", flush=True)

    failures: list[str] = []

    for step in steps:
        if step.optional and not _module_file_exists(project_root, step.module_name):
            print(
                f"\n[DAILY][{step.name}] skipped optional module: {step.module_name}",
                flush=True,
            )
            continue

        print(f"\n[DAILY][{step.name}] starting: {step.module_name}", flush=True)
        rc = _run_module(
            step_name=step.name,
            module_name=step.module_name,
            extra_args=step.extra_args,
            extra_env=step.extra_env,
            env=env,
            cwd=project_root,
            python_executable=args.python_executable,
        )
        if rc != 0:
            if step.soft_fail:
                print(
                    f"[DAILY][{step.name}] soft-failed (exit_code={rc}); continuing.",
                    flush=True,
                )
                continue

            failures.append(f"{step.name} (exit_code={rc})")
            print(f"[DAILY][{step.name}] failed (exit_code={rc})", flush=True)
            if not args.continue_on_error:
                print("[DAILY] Chain stopped because continue_on_error=false.", flush=True)
                return rc
        else:
            print(f"[DAILY][{step.name}] succeeded.", flush=True)

    print(f"\n[DAILY] Project {args.profile} chain completed.", flush=True)
    if failures:
        print("[DAILY] Failed steps:", flush=True)
        for item in failures:
            print(f"  - {item}", flush=True)
        return 1

    print(f"[DAILY] All {args.profile} steps succeeded.", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run_daily_project_runtime_chain(args)


if __name__ == "__main__":
    raise SystemExit(main())
