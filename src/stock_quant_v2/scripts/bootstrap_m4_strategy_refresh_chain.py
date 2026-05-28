from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

from stock_quant_v2.config.settings import settings


@dataclass(frozen=True)
class M4Chain:
    name: str
    module_name: str


M4_MAIN_CHAIN = M4Chain(
    name="rule_strategy_chain",
    module_name="stock_quant_v2.scripts.bootstrap_m4_rule_strategy_chain",
)


M4_TARGET_CHAIN = M4Chain(
    name="regime_sector_industry_target_signal_light",
    module_name="stock_quant_v2.scripts.bootstrap_m4_regime_sector_industry_target_signal_light",
)

TARGET_STRATEGY_CODE = "regime_sector_industry_selection_v1"
TARGET_VERSION_CODE = "v1_regime_state_machine"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _run_module(
    module_name: str,
    extra_env: dict[str, str] | None = None,
    args: list[str] | None = None,
) -> int:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)

    cmd = [sys.executable, "-m", module_name]
    if args:
        cmd.extend(args)
    print(f"[M4] executing: {' '.join(cmd)}")
    completed = subprocess.run(cmd, cwd=_project_root(), env=env)
    return int(completed.returncode)


class DatabaseInspector:
    def __init__(self, db_url: str) -> None:
        self.engine = create_engine(db_url)

    def close(self) -> None:
        self.engine.dispose()

    def latest_trading_day(self) -> date | None:
        candidates = [
            ("meta_trading_calendar", "trade_date", "is_open"),
            ("meta_trading_calendar", "calendar_date", "is_open"),
            ("meta_trading_calendar", "trade_date", "is_trading_day"),
            ("meta_trading_calendar", "calendar_date", "is_trading_day"),
        ]

        for table_name, date_col, open_col in candidates:
            sql = f"""
            SELECT MAX({date_col})
            FROM {table_name}
            WHERE {open_col} = TRUE
              AND {date_col} <= CURRENT_DATE
            """
            value = self._safe_scalar(sql)
            coerced = self._coerce_to_date(value)
            if coerced is not None:
                return coerced

        fallback = self._safe_scalar("SELECT MAX(trade_date) FROM core_daily_bar")
        return self._coerce_to_date(fallback)

    def next_trading_day(self, as_of_date: date) -> date | None:
        candidates = [
            ("meta_trading_calendar", "trade_date", "is_open"),
            ("meta_trading_calendar", "calendar_date", "is_open"),
            ("meta_trading_calendar", "trade_date", "is_trading_day"),
            ("meta_trading_calendar", "calendar_date", "is_trading_day"),
        ]

        for table_name, date_col, open_col in candidates:
            sql = (
                f"SELECT MIN({date_col}) "
                f"FROM {table_name} "
                f"WHERE {open_col} = TRUE AND {date_col} > :as_of_date"
            )
            value = self._safe_scalar(sql, {"as_of_date": as_of_date})
            coerced = self._coerce_to_date(value)
            if coerced is not None:
                return coerced

        return None

    def signal_total_rows(self) -> int | None:
        value = self._safe_scalar("SELECT COUNT(*) FROM strategy_signal")
        return int(value) if value is not None else None

    def signal_latest_as_of_date(self) -> date | None:
        value = self._safe_scalar("SELECT MAX(as_of_date) FROM strategy_signal")
        return self._coerce_to_date(value)

    def signal_latest_effective_date(self) -> date | None:
        value = self._safe_scalar("SELECT MAX(effective_date) FROM strategy_signal")
        return self._coerce_to_date(value)

    def strategy_definition_count(self) -> int | None:
        value = self._safe_scalar("SELECT COUNT(*) FROM strategy_definition")
        return int(value) if value is not None else None

    def strategy_version_count(self) -> int | None:
        value = self._safe_scalar("SELECT COUNT(*) FROM strategy_version")
        return int(value) if value is not None else None

    def parameter_schema_count(self) -> int | None:
        value = self._safe_scalar("SELECT COUNT(*) FROM strategy_parameter_schema")
        return int(value) if value is not None else None

    def current_true_rows(self) -> list[dict[str, Any]]:
        sql = """
        SELECT
            sd.strategy_code,
            COUNT(*) AS current_true_count
        FROM strategy_version sv
        JOIN strategy_definition sd
          ON sd.id = sv.strategy_definition_id
        WHERE sv.is_current = TRUE
        GROUP BY sd.strategy_code
        ORDER BY sd.strategy_code
        """
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(text(sql)).mappings().all()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def _safe_scalar(self, sql: str, params: dict[str, Any] | None = None) -> Any | None:
        try:
            with self.engine.connect() as conn:
                return conn.execute(text(sql), params or {}).scalar()
        except Exception:
            return None

    @staticmethod
    def _coerce_to_date(value: Any | None) -> date | None:
        if value is None:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            return datetime.strptime(value, "%Y-%m-%d").date()
        return None


def _build_m4_env(target_date: date) -> dict[str, str]:
    target = target_date.isoformat()
    # 这里统一导出一组不冲突的日期变量。
    # 如果下游 M4 脚本当前只消费其中一个，也能直接生效；
    # 若当前下游完全不读这些变量，则下一步只需补 child script，不用重写编排层。
    return {
        "M4_AS_OF_DATE": target,
        "M4_SIGNAL_AS_OF_DATE": target,
        "M4_TRADE_DATE": target,
        "M4_EFFECTIVE_DATE": target,
    }



def _load_strategy_release_payload(project_root: Path) -> tuple[dict[str, Any], Path | None]:
    candidates: list[Path] = []
    env_path = os.getenv("STRATEGY_RELEASE_LOCAL_FILE", "").strip()
    if env_path:
        candidates.append(Path(env_path))
    candidates.extend([
        project_root / "strategy_release_cache" / "active" / "strategy_release.json",
        project_root / "strategy_release_cache" / "inbox" / "strategy_release.json",
        Path("/app/strategy_release_cache/active/strategy_release.json"),
        Path("/app/strategy_release_cache/inbox/strategy_release.json"),
    ])

    for path in candidates:
        try:
            if path.exists():
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
                return payload, path
        except Exception as exc:
            print(f"[M4][release] failed to load {path}: {type(exc).__name__}: {exc}")

    return {}, None


def _release_version_code(payload: dict[str, Any]) -> str:
    return str(payload.get("strategy_version_code") or payload.get("version_code") or "").strip()


def _release_params(payload: dict[str, Any]) -> dict[str, Any]:
    params = payload.get("params")
    return params if isinstance(params, dict) else {}


def _truthy(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _release_value(payload: dict[str, Any], key: str, default: Any = None) -> Any:
    params = _release_params(payload)
    if key in payload:
        return payload.get(key)
    if key in params:
        return params.get(key)
    contract = payload.get("r63_fast_deploy_contract")
    if isinstance(contract, dict) and key in contract:
        return contract.get(key)
    return default


def _build_target_chain_args(
    *,
    project_root: Path,
    release_payload: dict[str, Any],
    report_date: date,
    effective_date: date,
) -> list[str]:
    strategy_code = str(_release_value(release_payload, "strategy_code", TARGET_STRATEGY_CODE)).strip() or TARGET_STRATEGY_CODE
    strategy_version_code = _release_version_code(release_payload) or TARGET_VERSION_CODE
    params = _release_params(release_payload)
    output_dir = project_root / "artifacts" / "m4" / "strategy_signal_db_write_contract" / "r63_release_route"
    output_json = output_dir / f"target_m4_signal_light_release_route_{report_date.isoformat()}_{effective_date.isoformat()}.json"

    args = [
        "--project-root",
        str(project_root),
        "--report-date",
        report_date.isoformat(),
        "--effective-date",
        effective_date.isoformat(),
        "--strategy-code",
        strategy_code,
        "--strategy-version-code",
        strategy_version_code,
        "--output-dir",
        str(output_dir),
        "--output-json",
        str(output_json),
    ]

    if _truthy(params.get("run_full_target_preview_chain"), True):
        args.append("--run-full-target-preview-chain")
    elif _truthy(params.get("build_preview"), True):
        args.append("--build-preview")

    if _truthy(params.get("write_db"), True):
        args.append("--write-db")
        write_confirmation = str(
            params.get("m4_target_signal_write_confirmation")
            or params.get("write_confirmation")
            or os.getenv("M4_TARGET_SIGNAL_WRITE_CONFIRMATION", "")
            or "PREVIEW_SCOPE_ONLY"
        )
        args.extend(["--write-confirmation", write_confirmation])

    if _truthy(params.get("allow_existing_same_version_date"), True):
        args.append("--allow-existing-same-version-date")

    max_rows = params.get("max_rows")
    if max_rows not in (None, ""):
        args.extend(["--max-rows", str(max_rows)])

    return args


def _resolve_release_selected_chain(
    *,
    project_root: Path,
    release_payload: dict[str, Any],
    release_path: Path | None,
    report_date: date,
    effective_date: date,
) -> tuple[M4Chain, list[str] | None, dict[str, Any]]:
    strategy_code = str(release_payload.get("strategy_code") or "").strip()
    version_code = _release_version_code(release_payload)
    summary = {
        "release_path": str(release_path) if release_path else None,
        "strategy_code": strategy_code or None,
        "version_code": version_code or None,
        "report_date": report_date.isoformat(),
        "effective_date": effective_date.isoformat(),
        "route": "rule_strategy_chain",
    }

    if strategy_code == TARGET_STRATEGY_CODE and version_code == TARGET_VERSION_CODE:
        summary["route"] = "regime_sector_industry_target_signal_light"
        return (
            M4_TARGET_CHAIN,
            _build_target_chain_args(
                project_root=project_root,
                release_payload=release_payload,
                report_date=report_date,
                effective_date=effective_date,
            ),
            summary,
        )

    return M4_MAIN_CHAIN, None, summary


def run_m4_strategy_refresh_chain(target_date: date | None = None) -> int:
    inspector = DatabaseInspector(str(settings.postgres_v2_url))
    try:
        print("[M4] Strategy refresh chain started.")
        print(f"[M4] Using database URL: {settings.postgres_v2_url}")

        latest_trading_day = target_date or inspector.latest_trading_day()
        if latest_trading_day is None:
            print("[M4] Failed to resolve latest_trading_day. Please make sure M2 is ready.")
            return 2

        print(f"[M4] latest_trading_day = {latest_trading_day.isoformat()}")

        effective_trading_day = inspector.next_trading_day(latest_trading_day) or latest_trading_day

        env_overrides = _build_m4_env(latest_trading_day)
        env_overrides["M4_EFFECTIVE_DATE"] = effective_trading_day.isoformat()
        print("[M4] Effective env overrides:")
        for k, v in env_overrides.items():
            print(f"  - {k}={v}")

        project_root = _project_root()
        release_payload, release_path = _load_strategy_release_payload(project_root)
        selected_chain, selected_args, release_route_summary = _resolve_release_selected_chain(
            project_root=project_root,
            release_payload=release_payload,
            release_path=release_path,
            report_date=latest_trading_day,
            effective_date=effective_trading_day,
        )
        print("[M4] Release route summary:")
        print(json.dumps(release_route_summary, ensure_ascii=False, indent=2))

        print(f"\n[M4][{selected_chain.name}] starting: {selected_chain.module_name}")
        rc = _run_module(selected_chain.module_name, extra_env=env_overrides, args=selected_args)
        if rc != 0:
            print(f"[M4][{selected_chain.name}] failed (exit_code={rc})")
            print("[M4] Chain stopped. Fix M4 before moving to M5.")
            return rc
        print(f"[M4][{selected_chain.name}] succeeded.")

        strategy_definition_count = inspector.strategy_definition_count()
        strategy_version_count = inspector.strategy_version_count()
        parameter_schema_count = inspector.parameter_schema_count()
        signal_total_rows = inspector.signal_total_rows()
        signal_latest_as_of_date = inspector.signal_latest_as_of_date()
        signal_latest_effective_date = inspector.signal_latest_effective_date()
        current_true_rows = inspector.current_true_rows()

        print("\n[M4] Lightweight post-run observations:")
        print(f"  - strategy_definition_count: {strategy_definition_count if strategy_definition_count is not None else '-'}")
        print(f"  - strategy_version_count: {strategy_version_count if strategy_version_count is not None else '-'}")
        print(f"  - parameter_schema_count: {parameter_schema_count if parameter_schema_count is not None else '-'}")
        print(f"  - signal_total_rows: {signal_total_rows if signal_total_rows is not None else '-'}")
        print(f"  - signal_latest_as_of_date: {signal_latest_as_of_date.isoformat() if signal_latest_as_of_date else '-'}")
        print(f"  - signal_latest_effective_date: {signal_latest_effective_date.isoformat() if signal_latest_effective_date else '-'}")

        if current_true_rows:
            print("  - current_true_rows:")
            for row in current_true_rows:
                print(f"      * {row['strategy_code']}: {row['current_true_count']}")
        else:
            print("  - current_true_rows: -")

        print("\n[M4] Strategy refresh chain completed successfully.")
        print("[M4] Next action: run sql/m4_1_acceptance.sql before moving to M5.")
        return 0
    finally:
        inspector.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the M4 strategy refresh chain. "
            "By default, resolve latest_trading_day at runtime and export M4 date env overrides."
        )
    )
    parser.add_argument(
        "--target-date",
        required=False,
        help="Optional manual override target date in YYYY-MM-DD. Default: latest_trading_day from DB.",
    )
    args = parser.parse_args(argv)

    target_date = datetime.strptime(args.target_date, "%Y-%m-%d").date() if args.target_date else None
    return run_m4_strategy_refresh_chain(target_date=target_date)


if __name__ == "__main__":
    raise SystemExit(main())

# R64_RESEARCH_REGISTRY_DISPATCH_BEGIN
# Research-only bridge for strategy_code=multi_layer_regime_rotation_v2.
# This block is intentionally inert unless explicitly imported/called.
def get_r64_research_strategy_dispatch_entry():
    """Return the R64 research-only dispatch entry without touching production signal paths."""
    from stock_quant_v2.strategy_domain.services.multi_layer_regime_rotation_v2_registry_dispatch import (
        get_r64_research_strategy_registry_entry,
    )

    entry = get_r64_research_strategy_registry_entry()
    if entry.get("formal_signal_allowed") or entry.get("trading_allowed"):
        raise RuntimeError("R64 research dispatch entry must not enable formal signals or trading.")
    if not entry.get("block_signal_generation") or not entry.get("block_trading"):
        raise RuntimeError("R64 research dispatch entry guardrails must stay blocked.")
    return entry
# R64_RESEARCH_REGISTRY_DISPATCH_END
