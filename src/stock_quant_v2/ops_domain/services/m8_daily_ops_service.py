from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from stock_quant_v2.ops_domain.services.m8_query_service import M8QueryService
from stock_quant_v2.ops_domain.services.m8_report_export_service import M8ReportExportService


class M8DailyOpsService:
    def __init__(self, session: Session):
        self.session = session
        self.query_service = M8QueryService(session)

    def daily_ops_check(
        self,
        *,
        portfolio_id: int,
        profile_code: str | None = None,
        export_report: bool = False,
        output_dir: Path | None = None,
    ) -> dict[str, Any]:
        latest = self.query_service.query_latest_runs(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
        )

        trading_chain = latest.get("trading_chain") or {}
        risk_chain = latest.get("risk_chain") or {}

        paper_chain = None
        risk_decision = None
        target_diff = None
        snapshot = None
        daily_report = None
        m5_backtest = self._query_m5_backtest_summary()

        if self._has_all(
            trading_chain,
            [
                "target_run_id",
                "order_run_id",
                "fill_run_id",
                "position_run_id",
                "snapshot_run_id",
            ],
        ):
            paper_chain = self.query_service.query_paper_chain(
                portfolio_id=portfolio_id,
                target_run_id=int(trading_chain["target_run_id"]),
                order_run_id=int(trading_chain["order_run_id"]),
                fill_run_id=int(trading_chain["fill_run_id"]),
                position_run_id=int(trading_chain["position_run_id"]),
                snapshot_run_id=int(trading_chain["snapshot_run_id"]),
            )

            snapshot = self.query_service.query_portfolio_snapshot(
                portfolio_id=portfolio_id,
                snapshot_run_id=int(trading_chain["snapshot_run_id"]),
            )

        if self._has_all(
            risk_chain,
            [
                "risk_run_id",
                "source_target_run_id",
                "adjusted_target_run_id",
            ],
        ):
            risk_decision = self.query_service.query_risk_decision(
                portfolio_id=portfolio_id,
                source_target_run_id=int(risk_chain["source_target_run_id"]),
                adjusted_target_run_id=int(risk_chain["adjusted_target_run_id"]),
                risk_run_id=int(risk_chain["risk_run_id"]),
                limit=200,
            )

            target_diff = self.query_service.query_target_diff(
                portfolio_id=portfolio_id,
                source_target_run_id=int(risk_chain["source_target_run_id"]),
                adjusted_target_run_id=int(risk_chain["adjusted_target_run_id"]),
                risk_run_id=int(risk_chain["risk_run_id"]),
                limit=200,
            )

        if export_report:
            daily_report = M8ReportExportService(self.session).export_daily_ops_report(
                output_dir=output_dir or Path("artifacts/m8/daily_ops"),
                portfolio_id=portfolio_id,
                profile_code=profile_code,
            )

        checks = self._build_checks(
            latest=latest,
            paper_chain=paper_chain,
            risk_decision=risk_decision,
            target_diff=target_diff,
            snapshot=snapshot,
            daily_report=daily_report,
            export_report=export_report,
        )

        warnings = self._build_warnings(
            latest=latest,
            paper_chain=paper_chain,
            risk_decision=risk_decision,
            target_diff=target_diff,
            snapshot=snapshot,
        )

        failures = [
            {
                "check_code": code,
                "message": item["message"],
            }
            for code, item in checks.items()
            if item["status"] == "FAIL"
        ]

        overall_status = "PASS"
        if failures:
            overall_status = "FAIL"
        elif warnings:
            overall_status = "WARN"

        return {
            "module": "M8.3",
            "query": "daily_ops_check",
            "portfolio_id": portfolio_id,
            "profile_code": profile_code,
            "checked_at": datetime.utcnow().isoformat(),
            "latest_runs": latest,
            "m5_backtest": m5_backtest,
            "paper_chain": self._compact_paper_chain(paper_chain),
            "risk_decision": self._compact_risk_decision(risk_decision),
            "target_diff": self._compact_target_diff(target_diff),
            "snapshot": self._compact_snapshot(snapshot),
            "daily_report": daily_report,
            "checks": checks,
            "warnings": warnings,
            "failures": failures,
            "overall_status": overall_status,
        }

    def daily_ops_plan(
        self,
        *,
        portfolio_id: int,
        profile_code: str | None = None,
    ) -> dict[str, Any]:
        check = self.daily_ops_check(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
            export_report=False,
        )

        latest = check.get("latest_runs") or {}
        trading_env = ((latest.get("powershell_env") or {}).get("trading_chain")) or []
        risk_env = ((latest.get("powershell_env") or {}).get("risk_chain")) or []

        actions: list[dict[str, Any]] = []

        actions.append(
            self._action(
                step_no=10,
                action_code="QUERY_LATEST_RUNS",
                title="识别最新交易链与风险链",
                command="python -m stock_quant_v2.scripts.m8_query_latest_runs",
                required=True,
                status="READY",
            )
        )

        actions.append(
            self._action(
                step_no=20,
                action_code="QUERY_PAPER_CHAIN",
                title="检查 paper trading chain",
                command="python -m stock_quant_v2.scripts.m8_query_paper_chain",
                required=True,
                status="READY" if trading_env else "BLOCKED",
                env=trading_env,
            )
        )

        actions.append(
            self._action(
                step_no=30,
                action_code="QUERY_RISK_DECISION",
                title="检查 risk decision",
                command="python -m stock_quant_v2.scripts.m8_query_risk_decision",
                required=True,
                status="READY" if risk_env else "BLOCKED",
                env=risk_env,
            )
        )

        actions.append(
            self._action(
                step_no=40,
                action_code="QUERY_TARGET_DIFF",
                title="检查 source target 与 adjusted target 差异",
                command="python -m stock_quant_v2.scripts.m8_query_target_diff",
                required=True,
                status="READY" if risk_env else "BLOCKED",
                env=risk_env,
            )
        )

        actions.append(
            self._action(
                step_no=50,
                action_code="EXPORT_DAILY_OPS_REPORT",
                title="导出 daily ops report",
                command="python -m stock_quant_v2.scripts.m8_export_daily_ops_report",
                required=True,
                status="READY",
                env=[
                    f'$env:M8_PORTFOLIO_ID="{portfolio_id}"',
                    *([f'$env:M8_RISK_PROFILE_CODE="{profile_code}"'] if profile_code else []),
                    '$env:M8_REPORT_OUTPUT_DIR="artifacts/m8/daily_ops"',
                ],
            )
        )

        recommended_next = []
        if check["overall_status"] == "PASS":
            recommended_next.append("当日 M8 运维检查通过，可以进入人工复核报告。")
        elif check["overall_status"] == "WARN":
            recommended_next.append("存在 WARN，建议先查看 warnings，再决定是否继续。")
        else:
            recommended_next.append("存在 FAIL，建议先修复 failures，不要进入下一阶段。")

        return {
            "module": "M8.3",
            "query": "daily_ops_plan",
            "portfolio_id": portfolio_id,
            "profile_code": profile_code,
            "check_status": check["overall_status"],
            "actions": actions,
            "recommended_next": recommended_next,
            "overall_status": "PASS" if all(a["status"] == "READY" for a in actions if a["required"]) else "WARN",
        }

    def ops_status_summary(
        self,
        *,
        portfolio_id: int,
        profile_code: str | None = None,
    ) -> dict[str, Any]:
        latest = self.query_service.query_latest_runs(
            portfolio_id=portfolio_id,
            profile_code=profile_code,
        )

        recent_runs = self._rows(
            """
            select
                id,
                run_type,
                run_name,
                status,
                trigger_type,
                requested_at,
                started_at,
                ended_at,
                created_at,
                updated_at,
                error_message
            from ops_run
            order by id desc
            limit 20
            """,
            {},
        )

        run_status_counts = self._rows(
            """
            select
                status,
                count(*) as cnt
            from ops_run
            group by status
            order by status
            """,
            {},
        )

        trading_chain = latest.get("trading_chain") or {}
        risk_chain = latest.get("risk_chain") or {}
        m5_backtest = self._query_m5_backtest_summary()

        summary = {
            "latest_trading_chain_complete": self._has_all(
                trading_chain,
                [
                    "target_run_id",
                    "order_run_id",
                    "fill_run_id",
                    "position_run_id",
                    "snapshot_run_id",
                ],
            ),
            "latest_risk_chain_complete": self._has_all(
                risk_chain,
                [
                    "risk_run_id",
                    "source_target_run_id",
                    "adjusted_target_run_id",
                ],
            ),
            "recent_run_count": len(recent_runs),
            "latest_m5_backtest_run_id": m5_backtest.get("run_id"),
            "latest_m5_backtest_status": m5_backtest.get("overall_status"),
            "latest_m5_backtest_execution_mode": m5_backtest.get("execution_mode"),
            "latest_m5_real_execution": bool(m5_backtest.get("real_execution")),
        }

        return {
            "module": "M8.3",
            "query": "ops_status_summary",
            "portfolio_id": portfolio_id,
            "profile_code": profile_code,
            "latest_runs": latest,
            "summary": summary,
            "m5_backtest": m5_backtest,
            "run_status_counts": run_status_counts,
            "recent_runs": recent_runs,
            "overall_status": "PASS"
            if summary["latest_trading_chain_complete"] and summary["latest_risk_chain_complete"]
            else "WARN",
        }

    def _build_checks(
        self,
        *,
        latest: dict[str, Any],
        paper_chain: dict[str, Any] | None,
        risk_decision: dict[str, Any] | None,
        target_diff: dict[str, Any] | None,
        snapshot: dict[str, Any] | None,
        daily_report: dict[str, Any] | None,
        export_report: bool,
    ) -> dict[str, dict[str, Any]]:
        checks = {
            "latest_runs_pass": self._check(
                latest.get("overall_status") == "PASS",
                "latest runs should be identified",
            ),
            "paper_chain_pass": self._check(
                paper_chain is not None and paper_chain.get("overall_status") == "PASS",
                "paper chain should pass",
            ),
            "risk_decision_pass": self._check(
                risk_decision is not None and risk_decision.get("overall_status") == "PASS",
                "risk decision should pass",
            ),
            "target_diff_pass": self._check(
                target_diff is not None and target_diff.get("overall_status") == "PASS",
                "target diff should pass",
            ),
            "snapshot_exists": self._check(
                snapshot is not None and snapshot.get("overall_status") == "PASS",
                "portfolio snapshot should exist",
            ),
        }

        if export_report:
            checks["daily_report_export_pass"] = self._check(
                daily_report is not None and daily_report.get("overall_status") == "PASS",
                "daily ops report should export successfully",
            )

        return checks

    def _build_warnings(
        self,
        *,
        latest: dict[str, Any],
        paper_chain: dict[str, Any] | None,
        risk_decision: dict[str, Any] | None,
        target_diff: dict[str, Any] | None,
        snapshot: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        warnings: list[dict[str, Any]] = []

        if latest.get("overall_status") == "WARN":
            warnings.append(
                {
                    "warning_code": "LATEST_RUNS_WARN",
                    "message": "latest_runs 未完全通过，可能存在某类 run 缺失。",
                }
            )

        risk_summary = (risk_decision or {}).get("summary") or {}
        reject_count = int(risk_summary.get("reject_count") or 0)
        warn_count = int(risk_summary.get("warn_count") or 0)
        adjust_count = int(risk_summary.get("adjust_count") or 0)

        if reject_count > 0:
            warnings.append(
                {
                    "warning_code": "RISK_REJECT_EXISTS",
                    "message": f"risk decision 存在 REJECT：{reject_count}",
                }
            )

        if warn_count > 0:
            warnings.append(
                {
                    "warning_code": "RISK_WARN_EXISTS",
                    "message": f"risk decision 存在 WARN：{warn_count}",
                }
            )

        if adjust_count > 0:
            warnings.append(
                {
                    "warning_code": "RISK_ADJUST_EXISTS",
                    "message": f"risk decision 存在 ADJUST：{adjust_count}",
                }
            )

        snapshot_obj = (snapshot or {}).get("snapshot") or {}
        if snapshot_obj:
            cash_balance = self._safe_decimal_str(snapshot_obj.get("cash_balance"))
            if cash_balance is not None and cash_balance.startswith("-"):
                warnings.append(
                    {
                        "warning_code": "NEGATIVE_CASH_BALANCE",
                        "message": f"snapshot cash_balance 为负：{cash_balance}",
                    }
                )

        diff_summary = (target_diff or {}).get("diff_summary") or {}
        if diff_summary:
            quantity_delta = self._safe_decimal_str(diff_summary.get("target_quantity_delta"))
            amount_delta = self._safe_decimal_str(diff_summary.get("target_amount_delta"))
            if quantity_delta not in {None, "0", "0E-8", "0.00000000"}:
                warnings.append(
                    {
                        "warning_code": "TARGET_QUANTITY_DIFF_EXISTS",
                        "message": f"target quantity 发生变化：{quantity_delta}",
                    }
                )
            if amount_delta not in {None, "0", "0E-8", "0.00000000"}:
                warnings.append(
                    {
                        "warning_code": "TARGET_AMOUNT_DIFF_EXISTS",
                        "message": f"target amount 发生变化：{amount_delta}",
                    }
                )

        return warnings

    @staticmethod
    def _check(ok: bool, message: str) -> dict[str, Any]:
        return {
            "status": "PASS" if ok else "FAIL",
            "message": message,
        }

    @staticmethod
    def _has_all(payload: dict[str, Any], keys: list[str]) -> bool:
        return all(payload.get(key) is not None for key in keys)

    @staticmethod
    def _action(
        *,
        step_no: int,
        action_code: str,
        title: str,
        command: str,
        required: bool,
        status: str,
        env: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "step_no": step_no,
            "action_code": action_code,
            "title": title,
            "required": required,
            "status": status,
            "env": env or [],
            "command": command,
        }

    @staticmethod
    def _compact_paper_chain(payload: dict[str, Any] | None) -> dict[str, Any] | None:
        if payload is None:
            return None
        return {
            "overall_status": payload.get("overall_status"),
            "runs": payload.get("runs"),
            "checks": payload.get("checks"),
            "target": payload.get("target"),
            "order": payload.get("order"),
            "fill": payload.get("fill"),
            "position": payload.get("position"),
            "snapshot": payload.get("snapshot"),
        }

    @staticmethod
    def _compact_risk_decision(payload: dict[str, Any] | None) -> dict[str, Any] | None:
        if payload is None:
            return None
        return {
            "overall_status": payload.get("overall_status"),
            "summary": payload.get("summary"),
            "reason_summary": payload.get("reason_summary"),
        }

    @staticmethod
    def _compact_target_diff(payload: dict[str, Any] | None) -> dict[str, Any] | None:
        if payload is None:
            return None
        return {
            "overall_status": payload.get("overall_status"),
            "source_target_run_id": payload.get("source_target_run_id"),
            "adjusted_target_run_id": payload.get("adjusted_target_run_id"),
            "risk_run_id": payload.get("risk_run_id"),
            "diff_summary": payload.get("diff_summary"),
            "risk_summary": payload.get("risk_summary"),
            "reason_summary": payload.get("reason_summary"),
        }

    @staticmethod
    def _compact_snapshot(payload: dict[str, Any] | None) -> dict[str, Any] | None:
        if payload is None:
            return None
        return {
            "overall_status": payload.get("overall_status"),
            "snapshot": payload.get("snapshot"),
            "checks": payload.get("checks"),
        }

    def _query_m5_backtest_summary(self) -> dict[str, Any]:
        """Read latest M5 backtest execution status for M8/M9 reporting.

        This helper is intentionally read-only and non-blocking. It should not
        change M8 daily ops overall status; it only makes the report aware that
        M5 has moved from placeholder / skeleton to real backtrader execution.
        """

        try:
            rows = self._rows(
                """
                select
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
                from research_backtest_result
                where result_status in ('SUCCESS', 'SUCCESS_WITH_WARN')
                order by id desc
                limit 1
                """,
                {},
            )
            if not rows:
                rows = self._rows(
                    """
                    select
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
                    from research_backtest_result
                    order by id desc
                    limit 1
                    """,
                    {},
                )

            if not rows:
                return {
                    "overall_status": "MISSING",
                    "run_id": None,
                    "backtest_request_id": None,
                    "execution_mode": None,
                    "real_execution": False,
                    "accepted_warning_codes": [],
                    "message": "No research_backtest_result found.",
                }

            result = dict(rows[0])
            summary = result.get("result_summary") or {}
            if not isinstance(summary, dict):
                summary = {}

            execution_mode = summary.get("execution_mode")
            warning_codes = summary.get("quality_warning_codes") or []
            if not isinstance(warning_codes, list):
                warning_codes = [str(warning_codes)]

            artifact_rows = self._rows(
                """
                select artifact_code
                from ops_run_artifact
                where run_id = :run_id
                order by artifact_code
                """,
                {"run_id": result["run_id"]},
            )
            artifact_codes = sorted(
                str(row["artifact_code"]) for row in artifact_rows if row.get("artifact_code")
            )

            required_artifacts = {
                "backtest_metrics_json",
                "backtest_equity_curve_csv",
                "backtest_trade_log_csv",
            }
            real_execution = (
                summary.get("stage") == "M5.10_BACKTRADER_REAL_EXECUTION_P1"
                and bool(summary.get("execution_enabled"))
                and required_artifacts.issubset(set(artifact_codes))
                and int(result.get("trade_count") or 0) > 0
            )

            accepted_warning_codes = []
            if execution_mode == "SNAPSHOT_STATIC_BASKET_P1" or "SNAPSHOT_STATIC_BASKET_P1" in warning_codes:
                accepted_warning_codes.append("SNAPSHOT_STATIC_BASKET_P1")

            if not real_execution:
                overall_status = "WARN"
            elif accepted_warning_codes:
                overall_status = "PASS_WITH_WARN"
            else:
                overall_status = "PASS"

            return {
                "overall_status": overall_status,
                "run_id": result.get("run_id"),
                "backtest_request_id": result.get("backtest_request_id"),
                "backtest_result_id": result.get("id"),
                "result_status": result.get("result_status"),
                "execution_mode": execution_mode,
                "real_execution": real_execution,
                "accepted_warning_codes": accepted_warning_codes,
                "start_date": str(result.get("start_date")) if result.get("start_date") else None,
                "end_date": str(result.get("end_date")) if result.get("end_date") else None,
                "trading_days": result.get("trading_days"),
                "final_equity": self._safe_decimal_str(result.get("final_equity")),
                "total_return": self._safe_decimal_str(result.get("total_return")),
                "max_drawdown": self._safe_decimal_str(result.get("max_drawdown")),
                "order_count": result.get("order_count"),
                "trade_count": result.get("trade_count"),
                "artifact_codes": artifact_codes,
                "message": (
                    "M5 real backtrader execution is available."
                    if real_execution
                    else "M5 latest backtest result is not yet a complete real execution."
                ),
            }
        except Exception as exc:
            return {
                "overall_status": "WARN",
                "run_id": None,
                "backtest_request_id": None,
                "execution_mode": None,
                "real_execution": False,
                "accepted_warning_codes": [],
                "message": f"Failed to query M5 backtest summary: {exc}",
            }

    def _rows(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        rows = self.session.execute(text(sql), params).mappings().all()
        return [dict(row) for row in rows]

    @staticmethod
    def _safe_decimal_str(value: Any) -> str | None:
        if value is None:
            return None
        return str(value)