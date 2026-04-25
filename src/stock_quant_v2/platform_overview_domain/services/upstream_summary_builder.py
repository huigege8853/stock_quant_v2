from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

from sqlalchemy import create_engine, text


class UpstreamSummaryBuilder:
    def __init__(self, repo_root: Path, db_url: str | None = None) -> None:
        self.repo_root = repo_root
        self.db_url = db_url or self._resolve_database_url()
        self.engine = create_engine(self.db_url)

    def close(self) -> None:
        self.engine.dispose()

    def build_all(self, report_date: str) -> dict[str, dict[str, Path]]:
        try:
            m3 = self.build_m3_summary(report_date=report_date)
            m4 = self.build_m4_summary(report_date=report_date)
            return {
                "m3": self._export_m3_summary(m3),
                "m4": self._export_m4_summary(m4),
            }
        finally:
            self.close()

    def build_m3_summary(self, report_date: str) -> dict[str, Any]:
        definition_counts = {
            "meta_indicator_definition": self._scalar("SELECT COUNT(*) FROM meta_indicator_definition"),
            "meta_factor_definition": self._scalar("SELECT COUNT(*) FROM meta_factor_definition"),
            "meta_feature_definition": self._scalar("SELECT COUNT(*) FROM meta_feature_definition"),
            "meta_feature_set_definition": self._scalar("SELECT COUNT(*) FROM meta_feature_set_definition"),
            "meta_label_definition": self._scalar("SELECT COUNT(*) FROM meta_label_definition"),
        }

        snapshot_counts = {
            "indicator_rows": self._safe_count("analytics_instrument_indicator_snapshot"),
            "factor_rows": self._safe_count("analytics_factor_snapshot"),
            "feature_rows": self._safe_count("analytics_feature_snapshot"),
            "label_rows": self._safe_count("analytics_label_snapshot"),
            "daily_bar_rows": self._safe_count("core_daily_bar"),
            "adjust_factor_rows": self._safe_count("core_adjust_factor"),
        }

        readiness_metrics = self._row(
            """
            WITH base AS (
                SELECT COUNT(*) AS total_bar_rows
                FROM core_daily_bar
            ),
            ff AS (
                SELECT
                    COUNT(*) FILTER (WHERE af.instrument_id IS NOT NULL) AS matched_forward_factor_rows,
                    COUNT(*) FILTER (WHERE af.instrument_id IS NULL) AS missing_forward_factor_rows
                FROM core_daily_bar db
                LEFT JOIN core_adjust_factor af
                  ON af.instrument_id = db.instrument_id
                 AND af.trade_date = db.trade_date
            ),
            indicator_check AS (
                SELECT
                    COUNT(*) FILTER (WHERE indicator_code = 'adj_close' AND numeric_value IS NOT NULL) AS adj_close_ready
                FROM analytics_instrument_indicator_snapshot
            ),
            factor_check AS (
                SELECT
                    COUNT(*) FILTER (WHERE factor_code = 'ret_20d' AND numeric_value IS NOT NULL) AS ret_20d_ready
                FROM analytics_factor_snapshot
            )
            SELECT
                base.total_bar_rows,
                ff.matched_forward_factor_rows,
                ff.missing_forward_factor_rows,
                indicator_check.adj_close_ready,
                factor_check.ret_20d_ready
            FROM base, ff, indicator_check, factor_check
            """
        ) or {}

        latest_success_run = self._row(
            """
            SELECT id, run_type, run_name, status, requested_at, started_at, ended_at, error_message
            FROM ops_run
            WHERE run_name LIKE 'bootstrap_m3_%'
            ORDER BY requested_at DESC
            LIMIT 1
            """
        )

        recent_runs = self._rows(
            """
            SELECT id, run_type, run_name, status, requested_at, started_at, ended_at, error_message
            FROM ops_run
            WHERE run_name LIKE 'bootstrap_m3_%'
            ORDER BY requested_at DESC
            LIMIT 10
            """
        )

        ready_definition_count = sum(int(v or 0) for v in definition_counts.values())
        total_bar_rows = int(readiness_metrics.get("total_bar_rows") or 0)
        matched_forward_factor_rows = int(readiness_metrics.get("matched_forward_factor_rows") or 0)
        missing_forward_factor_rows = int(readiness_metrics.get("missing_forward_factor_rows") or 0)
        adj_close_ready = int(readiness_metrics.get("adj_close_ready") or 0)
        ret_20d_ready = int(readiness_metrics.get("ret_20d_ready") or 0)

        has_recent_success = bool(latest_success_run and latest_success_run.get("status") == "SUCCESS")
        readiness_blocked = (
            total_bar_rows > 0
            and (
                matched_forward_factor_rows == 0
                or missing_forward_factor_rows > 0
                or adj_close_ready == 0
                or ret_20d_ready == 0
            )
        )

        if ready_definition_count > 0 and has_recent_success and readiness_blocked:
            status = "WARN"
            human_summary = (
                "M3 定义层已落库，且最近 bootstrap_m3_* runs 存在成功记录，"
                "但当前 readiness 事实仍明显未就绪："
                f"total_bar_rows={total_bar_rows}，"
                f"matched_forward_factor_rows={matched_forward_factor_rows}，"
                f"missing_forward_factor_rows={missing_forward_factor_rows}，"
                f"adj_close_ready={adj_close_ready}，"
                f"ret_20d_ready={ret_20d_ready}。"
                "当前应解释为 definitions ready、runtime/readiness blocked。"
            )
        elif ready_definition_count > 0 and has_recent_success and total_bar_rows == 0:
            status = "WARN"
            human_summary = (
                "M3 定义层已落库，且最近 bootstrap_m3_* runs 存在成功记录，"
                "但当前底层 bar 数据不足，尚不能支持稳定的指标/因子/特征/标签 readiness。"
            )
        elif ready_definition_count > 0 and (adj_close_ready > 0 or ret_20d_ready > 0):
            status = "OK"
            human_summary = (
                "M3 定义层与关键 readiness 事实已可识别，"
                "06_指标/因子/特征/标签状态 可不再仅依赖 docs-only。"
            )
        elif ready_definition_count > 0:
            status = "INFO"
            human_summary = (
                "M3 当前已识别到定义层，但 readiness 事实仍偏弱，"
                "尚未形成稳定的运行态输入。"
            )
        else:
            status = "INFO"
            human_summary = (
                "M3 当前仍以基础定义或历史运行痕迹为主，"
                "尚未形成稳定的 readiness 事实输入。"
            )

        latest_run_id = latest_success_run["id"] if latest_success_run else None

        return {
            "summary_type": "m3_readiness",
            "status": status,
            "report_date": report_date,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "latest_run_id": latest_run_id,
            "latest_success_run": latest_success_run,
            "definition_counts": definition_counts,
            "snapshot_counts": snapshot_counts,
            "readiness_metrics": readiness_metrics,
            "recent_runs": recent_runs,
            "human_summary": human_summary,
        }

    def build_m4_summary(self, report_date: str) -> dict[str, Any]:
        strategies = self._rows(
            """
            SELECT
                id,
                strategy_code,
                strategy_name,
                strategy_type,
                engine_type,
                lifecycle_status
            FROM strategy_definition
            ORDER BY id
            """
        )

        versions = self._rows(
            """
            SELECT
                sv.id,
                sd.strategy_code,
                sv.version_code,
                sv.version_no,
                sv.is_current,
                sv.lifecycle_status,
                sv.output_contract_version,
                sv.implementation_ref
            FROM strategy_version sv
            JOIN strategy_definition sd
              ON sd.id = sv.strategy_definition_id
            ORDER BY sv.id
            """
        )

        schemas = self._rows(
            """
            SELECT
                sps.id,
                sps.strategy_version_id,
                sps.schema_version_code,
                sps.parameter_schema_json,
                sps.example_payload_json
            FROM strategy_parameter_schema sps
            ORDER BY sps.id
            """
        )

        schema_count = len(schemas)
        signal_total_rows = self._safe_count("strategy_signal")
        signal_latest_as_of_date = self._scalar("SELECT MAX(as_of_date) FROM strategy_signal")
        signal_latest_effective_date = self._scalar("SELECT MAX(effective_date) FROM strategy_signal")

        current_true_rows = self._rows(
            """
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
        )

        if strategies and versions and int(schema_count or 0) > 0 and int(signal_total_rows or 0) == 0:
            status = "WARN"
            human_summary = (
                "M4 策略定义、当前版本与参数 schema 已 ready，"
                "但 strategy_signal 运行事实当前为 0，"
                "07_策略与信号状态 应解释为 metadata ready、signal facts absent。"
            )
        elif strategies and versions and int(signal_total_rows or 0) > 0:
            status = "OK"
            human_summary = (
                "M4 策略定义、版本与 signal 运行事实均已识别，"
                "07_策略与信号状态 可基于实际 signal facts 解释。"
            )
        else:
            status = "INFO"
            human_summary = (
                "M4 当前只识别到部分策略元数据，"
                "尚未形成稳定的策略/信号状态解释输入。"
            )

        return {
            "summary_type": "m4_strategy_signal",
            "status": status,
            "report_date": report_date,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "latest_run_id": None,
            "strategies": strategies,
            "versions": versions,
            "schemas": schemas[:5],
            "schema_count": schema_count,
            "signal_total_rows": signal_total_rows,
            "signal_latest_as_of_date": str(signal_latest_as_of_date) if signal_latest_as_of_date else None,
            "signal_latest_effective_date": str(signal_latest_effective_date) if signal_latest_effective_date else None,
            "current_true_rows": current_true_rows,
            "human_summary": human_summary,
        }

    def _export_m3_summary(self, payload: dict[str, Any]) -> dict[str, Path]:
        output_dir = self.repo_root / "artifacts" / "m3" / "m9_bridge"
        output_dir.mkdir(parents=True, exist_ok=True)

        latest_run_id = payload.get("latest_run_id")
        run_part = f"_r{latest_run_id}" if latest_run_id is not None else ""
        prefix = f"m3_m9_bridge_summary_p1{run_part}_{payload['report_date']}"

        md_path = output_dir / f"{prefix}.md"
        json_path = output_dir / f"{prefix}.json"

        md_path.write_text(self._render_m3_markdown(payload), encoding="utf-8")
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

        return {"markdown": md_path, "json": json_path}

    def _export_m4_summary(self, payload: dict[str, Any]) -> dict[str, Path]:
        output_dir = self.repo_root / "artifacts" / "m4" / "m9_bridge"
        output_dir.mkdir(parents=True, exist_ok=True)

        prefix = f"m4_m9_bridge_summary_p1_{payload['report_date']}"

        md_path = output_dir / f"{prefix}.md"
        json_path = output_dir / f"{prefix}.json"

        md_path.write_text(self._render_m4_markdown(payload), encoding="utf-8")
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

        return {"markdown": md_path, "json": json_path}

    @staticmethod
    def _render_m3_markdown(payload: dict[str, Any]) -> str:
        lines = [
            "# M3 → M9 Bridge Summary",
            "",
            f"- Report Date: {payload['report_date']}",
            f"- Status: {payload['status']}",
            f"- Latest Run ID: {payload.get('latest_run_id') or '-'}",
            "",
            "## Human Summary",
            "",
            payload["human_summary"],
            "",
            "## Definition Counts",
            "",
        ]
        for k, v in payload["definition_counts"].items():
            lines.append(f"- {k}: {v}")

        lines.extend(["", "## Snapshot Counts", ""])
        for k, v in payload["snapshot_counts"].items():
            lines.append(f"- {k}: {v}")

        lines.extend(["", "## Readiness Metrics", ""])
        for k, v in payload["readiness_metrics"].items():
            lines.append(f"- {k}: {v}")

        lines.extend(["", "## Latest Successful Run", ""])
        if payload["latest_success_run"]:
            for k, v in payload["latest_success_run"].items():
                lines.append(f"- {k}: {v}")
        else:
            lines.append("- none")

        return "\n".join(lines)

    @staticmethod
    def _render_m4_markdown(payload: dict[str, Any]) -> str:
        lines = [
            "# M4 → M9 Bridge Summary",
            "",
            f"- Report Date: {payload['report_date']}",
            f"- Status: {payload['status']}",
            f"- Signal Total Rows: {payload['signal_total_rows']}",
            f"- Signal Latest As Of Date: {payload['signal_latest_as_of_date'] or '-'}",
            "",
            "## Human Summary",
            "",
            payload["human_summary"],
            "",
            "## Strategies",
            "",
        ]
        if payload["strategies"]:
            for row in payload["strategies"]:
                lines.append(
                    f"- {row['strategy_code']} | {row['strategy_name']} | {row['strategy_type']} | {row['engine_type']} | {row['lifecycle_status']}"
                )
        else:
            lines.append("- none")

        lines.extend(["", "## Versions", ""])
        if payload["versions"]:
            for row in payload["versions"]:
                lines.append(
                    f"- {row['strategy_code']} | {row['version_code']} | version_no={row['version_no']} | is_current={row['is_current']} | {row['lifecycle_status']}"
                )
        else:
            lines.append("- none")

        lines.extend(["", "## Current True Rows", ""])
        if payload["current_true_rows"]:
            for row in payload["current_true_rows"]:
                lines.append(f"- {row['strategy_code']}: {row['current_true_count']}")
        else:
            lines.append("- none")

        return "\n".join(lines)

    def _resolve_database_url(self) -> str:
        self._load_env()
        candidates = [
            "V2_SQLALCHEMY_URL",
            "DATABASE_URL",
            "SQLALCHEMY_DATABASE_URI",
            "POSTGRES_DSN",
            "DB_URL",
        ]
        for key in candidates:
            value = self._clean_env_value(os.getenv(key))
            if value:
                return value

        host = self._clean_env_value(os.getenv("POSTGRES_HOST")) or "localhost"
        port = self._clean_env_value(os.getenv("POSTGRES_PORT")) or "5432"
        user = self._clean_env_value(os.getenv("POSTGRES_USER")) or "postgres"
        password = self._clean_env_value(os.getenv("POSTGRES_PASSWORD")) or "postgres"
        db = self._clean_env_value(os.getenv("POSTGRES_DB")) or "stock_quant_v2"

        return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"

    def _load_env(self) -> None:
        env_file = self.repo_root / ".env"
        if load_dotenv is not None and env_file.exists():
            load_dotenv(env_file, override=False)

    @staticmethod
    def _clean_env_value(value: str | None) -> str | None:
        if not value:
            return None
        cleaned = value.strip().splitlines()[0].strip()
        if " #" in cleaned:
            cleaned = cleaned.split(" #", 1)[0].strip()
        if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
            cleaned = cleaned[1:-1].strip()
        return cleaned or None

    def _scalar(self, sql: str) -> Any:
        with self.engine.connect() as conn:
            return conn.execute(text(sql)).scalar()

    def _row(self, sql: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(text(sql)).mappings().first()
            return dict(row) if row else None

    def _rows(self, sql: str) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql)).mappings().all()
            return [dict(r) for r in rows]

    def _safe_count(self, table_name: str) -> int | None:
        try:
            return int(self._scalar(f"SELECT COUNT(*) FROM {table_name}") or 0)
        except Exception:
            return None