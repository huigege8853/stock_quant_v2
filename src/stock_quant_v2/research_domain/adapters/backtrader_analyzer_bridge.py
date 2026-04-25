from __future__ import annotations

from typing import Any

from stock_quant_v2.db.models.research import ResearchBacktestRequest


class BacktraderAnalyzerBridge:
    """定义 backtrader analyzer 输出如何回写平台。

    M5.6 只生成 analyzer plan，不计算真实指标。
    """

    def build_analyzer_plan(
        self,
        *,
        request: ResearchBacktestRequest,
        data_feed_plan: dict[str, Any],
        strategy_bridge_plan: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "bridge": "BacktraderAnalyzerBridge",
            "execution_enabled": False,
            "backtest_request_id": request.id,
            "run_id": request.run_id,
            "planned_metric_targets": [
                "total_return",
                "annual_return",
                "benchmark_return",
                "excess_return",
                "max_drawdown",
                "sharpe_ratio",
                "volatility",
                "win_rate",
                "turnover_avg",
            ],
            "planned_series_targets": [
                "portfolio_equity",
                "portfolio_return_daily",
                "benchmark_equity",
                "benchmark_return_daily",
                "drawdown",
                "cash",
                "turnover",
                "holding_count",
            ],
            "planned_artifact_targets": [
                "backtest_execution_plan_json",
                "backtest_metrics_json",
                "backtest_equity_curve_csv",
                "backtest_trade_log_csv",
                "backtest_report_html",
            ],
            "input_summary": {
                "bar_rows": data_feed_plan.get("bar_rows"),
                "trade_day_count": data_feed_plan.get("trade_day_count"),
                "selected_count": strategy_bridge_plan.get("selected_count"),
                "instrument_count": strategy_bridge_plan.get("instrument_count"),
            },
            "note": "M5.6 plan only; analyzer output contract is reserved",
        }