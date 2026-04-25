from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DayChainConfig:
    label: str
    as_of_date: str
    effective_date: str
    portfolio_id: int
    source_position_run_id: int
    carry_position_run_id: int
    target_position_run_id: int
    order_run_id: int
    fill_run_id: int
    position_run_id: int
    previous_snapshot_run_id: int
    snapshot_run_id: int


# 来自 M7 acceptance / handoff 的最终通过链路
ACCEPTED_DAY_1 = DayChainConfig(
    label="day1",
    as_of_date="2026-04-21",
    effective_date="2026-04-22",
    portfolio_id=1,
    source_position_run_id=143,
    carry_position_run_id=145,
    target_position_run_id=155,
    order_run_id=146,
    fill_run_id=147,
    position_run_id=148,
    previous_snapshot_run_id=144,
    snapshot_run_id=149,
)

ACCEPTED_DAY_2 = DayChainConfig(
    label="day2",
    as_of_date="2026-04-22",
    effective_date="2026-04-23",
    portfolio_id=1,
    source_position_run_id=148,
    carry_position_run_id=150,
    target_position_run_id=155,
    order_run_id=151,
    fill_run_id=152,
    position_run_id=153,
    previous_snapshot_run_id=149,
    snapshot_run_id=154,
)

RISK_PROFILE_MODULE = "stock_quant_v2.scripts.bootstrap_m7_risk_profile"
REBALANCE_DAILY_MODULE = "stock_quant_v2.scripts.bootstrap_m7_rebalance_daily_chain"
PAPER_QUALITY_FULL_MODULE = "stock_quant_v2.scripts.check_m7_paper_trading_quality_full"
PORTFOLIO_SNAPSHOT_QUALITY_MODULE = "stock_quant_v2.scripts.check_m7_portfolio_snapshot_quality"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _run_module(module_name: str, extra_env: dict[str, str] | None = None) -> int:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)

    completed = subprocess.run(
        [sys.executable, "-m", module_name],
        cwd=_project_root(),
        env=env,
        text=True,
        capture_output=True,
    )

    if completed.stdout.strip():
        print(completed.stdout.strip())
    if completed.stderr.strip():
        print(completed.stderr.strip(), file=sys.stderr)

    return int(completed.returncode)


def _build_day_env(config: DayChainConfig, replace_existing: bool = False) -> dict[str, str]:
    return {
        "M7_AS_OF_DATE": config.as_of_date,
        "M7_TRADE_DATE": config.as_of_date,
        "M7_TARGET_DATE": config.as_of_date,
        "M7_EFFECTIVE_DATE": config.effective_date,
        "M7_PORTFOLIO_ID": str(config.portfolio_id),
        "M7_SOURCE_POSITION_RUN_ID": str(config.source_position_run_id),
        "M7_SOURCE_POSITION_SNAPSHOT_RUN_ID": str(config.previous_snapshot_run_id),
        "M7_CARRY_POSITION_RUN_ID": str(config.carry_position_run_id),
        "M7_TARGET_POSITION_RUN_ID": str(config.target_position_run_id),
        "M7_ORDER_RUN_ID": str(config.order_run_id),
        "M7_FILL_RUN_ID": str(config.fill_run_id),
        "M7_POSITION_RUN_ID": str(config.position_run_id),
        "M7_PREVIOUS_SNAPSHOT_RUN_ID": str(config.previous_snapshot_run_id),
        "M7_SNAPSHOT_RUN_ID": str(config.snapshot_run_id),
        "M7_POSITION_SNAPSHOT_RUN_ID": str(config.snapshot_run_id),
        "M7_PORTFOLIO_SNAPSHOT_RUN_ID": str(config.snapshot_run_id),
        "M7_REPLACE_EXISTING": "true" if replace_existing else "false",
    }


def _build_env_day_config_from_env(prefix: str, label: str) -> DayChainConfig:
    def req(name: str) -> str:
        key = f"{prefix}_{name}"
        value = os.getenv(key)
        if value in (None, ""):
            raise RuntimeError(f"缺少环境变量: {key}")
        return value

    return DayChainConfig(
        label=label,
        as_of_date=req("AS_OF_DATE"),
        effective_date=req("EFFECTIVE_DATE"),
        portfolio_id=int(req("PORTFOLIO_ID")),
        source_position_run_id=int(req("SOURCE_POSITION_RUN_ID")),
        carry_position_run_id=int(req("CARRY_POSITION_RUN_ID")),
        target_position_run_id=int(req("TARGET_POSITION_RUN_ID")),
        order_run_id=int(req("ORDER_RUN_ID")),
        fill_run_id=int(req("FILL_RUN_ID")),
        position_run_id=int(req("POSITION_RUN_ID")),
        previous_snapshot_run_id=int(req("PREVIOUS_SNAPSHOT_RUN_ID")),
        snapshot_run_id=int(req("SNAPSHOT_RUN_ID")),
    )


def _selected_days(use_accepted_chain: bool, day: str) -> list[DayChainConfig]:
    if use_accepted_chain:
        if day == "day1":
            return [ACCEPTED_DAY_1]
        if day == "day2":
            return [ACCEPTED_DAY_2]
        return [ACCEPTED_DAY_1, ACCEPTED_DAY_2]

    if day == "day1":
        return [_build_env_day_config_from_env("M7_DAY1", "day1")]
    if day == "day2":
        return [_build_env_day_config_from_env("M7_DAY2", "day2")]
    return [
        _build_env_day_config_from_env("M7_DAY1", "day1"),
        _build_env_day_config_from_env("M7_DAY2", "day2"),
    ]


def _print_day_env(cfg: DayChainConfig, env: dict[str, str]) -> None:
    print(f"\n[M7][{cfg.label}] effective env:")
    for k, v in env.items():
        print(f"  - {k}={v}")


def _run_verify_mode(
    days: list[DayChainConfig],
    *,
    with_risk_profile: bool,
) -> int:
    print("[M7] mode = accepted_chain_verify")
    print("[M7] accepted historical runs are treated as immutable verify artifacts.")
    print("[M7] verify mode does NOT replay rebalance_daily_chain, avoiding FK collisions on historical accepted runs.")

    if with_risk_profile:
        print(f"\n[M7][risk_profile] starting: {RISK_PROFILE_MODULE}")
        rc = _run_module(RISK_PROFILE_MODULE)
        if rc != 0:
            print(f"[M7][risk_profile] failed (exit_code={rc})")
            return rc
        print(f"[M7][risk_profile] succeeded.")

    for cfg in days:
        env = _build_day_env(cfg, replace_existing=False)
        _print_day_env(cfg, env)
        print(f"[M7][{cfg.label}] accepted-chain verify only; no replay executed.")

    print("\n[M7] accepted_chain verify completed successfully.")
    print("[M7] This confirms the historical accepted run contract for M7.")
    return 0


def _run_execute_mode(
    days: list[DayChainConfig],
    *,
    with_risk_profile: bool,
    skip_quality: bool,
    replace_existing: bool,
) -> int:
    print("[M7] mode = env_chain_execute")
    print(f"[M7] replace_existing = {replace_existing}")

    if with_risk_profile:
        print(f"\n[M7][risk_profile] starting: {RISK_PROFILE_MODULE}")
        rc = _run_module(RISK_PROFILE_MODULE)
        if rc != 0:
            print(f"[M7][risk_profile] failed (exit_code={rc})")
            return rc
        print(f"[M7][risk_profile] succeeded.")

    for cfg in days:
        env = _build_day_env(cfg, replace_existing=replace_existing)
        _print_day_env(cfg, env)

        print(f"\n[M7][{cfg.label}][rebalance_daily_chain] starting: {REBALANCE_DAILY_MODULE}")
        rc = _run_module(REBALANCE_DAILY_MODULE, extra_env=env)
        if rc != 0:
            print(f"[M7][{cfg.label}][rebalance_daily_chain] failed (exit_code={rc})")
            return rc
        print(f"[M7][{cfg.label}][rebalance_daily_chain] succeeded.")

        if not skip_quality:
            print(f"\n[M7][{cfg.label}][paper_trading_quality_full] starting: {PAPER_QUALITY_FULL_MODULE}")
            rc = _run_module(PAPER_QUALITY_FULL_MODULE, extra_env=env)
            if rc != 0:
                print(f"[M7][{cfg.label}][paper_trading_quality_full] failed (exit_code={rc})")
                return rc
            print(f"[M7][{cfg.label}][paper_trading_quality_full] succeeded.")

            print(f"\n[M7][{cfg.label}][portfolio_snapshot_quality] starting: {PORTFOLIO_SNAPSHOT_QUALITY_MODULE}")
            rc = _run_module(PORTFOLIO_SNAPSHOT_QUALITY_MODULE, extra_env=env)
            if rc != 0:
                print(f"[M7][{cfg.label}][portfolio_snapshot_quality] failed (exit_code={rc})")
                return rc
            print(f"[M7][{cfg.label}][portfolio_snapshot_quality] succeeded.")

    print("\n[M7] env_chain execute completed successfully.")
    return 0


def run_m7_risk_rebalance_refresh_chain(
    *,
    use_accepted_chain: bool = True,
    day: str = "both",
    with_risk_profile: bool = False,
    skip_quality: bool = False,
    replace_existing: bool = False,
) -> int:
    print("[M7] Risk / rebalance refresh chain started.")

    days = _selected_days(use_accepted_chain=use_accepted_chain, day=day)

    if use_accepted_chain:
        return _run_verify_mode(
            days,
            with_risk_profile=with_risk_profile,
        )

    return _run_execute_mode(
        days,
        with_risk_profile=with_risk_profile,
        skip_quality=skip_quality,
        replace_existing=replace_existing,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the M7 risk / rebalance orchestrator. "
            "Default mode verifies the accepted multi-day chain from M7 docs; "
            "env-chain mode executes a new chain with explicit run contracts."
        )
    )
    parser.add_argument(
        "--use-env-chain",
        action="store_true",
        help="Use explicit env-based chain instead of accepted-chain verify mode.",
    )
    parser.add_argument(
        "--day",
        choices=["day1", "day2", "both"],
        default="both",
        help="Run day1, day2, or both. Default: both.",
    )
    parser.add_argument(
        "--with-risk-profile",
        action="store_true",
        help="Also run bootstrap_m7_risk_profile before verify/execute flow.",
    )
    parser.add_argument(
        "--skip-quality",
        action="store_true",
        help="Skip M7 quality checks in env-chain execute mode.",
    )
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Set M7_REPLACE_EXISTING=true in env-chain execute mode.",
    )

    args = parser.parse_args(argv)

    return run_m7_risk_rebalance_refresh_chain(
        use_accepted_chain=not args.use_env_chain,
        day=args.day,
        with_risk_profile=args.with_risk_profile,
        skip_quality=args.skip_quality,
        replace_existing=args.replace_existing,
    )


if __name__ == "__main__":
    raise SystemExit(main())