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
            m5 = self.build_m5_summary(report_date=report_date)
            return {
                "m3": self._export_m3_summary(m3),
                "m4": self._export_m4_summary(m4),
                "m5": self._export_m5_summary(m5),
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

        readiness_metrics = self._build_m3_readiness_metrics()

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

    def build_m5_summary(self, report_date: str) -> dict[str, Any]:
        """Build M5 backtest execution facts for M9.1.1 section 08.

        This is a read-side bridge. It does not create or modify any backtest
        data. The goal is to let M9 distinguish M5.10 real backtrader execution
        from old placeholder / skeleton rows.
        """

        latest_result = self._row(
            """
            SELECT
                id,
                run_id,
                backtest_request_id,
                result_status,
                start_date,
                end_date,
                trading_days,
                initial_cash,
                final_equity,
                total_return,
                annual_return,
                max_drawdown,
                sharpe_ratio,
                volatility,
                order_count,
                trade_count,
                result_summary
            FROM research_backtest_result
            WHERE result_status IN ('SUCCESS', 'SUCCESS_WITH_WARN')
            ORDER BY id DESC
            LIMIT 1
            """
        )

        if latest_result is None:
            latest_result = self._row(
                """
                SELECT
                    id,
                    run_id,
                    backtest_request_id,
                    result_status,
                    start_date,
                    end_date,
                    trading_days,
                    initial_cash,
                    final_equity,
                    total_return,
                    annual_return,
                    max_drawdown,
                    sharpe_ratio,
                    volatility,
                    order_count,
                    trade_count,
                    result_summary
                FROM research_backtest_result
                ORDER BY id DESC
                LIMIT 1
                """
            )

        if latest_result is None:
            return {
                "summary_type": "m5_backtest_execution",
                "status": "WARN",
                "report_date": report_date,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "latest_run_id": None,
                "latest_result": None,
                "artifact_codes": [],
                "metric_count": 0,
                "series_count": 0,
                "checks": {
                    "result_exists": False,
                    "real_execution": False,
                    "trade_log_artifact": False,
                    "equity_curve_artifact": False,
                    "metrics_artifact": False,
                    "series_rows": False,
                    "metric_rows": False,
                },
                "warnings": [
                    {
                        "code": "M5_BACKTEST_RESULT_MISSING",
                        "severity": "WARN",
                        "message": "未识别到 research_backtest_result，M9 不应声称 M5 已完成真实回测执行。",
                    }
                ],
                "human_summary": "M5 当前未识别到可用 backtest result；08_回测与研究结果 仍应视为待补源。",
            }

        run_id = int(latest_result["run_id"])
        result_summary = self._coerce_json_dict(latest_result.get("result_summary"))
        execution_mode = result_summary.get("execution_mode")
        quality_warning_codes = result_summary.get("quality_warning_codes") or []
        if not isinstance(quality_warning_codes, list):
            quality_warning_codes = [str(quality_warning_codes)]

        artifacts = self._rows(
            f"""
            SELECT
                artifact_code,
                artifact_type,
                uri,
                file_size_bytes
            FROM ops_run_artifact
            WHERE run_id = {run_id}
            ORDER BY artifact_code
            """
        )
        artifact_codes = sorted(str(row.get("artifact_code")) for row in artifacts if row.get("artifact_code"))

        metric_rows = self._rows(
            f"""
            SELECT
                metric_code,
                metric_value_numeric,
                metric_value_text
            FROM ops_run_metric_snapshot
            WHERE run_id = {run_id}
              AND metric_namespace = 'backtest'
            ORDER BY sequence_no
            """
        )
        metric_codes = sorted(str(row.get("metric_code")) for row in metric_rows if row.get("metric_code"))

        series_rows = self._rows(
            f"""
            SELECT
                series_code,
                COUNT(*) AS row_count,
                MIN(trade_date) AS min_trade_date,
                MAX(trade_date) AS max_trade_date
            FROM ops_run_series_snapshot
            WHERE run_id = {run_id}
              AND series_namespace = 'backtest'
            GROUP BY series_code
            ORDER BY series_code
            """
        )
        series_codes = sorted(str(row.get("series_code")) for row in series_rows if row.get("series_code"))

        required_artifacts = {
            "backtest_metrics_json",
            "backtest_equity_curve_csv",
            "backtest_trade_log_csv",
        }
        required_metrics = {
            "final_equity",
            "total_return",
            "annual_return",
            "max_drawdown",
            "volatility",
            "trading_days",
        }
        required_series = {
            "portfolio_equity",
            "cash",
            "gross_exposure",
            "holding_count",
        }

        checks = {
            "result_exists": True,
            "result_status_success": latest_result.get("result_status") in {"SUCCESS", "SUCCESS_WITH_WARN"},
            "real_execution": bool(result_summary.get("execution_enabled")) and result_summary.get("stage") == "M5.10_BACKTRADER_REAL_EXECUTION_P1",
            "trade_log_artifact": "backtest_trade_log_csv" in artifact_codes,
            "equity_curve_artifact": "backtest_equity_curve_csv" in artifact_codes,
            "metrics_artifact": "backtest_metrics_json" in artifact_codes,
            "artifact_set_complete": required_artifacts.issubset(set(artifact_codes)),
            "series_rows": required_series.issubset(set(series_codes)),
            "metric_rows": required_metrics.issubset(set(metric_codes)),
            "trade_count_positive": int(latest_result.get("trade_count") or 0) > 0,
            "final_equity_present": latest_result.get("final_equity") is not None,
        }

        warnings: list[dict[str, Any]] = []
        if execution_mode == "SNAPSHOT_STATIC_BASKET_P1" or "SNAPSHOT_STATIC_BASKET_P1" in quality_warning_codes:
            warnings.append(
                {
                    "code": "SNAPSHOT_STATIC_BASKET_P1",
                    "severity": "WARN",
                    "message": (
                        "M5.10 P1 使用 latest selected signal basket 作为 static basket；"
                        "这是当前可接受告警，历史信号逐日重放仍为 M5.11 backlog。"
                    ),
                }
            )

        blocking_keys = [
            "result_status_success",
            "real_execution",
            "trade_log_artifact",
            "equity_curve_artifact",
            "metrics_artifact",
            "series_rows",
            "metric_rows",
            "trade_count_positive",
            "final_equity_present",
        ]
        blocking_ok = all(bool(checks.get(key)) for key in blocking_keys)

        if not blocking_ok:
            status = "WARN"
            human_summary = (
                f"M5 已识别到 backtest result run_id={run_id}，"
                f"但真实执行事实仍不完整：checks={checks}。"
                "08_回测与研究结果 不应视为稳定通过。"
            )
        elif warnings:
            status = "PASS_WITH_WARN"
            human_summary = (
                f"M5 已从 placeholder / skeleton 升级为真实 backtrader 执行："
                f"run_id={run_id}，backtest_request_id={latest_result.get('backtest_request_id')}，"
                f"result_status={latest_result.get('result_status')}，"
                f"execution_mode={execution_mode}，"
                f"final_equity={latest_result.get('final_equity')}，"
                f"total_return={latest_result.get('total_return')}，"
                f"trade_count={latest_result.get('trade_count')}，"
                f"trading_days={latest_result.get('trading_days')}。"
                "当前唯一核心限制是 SNAPSHOT_STATIC_BASKET_P1；这是真实执行结果，但不是历史信号逐日重放。"
            )
        else:
            status = "OK"
            human_summary = (
                f"M5 已识别到稳定真实 backtrader 回测执行："
                f"run_id={run_id}，result_status={latest_result.get('result_status')}，"
                f"final_equity={latest_result.get('final_equity')}，"
                f"total_return={latest_result.get('total_return')}。"
            )

        latest_result_out = dict(latest_result)
        latest_result_out["result_summary"] = result_summary

        return {
            "summary_type": "m5_backtest_execution",
            "status": status,
            "report_date": report_date,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "latest_run_id": run_id,
            "latest_result_id": latest_result.get("id"),
            "backtest_request_id": latest_result.get("backtest_request_id"),
            "execution_mode": execution_mode,
            "fallback_reason": result_summary.get("fallback_reason"),
            "quality_warning_codes": quality_warning_codes,
            "latest_result": latest_result_out,
            "artifact_codes": artifact_codes,
            "artifacts": artifacts,
            "metric_count": len(metric_rows),
            "metric_codes": metric_codes,
            "series_count": sum(int(row.get("row_count") or 0) for row in series_rows),
            "series_codes": series_codes,
            "series_rows": series_rows,
            "checks": checks,
            "warnings": warnings,
            "m5_11_backlog": "Historical Signal Replay Backtest",
            "human_summary": human_summary,
        }


    def _build_m3_readiness_metrics(self) -> dict[str, Any]:
        """Build M3 readiness facts without assuming a fixed snapshot value column.

        M3 snapshot table schemas have varied across project iterations. Some
        environments use indicator_value / factor_value instead of numeric_value.
        This helper introspects the live schema and falls back to row presence
        so upstream summary generation remains read-only and compatible.
        """

        total_bar_rows = int(self._safe_count("core_daily_bar") or 0)

        matched_forward_factor_rows = 0
        missing_forward_factor_rows = 0
        adjust_factor_join_status = "not_checked"
        if self._has_table("core_daily_bar") and self._has_table("core_adjust_factor"):
            db_columns = self._table_columns("core_daily_bar")
            af_columns = self._table_columns("core_adjust_factor")
            if {"instrument_id", "trade_date"}.issubset(db_columns) and {"instrument_id", "trade_date"}.issubset(af_columns):
                try:
                    row = self._row(
                        """
                        SELECT
                            COUNT(*) FILTER (WHERE af.instrument_id IS NOT NULL) AS matched_forward_factor_rows,
                            COUNT(*) FILTER (WHERE af.instrument_id IS NULL) AS missing_forward_factor_rows
                        FROM core_daily_bar db
                        LEFT JOIN core_adjust_factor af
                          ON af.instrument_id = db.instrument_id
                         AND af.trade_date = db.trade_date
                        """
                    ) or {}
                    matched_forward_factor_rows = int(row.get("matched_forward_factor_rows") or 0)
                    missing_forward_factor_rows = int(row.get("missing_forward_factor_rows") or 0)
                    adjust_factor_join_status = "checked"
                except Exception as exc:
                    adjust_factor_join_status = f"failed: {type(exc).__name__}"
            else:
                adjust_factor_join_status = "skipped_missing_join_columns"
        else:
            adjust_factor_join_status = "skipped_missing_table"

        indicator_value_column = self._pick_existing_column(
            "analytics_instrument_indicator_snapshot",
            [
                "numeric_value",
                "indicator_value",
                "indicator_value_numeric",
                "value_numeric",
                "value",
                "metric_value",
            ],
        )
        factor_value_column = self._pick_existing_column(
            "analytics_factor_snapshot",
            [
                "numeric_value",
                "factor_value",
                "factor_value_numeric",
                "score_value",
                "value_numeric",
                "value",
            ],
        )

        adj_close_ready = self._count_code_rows(
            table_name="analytics_instrument_indicator_snapshot",
            code_column="indicator_code",
            code_value="adj_close",
            value_column=indicator_value_column,
        )
        ret_20d_ready = self._count_code_rows(
            table_name="analytics_factor_snapshot",
            code_column="factor_code",
            code_value="ret_20d",
            value_column=factor_value_column,
        )

        return {
            "total_bar_rows": total_bar_rows,
            "matched_forward_factor_rows": matched_forward_factor_rows,
            "missing_forward_factor_rows": missing_forward_factor_rows,
            "adj_close_ready": adj_close_ready,
            "ret_20d_ready": ret_20d_ready,
            "indicator_value_column": indicator_value_column,
            "factor_value_column": factor_value_column,
            "adjust_factor_join_status": adjust_factor_join_status,
        }

    def _count_code_rows(
        self,
        *,
        table_name: str,
        code_column: str,
        code_value: str,
        value_column: str | None = None,
    ) -> int:
        if not self._has_table(table_name):
            return 0
        columns = self._table_columns(table_name)
        if code_column not in columns:
            return 0

        table_sql = self._quote_ident(table_name)
        code_sql = self._quote_ident(code_column)
        if value_column and value_column in columns:
            value_sql = self._quote_ident(value_column)
            sql = f"SELECT COUNT(*) FROM {table_sql} WHERE {code_sql} = :code_value AND {value_sql} IS NOT NULL"
        else:
            # Fall back to row presence when the live schema does not expose a
            # recognized numeric value column. This still tells M9 that the
            # snapshot fact exists, while preserving schema compatibility.
            sql = f"SELECT COUNT(*) FROM {table_sql} WHERE {code_sql} = :code_value"

        try:
            with self.engine.connect() as conn:
                return int(conn.execute(text(sql), {"code_value": code_value}).scalar() or 0)
        except Exception:
            return 0

    def _pick_existing_column(self, table_name: str, candidate_columns: list[str]) -> str | None:
        columns = self._table_columns(table_name)
        for column in candidate_columns:
            if column in columns:
                return column
        return None

    def _has_table(self, table_name: str) -> bool:
        return bool(
            self._scalar_safe(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = :table_name
                )
                """,
                {"table_name": table_name},
            )
        )

    def _table_columns(self, table_name: str) -> set[str]:
        rows = self._rows_safe(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name
            """,
            {"table_name": table_name},
        )
        return {str(row["column_name"]) for row in rows if row.get("column_name")}

    @staticmethod
    def _quote_ident(identifier: str) -> str:
        if not identifier.replace("_", "").isalnum():
            raise ValueError(f"unsafe SQL identifier: {identifier!r}")
        return f'"{identifier}"'

    def _scalar_safe(self, sql: str, params: dict[str, Any] | None = None) -> Any:
        try:
            with self.engine.connect() as conn:
                return conn.execute(text(sql), params or {}).scalar()
        except Exception:
            return None

    def _rows_safe(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(text(sql), params or {}).mappings().all()
                return [dict(r) for r in rows]
        except Exception:
            return []

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

    def _export_m5_summary(self, payload: dict[str, Any]) -> dict[str, Path]:
        output_dir = self.repo_root / "artifacts" / "m5" / "m9_bridge"
        output_dir.mkdir(parents=True, exist_ok=True)

        latest_run_id = payload.get("latest_run_id")
        run_part = f"_r{latest_run_id}" if latest_run_id is not None else ""
        prefix = f"m5_m9_bridge_summary_p1{run_part}_{payload['report_date']}"

        md_path = output_dir / f"{prefix}.md"
        json_path = output_dir / f"{prefix}.json"

        md_path.write_text(self._render_m5_markdown(payload), encoding="utf-8")
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

    @staticmethod
    def _render_m5_markdown(payload: dict[str, Any]) -> str:
        lines = [
            "# M5 → M9 Bridge Summary",
            "",
            f"- Report Date: {payload['report_date']}",
            f"- Status: {payload['status']}",
            f"- Latest Run ID: {payload.get('latest_run_id') or '-'}",
            f"- Backtest Request ID: {payload.get('backtest_request_id') or '-'}",
            f"- Execution Mode: {payload.get('execution_mode') or '-'}",
            "",
            "## Human Summary",
            "",
            payload["human_summary"],
            "",
            "## Checks",
            "",
        ]

        for k, v in (payload.get("checks") or {}).items():
            lines.append(f"- {k}: {v}")

        lines.extend(["", "## Warnings", ""])
        warnings = payload.get("warnings") or []
        if warnings:
            for item in warnings:
                lines.append(f"- {item.get('code')}: {item.get('message')}")
        else:
            lines.append("- none")

        lines.extend(["", "## Latest Result", ""])
        latest_result = payload.get("latest_result") or {}
        if latest_result:
            for key in [
                "id",
                "run_id",
                "backtest_request_id",
                "result_status",
                "start_date",
                "end_date",
                "trading_days",
                "initial_cash",
                "final_equity",
                "total_return",
                "annual_return",
                "max_drawdown",
                "sharpe_ratio",
                "volatility",
                "order_count",
                "trade_count",
            ]:
                lines.append(f"- {key}: {latest_result.get(key)}")
        else:
            lines.append("- none")

        lines.extend(["", "## Artifacts", ""])
        artifact_codes = payload.get("artifact_codes") or []
        if artifact_codes:
            for code in artifact_codes:
                lines.append(f"- {code}")
        else:
            lines.append("- none")

        lines.extend(["", "## Backlog", ""])
        lines.append(f"- {payload.get('m5_11_backlog', 'Historical Signal Replay Backtest')}")
        return "\n".join(lines)

    @staticmethod
    def _coerce_json_dict(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        return {}

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