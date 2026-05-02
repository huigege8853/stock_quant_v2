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
    """Load a simple .env.research file without overriding already exported variables.

    Precedence is intentionally: CLI args > process environment > env file > defaults.
    This keeps Docker/cron/shell exports authoritative while still allowing
    .env.research.production / .env.research.research to provide local defaults.
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


def _build_runtime_steps(args: argparse.Namespace) -> list[ChainStep]:
    steps: list[ChainStep] = [
        ChainStep("m2_data_refresh", "stock_quant_v2.scripts.bootstrap_m2_data_refresh_chain"),
        ChainStep("m3_analytics_refresh", "stock_quant_v2.scripts.bootstrap_m3_analytics_refresh_chain"),
        ChainStep("m4_strategy_refresh", "stock_quant_v2.scripts.bootstrap_m4_strategy_refresh_chain"),
    ]

    if not args.skip_m5:
        steps.append(
            ChainStep("m5_research_refresh", "stock_quant_v2.scripts.bootstrap_m5_research_refresh_chain")
        )

    paper_step = _resolve_paper_step(args)
    if paper_step is not None:
        steps.append(paper_step)

    if not args.skip_m8_daily_ops:
        steps.append(
            ChainStep(
                "m8_daily_ops_entrypoint",
                "stock_quant_v2.scripts.m8_daily_ops_entrypoint",
            )
        )

    return steps


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
            "runtime = production daily path with m8_daily_ops_entrypoint; "
            "research = heavy/research path with bootstrap_m8_ops_master_chain; "
            "full = runtime + research."
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
            "Optional .env.research file to load before resolving DailyRun controls. "
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
        help="Skip M5 research refresh chain. Env: SQV2_DAILY_SKIP_M5.",
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
            "Enable M8 ops master chain for research/full profiles. "
            "Use --no-enable-m8-ops-master to disable. "
            "Env: SQV2_RESEARCH_ENABLE_M8_OPS_MASTER."
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
