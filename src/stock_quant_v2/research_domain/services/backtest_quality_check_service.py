from __future__ import annotations

import csv
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


class BacktestQualityCheckService:
    """M5.9 回测结果质量检查。

    只读检查，不修改数据库和 artifact。
    """

    def __init__(self, session: Session):
        self.session = session

    def check_backtest_run(
        self,
        *,
        run_id: int,
    ) -> dict[str, Any]:
        result = self._load_backtest_result(run_id=run_id)
        artifacts = self._load_artifacts(run_id=run_id)
        series_summary = self._load_series_summary(run_id=run_id)
        metric_summary = self._load_metric_summary(run_id=run_id)

        trade_log_rows = self._read_csv_artifact(
            artifacts=artifacts,
            artifact_code="backtest_trade_log_csv",
        )
        equity_rows = self._read_csv_artifact(
            artifacts=artifacts,
            artifact_code="backtest_equity_curve_csv",
        )

        trade_log_check = self._check_trade_log(
            result=result,
            trade_log_rows=trade_log_rows,
        )
        equity_curve_check = self._check_equity_curve(
            result=result,
            equity_rows=equity_rows,
        )
        series_check = self._check_series(
            result=result,
            series_summary=series_summary,
        )
        artifact_check = self._check_artifacts(artifacts=artifacts)
        metric_check = self._check_metrics(metric_summary=metric_summary)

        checks = {
            "result_status_check": result["result_status"] == "SUCCESS",
            "trade_log_check": trade_log_check["status"] == "PASS",
            "equity_curve_check": equity_curve_check["status"] == "PASS",
            "series_check": series_check["status"] == "PASS",
            "artifact_check": artifact_check["status"] == "PASS",
            "metric_check": metric_check["status"] == "PASS",
        }

        overall_status = "PASS" if all(checks.values()) else "FAIL"

        return {
            "run_id": run_id,
            "backtest_request_id": result["backtest_request_id"],
            "overall_status": overall_status,
            "checks": checks,
            "result": result,
            "trade_log_check": trade_log_check,
            "equity_curve_check": equity_curve_check,
            "series_check": series_check,
            "artifact_check": artifact_check,
            "metric_check": metric_check,
            "notes": [
                "order_count includes Submitted / Accepted / Completed notifications.",
                "trade_count counts Completed orders only.",
                "M5.9 is read-only quality check; no database rows are modified.",
            ],
        }

    def _load_backtest_result(self, *, run_id: int) -> dict[str, Any]:
        row = self.session.execute(
            text(
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
                where run_id = :run_id
                order by id desc
                limit 1
                """
            ),
            {"run_id": run_id},
        ).mappings().first()

        if row is None:
            raise RuntimeError(f"research_backtest_result not found: run_id={run_id}")

        return dict(row)

    def _load_artifacts(self, *, run_id: int) -> dict[str, dict[str, Any]]:
        rows = self.session.execute(
            text(
                """
                select
                    id,
                    run_id,
                    artifact_code,
                    artifact_type,
                    storage_backend,
                    uri,
                    mime_type,
                    file_size_bytes,
                    artifact_metadata
                from ops_run_artifact
                where run_id = :run_id
                """
            ),
            {"run_id": run_id},
        ).mappings().all()

        return {row["artifact_code"]: dict(row) for row in rows}

    def _load_series_summary(self, *, run_id: int) -> dict[str, dict[str, Any]]:
        rows = self.session.execute(
            text(
                """
                select
                    series_code,
                    count(*) as row_count,
                    min(trade_date) as min_trade_date,
                    max(trade_date) as max_trade_date,
                    min(value_numeric) as min_value,
                    max(value_numeric) as max_value
                from ops_run_series_snapshot
                where run_id = :run_id
                  and series_namespace = 'backtest'
                group by series_code
                order by series_code
                """
            ),
            {"run_id": run_id},
        ).mappings().all()

        return {row["series_code"]: dict(row) for row in rows}

    def _load_metric_summary(self, *, run_id: int) -> dict[str, Any]:
        rows = self.session.execute(
            text(
                """
                select
                    metric_code,
                    metric_value_numeric,
                    metric_value_text
                from ops_run_metric_snapshot
                where run_id = :run_id
                  and metric_namespace = 'backtest'
                order by sequence_no asc
                """
            ),
            {"run_id": run_id},
        ).mappings().all()

        return {
            row["metric_code"]: (
                row["metric_value_numeric"]
                if row["metric_value_numeric"] is not None
                else row["metric_value_text"]
            )
            for row in rows
        }

    def _read_csv_artifact(
        self,
        *,
        artifacts: dict[str, dict[str, Any]],
        artifact_code: str,
    ) -> list[dict[str, str]]:
        artifact = artifacts.get(artifact_code)
        if artifact is None:
            return []

        uri = artifact.get("uri")
        if not uri:
            return []

        path = Path(uri)
        if not path.exists():
            return []

        with path.open("r", encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))

    def _check_trade_log(
        self,
        *,
        result: dict[str, Any],
        trade_log_rows: list[dict[str, str]],
    ) -> dict[str, Any]:
        status_counter = Counter(row.get("status") for row in trade_log_rows)

        completed_count = status_counter.get("Completed", 0)
        submitted_count = status_counter.get("Submitted", 0)
        accepted_count = status_counter.get("Accepted", 0)

        result_order_count = int(result["order_count"] or 0)
        result_trade_count = int(result["trade_count"] or 0)

        status = "PASS"
        reasons = []

        if len(trade_log_rows) != result_order_count:
            status = "FAIL"
            reasons.append(
                "trade_log row count does not match research_backtest_result.order_count"
            )

        if completed_count != result_trade_count:
            status = "FAIL"
            reasons.append(
                "Completed order count does not match research_backtest_result.trade_count"
            )

        if completed_count <= 0:
            status = "FAIL"
            reasons.append("no Completed orders found")

        return {
            "status": status,
            "trade_log_rows": len(trade_log_rows),
            "result_order_count": result_order_count,
            "result_trade_count": result_trade_count,
            "submitted_count": submitted_count,
            "accepted_count": accepted_count,
            "completed_count": completed_count,
            "status_counter": dict(status_counter),
            "reasons": reasons,
        }

    def _check_equity_curve(
        self,
        *,
        result: dict[str, Any],
        equity_rows: list[dict[str, str]],
    ) -> dict[str, Any]:
        status = "PASS"
        reasons = []

        if not equity_rows:
            return {
                "status": "FAIL",
                "reasons": ["equity curve artifact is empty or missing"],
            }

        first = equity_rows[0]
        last = equity_rows[-1]

        first_equity = self._decimal_or_none(first.get("portfolio_equity"))
        last_equity = self._decimal_or_none(last.get("portfolio_equity"))

        result_final_equity = result["final_equity"]
        result_initial_cash = result["initial_cash"]

        if last_equity is None:
            status = "FAIL"
            reasons.append("last equity is null")

        if result_final_equity is not None and last_equity is not None:
            if self._round8(result_final_equity) != self._round8(last_equity):
                status = "FAIL"
                reasons.append("last equity does not match final_equity")

        if len(equity_rows) != int(result["trading_days"] or 0):
            status = "FAIL"
            reasons.append("equity row count does not match trading_days")

        return {
            "status": status,
            "row_count": len(equity_rows),
            "first_trade_date": first.get("trade_date"),
            "last_trade_date": last.get("trade_date"),
            "first_equity": str(first_equity) if first_equity is not None else None,
            "last_equity": str(last_equity) if last_equity is not None else None,
            "result_initial_cash": str(result_initial_cash),
            "result_final_equity": str(result_final_equity),
            "reasons": reasons,
        }

    def _check_series(
        self,
        *,
        result: dict[str, Any],
        series_summary: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        required_series = {
            "portfolio_equity",
            "cash",
            "holding_count",
            "gross_exposure",
        }

        status = "PASS"
        reasons = []

        missing = sorted(required_series.difference(series_summary.keys()))
        if missing:
            status = "FAIL"
            reasons.append(f"missing series: {missing}")

        trading_days = int(result["trading_days"] or 0)

        per_series = {}
        total_rows = 0

        for code in sorted(required_series):
            item = series_summary.get(code)
            if item is None:
                continue

            row_count = int(item["row_count"] or 0)
            total_rows += row_count

            if row_count != trading_days:
                status = "FAIL"
                reasons.append(
                    f"series {code} row_count={row_count} does not match trading_days={trading_days}"
                )

            per_series[code] = {
                "row_count": row_count,
                "min_trade_date": str(item["min_trade_date"]),
                "max_trade_date": str(item["max_trade_date"]),
                "min_value": str(item["min_value"]),
                "max_value": str(item["max_value"]),
            }

        holding = series_summary.get("holding_count")
        if holding is not None:
            max_holding = holding["max_value"]
            if max_holding is None or Decimal(str(max_holding)) <= 0:
                status = "FAIL"
                reasons.append("holding_count never becomes positive")

        return {
            "status": status,
            "total_rows": total_rows,
            "expected_total_rows": trading_days * len(required_series),
            "per_series": per_series,
            "reasons": reasons,
        }

    def _check_artifacts(
        self,
        *,
        artifacts: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        required_artifacts = {
            "backtest_metrics_json",
            "backtest_equity_curve_csv",
            "backtest_trade_log_csv",
        }

        status = "PASS"
        reasons = []

        missing = sorted(required_artifacts.difference(artifacts.keys()))
        if missing:
            status = "FAIL"
            reasons.append(f"missing artifacts: {missing}")

        existing = {}
        for code in sorted(required_artifacts):
            artifact = artifacts.get(code)
            if artifact is None:
                continue

            uri = artifact.get("uri")
            path_exists = bool(uri and Path(uri).exists())

            if not path_exists:
                status = "FAIL"
                reasons.append(f"artifact path not found: {code}")

            existing[code] = {
                "uri": uri,
                "file_size_bytes": artifact.get("file_size_bytes"),
                "path_exists": path_exists,
            }

        return {
            "status": status,
            "existing": existing,
            "reasons": reasons,
        }

    def _check_metrics(
        self,
        *,
        metric_summary: dict[str, Any],
    ) -> dict[str, Any]:
        required_metrics = {
            "initial_cash",
            "final_equity",
            "total_return",
            "annual_return",
            "max_drawdown",
            "volatility",
            "order_count",
            "trade_count",
            "trading_days",
        }

        missing = sorted(required_metrics.difference(metric_summary.keys()))
        status = "PASS" if not missing else "FAIL"

        return {
            "status": status,
            "metric_count": len(metric_summary),
            "missing": missing,
            "metrics": {
                key: str(value) if value is not None else None
                for key, value in metric_summary.items()
            },
        }

    @staticmethod
    def _decimal_or_none(value: Any) -> Decimal | None:
        if value is None or value == "":
            return None
        return Decimal(str(value))

    @staticmethod
    def _round8(value: Any) -> Decimal:
        return Decimal(str(value)).quantize(Decimal("0.00000001"))