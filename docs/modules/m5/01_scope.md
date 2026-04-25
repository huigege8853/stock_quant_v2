# M5｜Research & Evaluation Domain｜Scope

## 1. 阶段定位

M5 是 stock_quant_v2 的研究与评估域，承接 M4 产出的 `strategy_signal`，向后为真实回测、walk-forward、参数搜索、报告导出、M6 paper trading 提供统一研究入口。

M5 的核心原则是：

- 以 `ops_run` 为中心追踪所有研究运行。
- M5 消费 M4 `strategy_signal`，不修改 signal contract。
- screen / backtest / result / artifact / metric / series 统一建模。
- backtrader 只作为执行器，通过 adapter 接入，不能侵入平台核心模型。
- 本阶段先完成最小研究评估闭环，不急于直接跑真实回测收益。

## 2. 本阶段已完成范围

### M5.1 Schema / Model

已新增 research core 表：

- `research_execution_assumption_profile`
- `research_benchmark_definition`
- `research_screen_request`
- `research_screen_result`
- `research_backtest_request`
- `research_backtest_result`

已新增 run 统一结果表：

- `ops_run_metric_snapshot`
- `ops_run_series_snapshot`
- `ops_run_artifact`

已新增 SQLAlchemy model：

- `db/models/research/*`
- `db/models/ops/run_metric_snapshot.py`
- `db/models/ops/run_series_snapshot.py`
- `db/models/ops/run_artifact.py`

### M5.2 Execution Assumption Seed

已 seed 默认执行假设：

- `profile_code = cn_a_daily_default`
- `version_code = v1`
- `profile_name = CN A Daily Default Execution Assumption v1`
- `initial_cash = 10000000`
- `price_fill_rule = NEXT_OPEN`
- `commission_rate = 0.0003`
- `min_commission = 5`
- `stamp_duty_rate = 0.001`
- `transfer_fee_rate = 0.00001`
- `slippage_model = BPS`
- `slippage_bps = 5`
- `t_plus_rule = T_PLUS_1`
- `lot_size = 100`
- `allow_fractional_share = false`
- `limit_up_down_rule = BLOCK_IF_LIMIT`
- `suspend_rule = BLOCK_IF_SUSPENDED`
- `cash_rule = STRICT_CASH`

当前不 seed 默认 benchmark。

### M5.3 Screen First Chain

已跑通：

```text
M4 strategy_signal
→ M5 screen_request
→ M5 screen_result
→ ops_run_metric_snapshot

## M5.8 Real Backtrader Minimal Execution

已跑通最小真实 backtrader 回测执行。

执行对象：

```text
backtest_request_id = 2
run_id = 61
source_signal_run_id = 53
screen_request_id = 3
execution_assumption_profile = cn_a_daily_default:v1
portfolio_construction_mode = EQUAL_WEIGHT_TOP_N
engine_code = backtrader

执行逻辑：

1. 读取 M4 strategy_signal
2. 按 effective_date 构造等权 target weight
3. 从 core_daily_bar 加载 30 只股票日线
4. 使用 backtrader 执行最小回测
5. 更新 research_backtest_result
6. 写入 ops_run_metric_snapshot
7. 写入 ops_run_series_snapshot
8. 写入 ops_run_artifact

验收结果：

run_id = 61
backtest_request_id = 2
backtest_result_id = 1
result_status = SUCCESS
initial_cash = 10000000.00000000
final_equity = 9749133.62932400
total_return = -0.02508664
annual_return = -0.03419767
max_drawdown = -0.25480463
sharpe_ratio = -0.06033385
volatility = 0.25128005
order_count = 90
trade_count = 30
trading_days = 184
series_written = 736

产物：

backtest_metrics_json
backtest_equity_curve_csv
backtest_trade_log_csv
M5.9 Backtest Result Quality Check

已完成只读质量检查。

检查对象：

run_id = 61
backtest_request_id = 2

检查结果：

overall_status = PASS
result_status_check = true
trade_log_check = true
equity_curve_check = true
series_check = true
artifact_check = true
metric_check = true

交易日志分布：

order_count = 90
├── Submitted = 30
├── Accepted = 30
└── Completed = 30

trade_count = 30
└── Completed orders only

结果一致性：

research_backtest_result.final_equity = 9749133.629324
equity_curve.last_equity = 9749133.629323998
metric final_equity = 9749133.6293239980

8 位精度对齐，无异常。

M5 当前完成判定

M5 当前已完成从 M4 signal 到真实最小 backtrader 回测结果的闭环：

M4 strategy_signal
→ M5 screen_request / screen_result
→ M5 backtest_request
→ M5 backtest_result
→ M5 backtest_execution_plan artifact
→ M5 real backtrader execution
→ ops_run_metric_snapshot
→ ops_run_series_snapshot
→ ops_run_artifact
→ M5 quality check

M5 可判定为阶段主链完成。