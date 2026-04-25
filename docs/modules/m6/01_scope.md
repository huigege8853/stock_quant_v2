M6 Scope｜Paper Trading 最小闭环

## 1. 模块目标

M6 的目标是完成 Paper Trading 域的最小闭环。

M6 不是真实交易模块，也不是 M5 backtest 的延伸。M6 是独立交易域，负责把研究信号转化为模拟交易状态。

核心链路：

```text
strategy_signal
→ trading_paper_target_position
→ trading_paper_order
→ trading_paper_fill
→ trading_paper_position
→ trading_paper_portfolio_snapshot
→ trading_paper_trade_ledger
→ ops_run_metric_snapshot / ops_run_series_snapshot
→ quality_check
2. 本阶段已完成
paper_account / paper_portfolio
paper_target_position
paper_order
paper_fill
paper_position
paper_portfolio_snapshot
paper_trade_ledger
M6 quality check
M6 metric / series result writer
M6 一键总编排脚本
3. 本阶段不做
不接真实券商
不做真实下单
不做多日滚动持仓
不做调仓卖出
不做 T+1 可卖数量跨日更新
不做风控约束体系
不修改 strategy_signal
不把 M5 backtest target_weight 直接当 M6 target_position
不复用 backtrader 内部 order / trade / position 作为 M6 状态源
4. 当前验收输入
source_signal_run_id = 81
source_screen_request_id = 3
as_of_date = 2026-04-17
effective_date = 2026-04-20
target_count = 30
initial_cash = 10000000
execution_assumption_profile_id = 1
strategy_version_id = 1
portfolio_id = 1
5. 当前最终验收输出
target_run_id = 111
order_run_id = 112
fill_run_id = 113
position_snapshot_run_id = 114
ledger_run_id = 115

target_count = 30
order_count = 30
fill_count = 30
position_count = 30
snapshot_count = 1
ledger_count = 122
metric_written = 22
series_written = 9
overall_status = PASS
6. M6 完成判定

M6 Paper Trading 最小闭环已完成。


---

# 3. `docs/modules/m6/02_decisions.md`

```md
# M6 Decisions｜Paper Trading 域关键决策

## D-M6-001｜M6 使用 trading_paper_* 表名前缀

M6 物理表统一使用 `trading_paper_*` 前缀。

已落地：

```text
trading_paper_account
trading_paper_portfolio
trading_paper_target_position
trading_paper_order
trading_paper_fill
trading_paper_position
trading_paper_portfolio_snapshot
trading_paper_trade_ledger

D-M6-002｜M6 target_position 独立于 M5 backtest target_weight

trading_paper_target_position.target_weight 是 M6 交易域目标仓位，不等于 M5 backtest 内部 target_weight。

M5 backtest 内部 target_weight 只能作为研究回测执行计划，不可直接作为 M6 持仓状态。

D-M6-003｜strategy_signal 只表达研究判断

M6 只消费 strategy_signal，不修改 strategy_signal。

M6 不向 strategy_signal 写入：

target_weight
target_quantity
order_quantity
fill_quantity
position_quantity
cash_balance
market_value
portfolio_equity
D-M6-004｜M6 不接真实券商

M6 只做 paper trading：

paper_order = 模拟订单
paper_fill = 模拟成交
paper_position = 模拟持仓

不接真实券商，不生成真实委托，不做真实交易。

D-M6-005｜第一轮组合构造使用 30 只等权

当前 M6 第一轮使用：

construction_mode = EQUAL_WEIGHT_SELECTED
target_count = 30
target_weight = 1 / 30
long_only = true
D-M6-006｜order 阶段允许估算价格，fill 阶段严格 NEXT_OPEN

M6.3 order 生成阶段：

优先使用 effective_date open 估算订单金额
如果 open 不存在，可使用最近 close 做 estimated_price
estimated_price 只是预算，不是成交价

M6.4 fill 成交阶段：

必须使用 effective_date open
严格 NEXT_OPEN
open 不存在则不能成交
D-M6-007｜M6 现金必须按 run 隔离

同一个 portfolio / 同一个日期可能存在多次调试 run。

fill 阶段现金计算只允许使用当前 fill_run_id 已产生的成交，不得把同一天其他 fill_run 的 cash_delta 混入当前链路。

该问题已在 M6.10 前修复。

D-M6-008｜最终结果挂到 position_snapshot_run_id

M6 metric / series 统一写入最终交易状态 run：

result_run_id = position_snapshot_run_id

当前最终结果 run：

position_snapshot_run_id = 114
D-M6-009｜trade_ledger 作为审计流水

M6.8 生成最小审计流水：

TARGET_CREATED = 30
ORDER_ACCEPTED = 30
FILL_COMPLETED = 30
POSITION_UPDATED = 30
SNAPSHOT_CREATED = 1
QUALITY_CHECKED = 1
total = 122
D-M6-010｜M6 一键总编排已通过

脚本：

python -m stock_quant_v2.scripts.bootstrap_m6_paper_trading_first_chain

最终输出：

status = SUCCESS
overall_status = PASS
metric_written = 22
series_written = 9