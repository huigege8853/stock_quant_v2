from __future__ import annotations

import argparse
import json
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
RESEARCH_STEP_SCOPE_CHOICES = ("all", "regime_state_machine", "none")
_TRUE_VALUES = {"1", "true", "t", "yes", "y", "on"}
_FALSE_VALUES = {"0", "false", "f", "no", "n", "off"}
DEFAULT_RESEARCH_STRATEGY_CODE = "regime_sector_industry_selection_v1"
DEFAULT_RESEARCH_STRATEGY_VERSION_CODE = "v1_regime_state_machine"
DEFAULT_RESEARCH_REQUEST_ID = 47
DEFAULT_RESEARCH_INITIAL_CASH = "1000000"
DEFAULT_RESEARCH_TRANSACTION_COST_BPS = "0"
DEFAULT_RESEARCH_PRICE_SOURCE = "close"
DEFAULT_RESEARCH_M9_TOP_N = 10
DEFAULT_RESEARCH_WINDOW_TRADING_DAYS = 60


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
    default_research_min_preview_rows = min(50, int(args.research_target_top_n or 100))
    args.research_min_preview_rows_per_batch = _resolve_int_option(
        getattr(args, "research_min_preview_rows_per_batch", None),
        ("SQV2_RESEARCH_MIN_PREVIEW_ROWS_PER_BATCH",),
        default_research_min_preview_rows,
    )
    args.research_min_candidate_rows = _resolve_int_option(
        args.research_min_candidate_rows,
        ("SQV2_RESEARCH_MIN_CANDIDATE_ROWS",),
        1000,
    )
    args.enable_adaptive_m5_m9_research = _resolve_bool_option(
        getattr(args, "enable_adaptive_m5_m9_research", None),
        ("SQV2_RESEARCH_ENABLE_ADAPTIVE_M5_M9",),
        False,
    )
    args.research_request_id = _resolve_int_option(
        getattr(args, "research_request_id", None),
        ("SQV2_RESEARCH_REQUEST_ID",),
        DEFAULT_RESEARCH_REQUEST_ID,
    )
    args.research_initial_cash = _resolve_string_option(
        getattr(args, "research_initial_cash", None),
        ("SQV2_RESEARCH_INITIAL_CASH",),
        DEFAULT_RESEARCH_INITIAL_CASH,
    )
    args.research_transaction_cost_bps = _resolve_string_option(
        getattr(args, "research_transaction_cost_bps", None),
        ("SQV2_RESEARCH_TRANSACTION_COST_BPS",),
        DEFAULT_RESEARCH_TRANSACTION_COST_BPS,
    )
    args.research_price_source = _resolve_string_option(
        getattr(args, "research_price_source", None),
        ("SQV2_RESEARCH_PRICE_SOURCE",),
        DEFAULT_RESEARCH_PRICE_SOURCE,
    )
    args.research_max_candidate_dates = _resolve_int_option(
        getattr(args, "research_max_candidate_dates", None),
        ("SQV2_RESEARCH_MAX_CANDIDATE_DATES",),
        None,
    )
    args.research_window_start = _resolve_string_option(
        getattr(args, "research_window_start", None),
        ("SQV2_RESEARCH_WINDOW_START",),
        "",
    )
    args.research_window_end = _resolve_string_option(
        getattr(args, "research_window_end", None),
        ("SQV2_RESEARCH_WINDOW_END",),
        "",
    )
    default_window_trading_days = (
        int(args.research_max_candidate_dates) + 1
        if args.research_max_candidate_dates is not None
        else DEFAULT_RESEARCH_WINDOW_TRADING_DAYS
    )
    args.research_window_trading_days = _resolve_int_option(
        getattr(args, "research_window_trading_days", None),
        ("SQV2_RESEARCH_WINDOW_TRADING_DAYS",),
        default_window_trading_days,
    )
    args.research_m9_top_n = _resolve_int_option(
        getattr(args, "research_m9_top_n", None),
        ("SQV2_RESEARCH_M9_TOP_N",),
        DEFAULT_RESEARCH_M9_TOP_N,
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
    args.enable_next_trade_plan = _resolve_bool_option(
        args.enable_next_trade_plan,
        ("SQV2_DAILY_ENABLE_NEXT_TRADE_PLAN", "SQV2_ENABLE_NEXT_TRADE_PLAN"),
        bool(args.enable_m6_5_campaign),
    )
    args.next_trade_plan_execution_context = _resolve_string_option(
        args.next_trade_plan_execution_context,
        ("SQV2_NEXT_TRADE_PLAN_EXECUTION_CONTEXT",),
        "production_paper_campaign",
    )
    args.next_trade_plan_effective_date = _resolve_string_option(
        args.next_trade_plan_effective_date,
        ("SQV2_NEXT_TRADE_PLAN_EFFECTIVE_DATE",),
        "",
    )
    args.next_trade_plan_replace_existing = _resolve_bool_option(
        args.next_trade_plan_replace_existing,
        ("SQV2_NEXT_TRADE_PLAN_REPLACE_EXISTING",),
        True,
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
    args.research_step_scope = _resolve_choice_option(
        getattr(args, "research_step_scope", None),
        ("SQV2_RESEARCH_STEP_SCOPE",),
        RESEARCH_STEP_SCOPE_CHOICES,
        "all",
    )
    args.skip_research_backfill = _resolve_bool_option(
        getattr(args, "skip_research_backfill", None),
        ("SQV2_RESEARCH_SKIP_BACKFILL",),
        False,
    )
    args.research_artifact_only = _resolve_bool_option(
        getattr(args, "research_artifact_only", None),
        ("SQV2_RESEARCH_ARTIFACT_ONLY",),
        False,
    )
    if args.research_artifact_only:
        args.paper_mode = "skip"
        args.skip_m8_daily_ops = True
        args.enable_m8_ops_master = False
        args.enable_m6_5_campaign = False
        args.enable_m6_5_campaign_summary = False
        args.enable_next_trade_plan = False
        args.enable_production_daily_observation_report = False

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

    def next_trading_day(self, after_date: date) -> date | None:
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
                SELECT MIN({date_col})
                FROM {table_name}
                WHERE {open_col} = TRUE
                  AND {date_col} > :after_date
                """
                value = self._safe_scalar(session, sql, {"after_date": after_date})
                coerced = self._coerce_to_date(value)
                if coerced is not None:
                    return coerced

        return None

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

    def resolve_strategy_signal_source(
        self,
        *,
        strategy_code: str,
        strategy_version_code: str,
        effective_date: date,
    ) -> dict[str, object] | None:
        """Resolve the exact signal run for a campaign strategy/version/date.

        The next-trade plan runner must not fall back to a global latest
        strategy_signal run.  It should carry the campaign's own strategy_code
        and strategy_version_code into M7 as an explicit source_signal_run_id.
        """
        from stock_quant_v2.db.session import SessionLocal

        sql = """
        select
            ss.run_id as source_signal_run_id,
            max(ss.as_of_date) as as_of_date,
            max(ss.effective_date) as effective_date,
            max(ss.strategy_version_id) as strategy_version_id
        from strategy_signal ss
        join strategy_version sv on sv.id = ss.strategy_version_id
        join strategy_definition sd on sd.id = sv.strategy_definition_id
        where sd.strategy_code = :strategy_code
          and sv.version_code = :strategy_version_code
          and ss.effective_date = :effective_date
        group by ss.run_id
        order by ss.run_id desc
        limit 1
        """
        params = {
            "strategy_code": strategy_code,
            "strategy_version_code": strategy_version_code,
            "effective_date": effective_date,
        }
        with SessionLocal() as session:
            try:
                row = session.execute(text(sql), params).mappings().one_or_none()
            except Exception:
                return None
            if row is None:
                return None

            source_signal_run_id = int(row["source_signal_run_id"])
            screen_request_id = self._safe_scalar(
                session,
                """
                select screen_request_id
                from research_screen_result
                where signal_run_id = :source_signal_run_id
                  and result_status = 'SUCCESS'
                  and effective_date <= :effective_date
                order by effective_date desc, id desc
                limit 1
                """,
                {
                    "source_signal_run_id": source_signal_run_id,
                    "effective_date": effective_date,
                },
            )
            return {
                "source_signal_run_id": source_signal_run_id,
                "source_screen_request_id": int(screen_request_id) if screen_request_id is not None else None,
                "as_of_date": self._coerce_to_date(row["as_of_date"]),
                "effective_date": self._coerce_to_date(row["effective_date"]),
                "strategy_version_id": int(row["strategy_version_id"]),
            }

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


def _resolve_relative_path(project_root: Path, value: str | None) -> Path | None:
    if value is None or str(value).strip() == "":
        return None

    path = Path(str(value).strip())
    if path.is_absolute():
        return path
    return project_root / path


def _load_next_trade_plan_campaigns(
    *,
    project_root: Path,
    config_path: str | None,
    execution_context: str,
) -> list[dict]:
    resolved_config = _resolve_relative_path(project_root, config_path)
    if resolved_config is None:
        default_config = project_root / "configs" / "paper_campaigns" / "active_campaigns.json"
        resolved_config = default_config if default_config.exists() else None

    if resolved_config is None or not resolved_config.exists():
        return []

    data = json.loads(resolved_config.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"campaign config must be a list: {resolved_config}")

    campaigns: list[dict] = []
    for raw in data:
        if not isinstance(raw, dict):
            continue
        status = str(raw.get("status") or "").upper()
        run_mode = str(raw.get("run_mode") or "").lower()
        raw_execution_context = str(raw.get("execution_context") or "")
        portfolio_id = raw.get("portfolio_id")

        if status != "ACTIVE":
            continue
        if run_mode != "auto":
            continue
        if raw_execution_context != execution_context:
            continue
        if portfolio_id in (None, ""):
            continue

        campaigns.append(raw)

    return campaigns


def _resolve_next_trade_plan_effective_date(args: argparse.Namespace) -> date | None:
    if getattr(args, "next_trade_plan_effective_date", None):
        return date.fromisoformat(str(args.next_trade_plan_effective_date))

    inspector = DatabaseInspector()
    latest_day = inspector.latest_trading_day()
    if latest_day is None:
        return None
    return inspector.next_trading_day(latest_day)


def _build_next_trade_plan_steps(project_root: Path, args: argparse.Namespace) -> list[ChainStep]:
    if not getattr(args, "enable_next_trade_plan", False):
        return []

    effective_date = _resolve_next_trade_plan_effective_date(args)
    if effective_date is None:
        return []

    campaigns = _load_next_trade_plan_campaigns(
        project_root=project_root,
        config_path=getattr(args, "m6_5_campaign_config", None),
        execution_context=str(args.next_trade_plan_execution_context),
    )
    steps: list[ChainStep] = []
    inspector = DatabaseInspector()

    for campaign in campaigns:
        portfolio_id = int(campaign["portfolio_id"])
        campaign_code = str(campaign.get("campaign_code") or f"portfolio_{portfolio_id}")
        strategy_code = str(campaign.get("strategy_code") or "").strip()
        strategy_version_code = str(campaign.get("strategy_version_code") or "").strip()
        if not strategy_code or not strategy_version_code:
            print(
                "[DAILY][next_trade_plan] skip campaign because strategy_code/version is missing: "
                f"campaign_code={campaign_code}",
                flush=True,
            )
            continue

        signal_source = inspector.resolve_strategy_signal_source(
            strategy_code=strategy_code,
            strategy_version_code=strategy_version_code,
            effective_date=effective_date,
        )
        if signal_source is None:
            print(
                "[DAILY][next_trade_plan] skip campaign because exact strategy signal is missing: "
                f"campaign_code={campaign_code}, strategy_code={strategy_code}, "
                f"strategy_version_code={strategy_version_code}, effective_date={effective_date.isoformat()}",
                flush=True,
            )
            continue

        source_signal_run_id = int(signal_source["source_signal_run_id"])
        source_as_of_date = signal_source.get("as_of_date")
        source_screen_request_id = signal_source.get("source_screen_request_id")
        step_name = f"m7_next_trade_plan_only_p{portfolio_id}"
        extra_args = [
            "--portfolio-id",
            str(portfolio_id),
            "--effective-date",
            effective_date.isoformat(),
            "--plan-only",
            "--source-signal-run-id",
            str(source_signal_run_id),
            "--strategy-code",
            strategy_code,
            "--strategy-version-code",
            strategy_version_code,
        ]
        if source_as_of_date is not None:
            extra_args.extend(["--as-of-date", source_as_of_date.isoformat()])
        if source_screen_request_id is not None:
            extra_args.extend(["--source-screen-request-id", str(source_screen_request_id)])
        if getattr(args, "next_trade_plan_replace_existing", True):
            extra_args.append("--replace-existing")

        print(
            "[DAILY][next_trade_plan] resolved exact campaign signal: "
            f"campaign_code={campaign_code}, portfolio_id={portfolio_id}, "
            f"strategy_code={strategy_code}, strategy_version_code={strategy_version_code}, "
            f"source_signal_run_id={source_signal_run_id}, effective_date={effective_date.isoformat()}",
            flush=True,
        )
        steps.append(
            ChainStep(
                step_name,
                "stock_quant_v2.scripts.bootstrap_m7_daily_refresh_chain",
                extra_args=tuple(extra_args),
                optional=True,
                soft_fail=True,
                extra_env={
                    "SQV2_NEXT_TRADE_PLAN_CAMPAIGN_CODE": campaign_code,
                    "SQV2_NEXT_TRADE_PLAN_EFFECTIVE_DATE": effective_date.isoformat(),
                    "SQV2_NEXT_TRADE_PLAN_STRATEGY_CODE": strategy_code,
                    "SQV2_NEXT_TRADE_PLAN_STRATEGY_VERSION_CODE": strategy_version_code,
                    "SQV2_NEXT_TRADE_PLAN_SOURCE_SIGNAL_RUN_ID": str(source_signal_run_id),
                },
            )
        )

    return steps


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


def _build_runtime_steps(args: argparse.Namespace, project_root: Path) -> list[ChainStep]:
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

        steps.extend(_build_next_trade_plan_steps(project_root, args))

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
    historical_request_dir = f"artifacts/m5/research_chain_{label}/historical_backtest_request_design"
    window_filter_dir = f"{base_dir}/window_filtered_candidate_signal_rows"
    input_enrichment_dir = f"artifacts/m5/research_chain_{label}/adaptive_execution_input_enrichment"
    dry_run_dir = f"artifacts/m5/research_chain_{label}/adaptive_execution_dry_run"
    attribution_dir = f"artifacts/m9/research_chain_{label}/adaptive_execution_attribution"
    request_id = int(getattr(args, "research_request_id", DEFAULT_RESEARCH_REQUEST_ID) or DEFAULT_RESEARCH_REQUEST_ID)
    input_enrichment_request_dir = f"{input_enrichment_dir}/request_{request_id}"
    dry_run_request_dir = f"{dry_run_dir}/request_{request_id}"
    enriched_candidate_csv = f"{input_enrichment_request_dir}/enriched_candidate_signal_rows.csv"
    window_start = getattr(args, "research_window_start", None)
    window_end = getattr(args, "research_window_end", None)
    has_research_window_filter = bool(window_start and window_end)
    window_report_date = args.report_date or window_end or "latest"
    window_token = f"{str(window_start).replace('-', '')}_{str(window_end).replace('-', '')}"
    window_filtered_candidate_csv = (
        f"{window_filter_dir}/request_{request_id}/"
        f"window_filtered_candidate_signal_rows_{window_report_date}_{window_token}.csv"
    )
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

    steps: list[ChainStep] = []

    if has_research_window_filter:
        steps.append(
            ChainStep(
                "m5_window_bound_historical_request_design",
                "stock_quant_v2.scripts.bootstrap_m5_backtest_historical_request_design",
                extra_args=(
                    *common_strategy_args,
                    "--mode",
                    "design",
                    "--output-dir",
                    historical_request_dir,
                    "--target-trading-days",
                    str(getattr(args, "research_window_trading_days", DEFAULT_RESEARCH_WINDOW_TRADING_DAYS)),
                    "--max-signal-plan-rows",
                    str(args.research_max_signal_batches),
                    "--historical-anchor-date",
                    str(window_end or args.report_date),
                    "--research-backtest-request-id",
                    str(request_id),
                ),
            )
        )

    m4_historical_request_artifact_dir = (
        historical_request_dir if has_research_window_filter else "artifacts/m5/historical_backtest_request_design"
    )

    steps.extend([
        ChainStep(
            "m4_regime_sm_historical_design",
            "stock_quant_v2.scripts.bootstrap_m4_historical_signal_generation_design",
            extra_args=(
                *common_strategy_args,
                "--mode",
                "design",
                "--historical-request-artifact-dir",
                m4_historical_request_artifact_dir,
                "--research-backtest-request-id",
                str(request_id),
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
                "--research-backtest-request-id",
                str(request_id),
                "--design-artifact-dir",
                design_dir,
                "--output-dir",
                preview_dir,
                "--target-top-n",
                str(args.research_target_top_n),
                "--max-signal-batches",
                str(args.research_max_signal_batches),
                "--min-preview-rows-per-batch",
                str(args.research_min_preview_rows_per_batch),
            ),
        ),
        ChainStep(
            "m4_regime_sm_db_write_preview",
            "stock_quant_v2.scripts.bootstrap_m4_historical_signal_generation_design",
            extra_args=(
                *common_strategy_args,
                "--mode",
                "db_write_preview",
                "--research-backtest-request-id",
                str(request_id),
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
    ])

    if has_research_window_filter:
        steps.append(
            ChainStep(
                "m4_regime_sm_candidate_window_filter",
                "stock_quant_v2.scripts.bootstrap_research_candidate_window_filter",
                extra_args=(
                    "--project-root",
                    ".",
                    *report_date_args,
                    "--candidate-signal-artifact-dir",
                    preview_dir,
                    "--output-dir",
                    window_filter_dir,
                    "--request-id",
                    str(request_id),
                    "--window-start",
                    str(window_start),
                    "--window-end",
                    str(window_end),
                    "--min-candidate-rows",
                    str(args.research_min_candidate_rows),
                ),
                soft_fail=bool(
                    getattr(args, "enable_adaptive_m5_m9_research", False)
                    and getattr(args, "research_artifact_only", False)
                ),
            )
        )

    if getattr(args, "enable_adaptive_m5_m9_research", False):
        input_enrichment_args: list[str] = [
            "--project-root",
            ".",
            *report_date_args,
            "--request-id",
            str(request_id),
            "--candidate-signal-artifact-dir",
            preview_dir,
            "--output-dir",
            input_enrichment_dir,
            "--price-source",
            str(getattr(args, "research_price_source", DEFAULT_RESEARCH_PRICE_SOURCE)),
        ]
        if has_research_window_filter:
            input_enrichment_args.extend(["--candidate-signal-csv", window_filtered_candidate_csv])

        dry_run_args: list[str] = [
            "--project-root",
            ".",
            *report_date_args,
            "--request-id",
            str(request_id),
            "--candidate-signal-artifact-dir",
            preview_dir,
            "--candidate-signal-csv",
            enriched_candidate_csv,
            "--output-dir",
            dry_run_dir,
            "--initial-cash",
            str(getattr(args, "research_initial_cash", DEFAULT_RESEARCH_INITIAL_CASH)),
            "--transaction-cost-bps",
            str(getattr(args, "research_transaction_cost_bps", DEFAULT_RESEARCH_TRANSACTION_COST_BPS)),
            "--execution-price-column",
            "execution_price",
        ]
        max_candidate_dates = getattr(args, "research_max_candidate_dates", None)
        if max_candidate_dates is not None:
            input_enrichment_args.extend(["--max-candidate-dates", str(max_candidate_dates)])
            dry_run_args.extend(["--max-candidate-dates", str(max_candidate_dates)])
        m9_attribution_args: list[str] = [
            "--project-root",
            ".",
            *report_date_args,
            "--request-id",
            str(request_id),
            "--dry-run-artifact-dir",
            dry_run_request_dir,
            "--input-enrichment-artifact-dir",
            input_enrichment_request_dir,
            "--output-dir",
            attribution_dir,
            "--top-n",
            str(getattr(args, "research_m9_top_n", DEFAULT_RESEARCH_M9_TOP_N)),
        ]
        steps.extend(
            [
                ChainStep(
                    "m5_adaptive_execution_input_enrichment",
                    "stock_quant_v2.scripts.bootstrap_m5_adaptive_execution_input_enrichment",
                    extra_args=tuple(input_enrichment_args),
                ),
                ChainStep(
                    "m5_adaptive_execution_dry_run",
                    "stock_quant_v2.scripts.bootstrap_m5_adaptive_execution_dry_run",
                    extra_args=tuple(dry_run_args),
                ),
                ChainStep(
                    "m9_adaptive_execution_attribution_report",
                    "stock_quant_v2.scripts.bootstrap_m9_adaptive_execution_attribution_report",
                    extra_args=tuple(m9_attribution_args),
                ),
            ]
        )

    return steps



# STAGE6_23R17_RESEARCH_BACKFILL_DATE_ARGS_BEGIN
def _build_research_backfill_date_args(args: argparse.Namespace) -> list[str]:
    """Pass research window dates to child historical backfill modules."""
    extra_args: list[str] = []
    window_start = str(getattr(args, "research_window_start", "") or "").strip()
    window_end = str(getattr(args, "research_window_end", "") or "").strip()
    if window_start:
        extra_args.extend(["--start-date", window_start])
    if window_end:
        extra_args.extend(["--end-date", window_end])
    return extra_args
# STAGE6_23R17_RESEARCH_BACKFILL_DATE_ARGS_END

def _build_research_steps(
    args: argparse.Namespace,
    *,
    include_m5_refresh: bool,
) -> list[ChainStep]:
    steps: list[ChainStep] = []
    research_step_scope = getattr(args, "research_step_scope", "all")

    if research_step_scope == "none":
        return steps

    # Optional heavy/research modules are skipped when the current branch does
    # not contain them yet. This lets the production runtime profile stay stable
    # while research capabilities are introduced incrementally.
    if research_step_scope == "all" and not getattr(args, "skip_research_backfill", False):
        steps.extend(
            [
                ChainStep(
                    "m3_historical_feature_backfill_p1",
                    "stock_quant_v2.scripts.bootstrap_m3_historical_feature_backfill_p1",
                    extra_args=tuple(_build_research_backfill_date_args(args)),  # m3_historical_feature_backfill_p1_STAGE6_23R17
                    optional=True,
                ),
                ChainStep(
                    "m5_historical_signal_backfill_p1",
                    "stock_quant_v2.scripts.bootstrap_m5_historical_signal_backfill_p1",
                    extra_args=tuple(_build_research_backfill_date_args(args)),  # m5_historical_signal_backfill_p1_STAGE6_23R17
                    optional=True,
                ),
            ]
        )

    if research_step_scope == "all" and include_m5_refresh and not args.skip_m5:
        steps.append(
            ChainStep("m5_research_refresh", "stock_quant_v2.scripts.bootstrap_m5_research_refresh_chain")
        )

    if research_step_scope in {"all", "regime_state_machine"} and args.enable_regime_state_machine_research:
        steps.extend(_build_regime_state_machine_research_steps(args))

    if research_step_scope == "all" and args.enable_m8_ops_master:
        steps.append(
            ChainStep(
                "m8_ops_master_chain",
                "stock_quant_v2.scripts.bootstrap_m8_ops_master_chain",
                extra_args=("--continue-on-error",),
                soft_fail=True,
            )
        )

    return steps

def _build_steps(args: argparse.Namespace, project_root: Path) -> list[ChainStep]:
    if args.profile == "runtime":
        return _build_runtime_steps(args, project_root)

    if args.profile == "research":
        return _build_research_steps(args, include_m5_refresh=True)

    if args.profile == "full":
        return [
            *_build_runtime_steps(args, project_root),
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
        "--research-min-preview-rows-per-batch",
        type=int,
        default=None,
        help=(
            "Minimum preview rows per M4 historical signal batch in research quick-scope. "
            "Default is min(50, --research-target-top-n), so top30 research smoke does not fail a top50 floor. "
            "Env: SQV2_RESEARCH_MIN_PREVIEW_ROWS_PER_BATCH."
        ),
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
        "--enable-adaptive-m5-m9-research",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Enable optional artifact-only M5 input enrichment, M5 adaptive dry-run, "
            "and M9 adaptive attribution after the regime state-machine M4 preview chain. "
            "Env: SQV2_RESEARCH_ENABLE_ADAPTIVE_M5_M9."
        ),
    )
    parser.add_argument(
        "--research-request-id",
        type=int,
        default=None,
        help="Request id for optional adaptive M5/M9 research artifacts. Env: SQV2_RESEARCH_REQUEST_ID.",
    )
    parser.add_argument(
        "--research-initial-cash",
        default=None,
        help="Initial cash for optional M5 adaptive dry-run. Env: SQV2_RESEARCH_INITIAL_CASH.",
    )
    parser.add_argument(
        "--research-transaction-cost-bps",
        default=None,
        help="Transaction cost bps for optional M5 adaptive dry-run. Env: SQV2_RESEARCH_TRANSACTION_COST_BPS.",
    )
    parser.add_argument(
        "--research-price-source",
        default=None,
        help="Execution price source for optional M5 input enrichment. Env: SQV2_RESEARCH_PRICE_SOURCE.",
    )
    parser.add_argument(
        "--research-max-candidate-dates",
        type=int,
        default=None,
        help="Optional cap on candidate dates for optional M5 adaptive research smoke. Env: SQV2_RESEARCH_MAX_CANDIDATE_DATES.",
    )
    parser.add_argument(
        "--research-window-start",
        default=None,
        help=(
            "Inclusive start date for strict research walk-forward window filtering, format YYYY-MM-DD. "
            "When paired with --research-window-end, daily runtime writes a window-filtered M4 candidate CSV "
            "and feeds it to M5 adaptive research. Env: SQV2_RESEARCH_WINDOW_START."
        ),
    )
    parser.add_argument(
        "--research-window-end",
        default=None,
        help=(
            "Inclusive end date for strict research walk-forward window filtering, format YYYY-MM-DD. "
            "When paired with --research-window-start, daily runtime writes a window-filtered M4 candidate CSV "
            "and feeds it to M5 adaptive research. Env: SQV2_RESEARCH_WINDOW_END."
        ),
    )
    parser.add_argument(
        "--research-window-trading-days",
        type=int,
        default=None,
        help=(
            "Trading-day span used by the window-bound M5 historical request design. "
            "Default is --research-max-candidate-dates + 1, or 60. Env: SQV2_RESEARCH_WINDOW_TRADING_DAYS."
        ),
    )
    parser.add_argument(
        "--research-m9-top-n",
        type=int,
        default=None,
        help="Top/bottom rows for optional M9 adaptive attribution. Env: SQV2_RESEARCH_M9_TOP_N.",
    )
    parser.add_argument(
        "--research-step-scope",
        choices=RESEARCH_STEP_SCOPE_CHOICES,
        default=None,
        help=(
            "Limit research profile steps. all = existing behavior; "
            "regime_state_machine = run only optional regime-state-machine research chain; "
            "none = skip research-only steps. Env: SQV2_RESEARCH_STEP_SCOPE."
        ),
    )
    parser.add_argument(
        "--skip-research-backfill",
        action="store_true",
        default=None,
        help=(
            "Skip optional research historical backfill steps in research/full profiles. "
            "Env: SQV2_RESEARCH_SKIP_BACKFILL."
        ),
    )
    parser.add_argument(
        "--research-artifact-only",
        action="store_true",
        default=None,
        help=(
            "Research safety guard: force paper_mode=skip, skip M8 ops, disable production daily observation, "
            "and keep execution artifact-only. Env: SQV2_RESEARCH_ARTIFACT_ONLY."
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
        "--enable-next-trade-plan",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Enable automatic M7 plan-only next-trade target/order generation after M6.5 daily campaign. "
            "This writes target/order rows only and must not write fill, position, or snapshot rows. "
            "Default follows --enable-m6-5-campaign. Env: SQV2_DAILY_ENABLE_NEXT_TRADE_PLAN."
        ),
    )
    parser.add_argument(
        "--next-trade-plan-execution-context",
        default=None,
        help=(
            "Campaign execution_context filter for automatic next-trade plan-only generation. "
            "Default: production_paper_campaign. Env: SQV2_NEXT_TRADE_PLAN_EXECUTION_CONTEXT."
        ),
    )
    parser.add_argument(
        "--next-trade-plan-effective-date",
        default=None,
        help=(
            "Optional override for next-trade plan effective_date, format YYYY-MM-DD. "
            "Default: next open trading day after latest trading day. Env: SQV2_NEXT_TRADE_PLAN_EFFECTIVE_DATE."
        ),
    )
    parser.add_argument(
        "--next-trade-plan-replace-existing",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Pass --replace-existing to M7 plan-only next-trade generation. "
            "Default: true for daily runtime idempotency. Env: SQV2_NEXT_TRADE_PLAN_REPLACE_EXISTING."
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
    steps = _build_steps(args, project_root)

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
        print(f"[DAILY] research_step_scope = {getattr(args, 'research_step_scope', 'all')}", flush=True)
        print(f"[DAILY] skip_research_backfill = {getattr(args, 'skip_research_backfill', False)}", flush=True)
        print(f"[DAILY] research_artifact_only = {getattr(args, 'research_artifact_only', False)}", flush=True)
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
                f"[DAILY] research_min_preview_rows_per_batch = {args.research_min_preview_rows_per_batch}",
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
