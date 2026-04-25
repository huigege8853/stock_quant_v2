# 10. `docs/modules/m6/09_handoff_to_m7.md`

```md
# stock_quant_v2｜M6 → M7 交接文档

版本：v1.0  
阶段：M6 已完成，准备进入 M7  
项目：stock_quant_v2

---

## 1. M6 完成结论

M6 Paper Trading 最小闭环已完成并通过一键总编排验收。

最终链路：

```text
strategy_signal
→ trading_paper_target_position
→ trading_paper_order
→ trading_paper_fill
→ trading_paper_position
→ trading_paper_portfolio_snapshot
→ trading_paper_trade_ledger
→ ops_run_metric_snapshot
→ ops_run_series_snapshot
→ quality_check
2. 最终验收 run
source_signal_run_id = 81
source_screen_request_id = 3
as_of_date = 2026-04-17
effective_date = 2026-04-20

target_run_id = 111
order_run_id = 112
fill_run_id = 113
position_snapshot_run_id = 114
ledger_run_id = 115
portfolio_id = 1
3. 最终结果
target_count = 30
order_count = 30
fill_count = 30
position_count = 30
snapshot_count = 1
ledger_count = 122
metric_written = 22
series_written = 9
overall_status = PASS

资金结果：

initial_cash = 10000000.00000000
cash_balance = 45709.00960389
market_value = 9989383.00000000
total_equity = 10035092.00960389
cash_diff = 0
equity_diff = 0
4. 已落地表
trading_paper_account
trading_paper_portfolio
trading_paper_target_position
trading_paper_order
trading_paper_fill
trading_paper_position
trading_paper_portfolio_snapshot
trading_paper_trade_ledger

复用统一结果表：

ops_run_metric_snapshot
ops_run_series_snapshot
ops_run
5. 已落地目录
src/stock_quant_v2/db/models/trading/
src/stock_quant_v2/trading_domain/
src/stock_quant_v2/scripts/bootstrap_m6_*.py
src/stock_quant_v2/scripts/check_m6_paper_trading_quality.py
sql/m6_1_acceptance.sql
docs/modules/m6/
6. 关键脚本
bootstrap_m6_paper_account.py
bootstrap_m6_target_position_chain.py
bootstrap_m6_paper_order_chain.py
bootstrap_m6_paper_fill_chain.py
bootstrap_m6_paper_position_snapshot_chain.py
bootstrap_m6_trade_ledger_chain.py
bootstrap_m6_run_results_chain.py
check_m6_paper_trading_quality.py
bootstrap_m6_paper_trading_first_chain.py

一键总编排：

python -m stock_quant_v2.scripts.bootstrap_m6_paper_trading_first_chain
7. M6 关键边界
7.1 不修改 strategy_signal

M6 只消费 strategy_signal，不写回。

7.2 target_position 是交易域对象

M6 target_position 不等于 M5 backtest target_weight。

7.3 paper_order / paper_fill / paper_position 独立建模

M6 交易状态不复用 backtrader 内部状态。

7.4 不做真实下单

M6 仅 paper trading。

7.5 fill 阶段严格 NEXT_OPEN

order 阶段可估算，fill 阶段必须用 effective_date open。

7.6 cash 按 run 隔离

避免同一 portfolio 同一日期多次调试 run 互相污染。

8. M7 建议目标

M7 建议名称：

M7 Paper Trading Multi-Day & Rebalance

M7 建议范围：

1. 多日 paper trading 推进
2. 持仓 carry forward
3. T+1 available_quantity 更新
4. 新 target 与旧 position 对比
5. BUY / SELL 双向 order
6. 卖出成交与 realized_pnl
7. stamp_duty on SELL
8. portfolio_snapshot 连续序列
9. 多日 quality check
10. 基础 rebalance ledger
9. M7 不建议一开始做
真实券商接入
高频/分钟级撮合
复杂组合优化器
复杂风控平台
多策略资金分配
实盘自动交易

这些应在 M7 多日 paper trading 稳定后再进入 M8/M9。

10. 新聊天启动语

项目名称：stock_quant_v2

当前阶段：M6 Paper Trading 最小闭环已完成，准备进入 M7。

M6 已完成：

trading_paper_account / portfolio
target_position
paper_order
paper_fill
paper_position
portfolio_snapshot
trade_ledger
metric / series
quality_check
一键总编排

M6 最终验收：

source_signal_run_id = 81
source_screen_request_id = 3
as_of_date = 2026-04-17
effective_date = 2026-04-20
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
total_equity = 10035092.00960389
cash_diff = 0
equity_diff = 0

M6 关键结论：

M6 不修改 strategy_signal
M6 target_position 不等于 M5 backtest target_weight
M6 paper_order / paper_fill / paper_position 独立建模
M6 不接真实券商
M6 fill 阶段严格 NEXT_OPEN
M6 cash 按 run 隔离
M6 最终结果写入 ops_run_metric_snapshot / ops_run_series_snapshot

请继续推进 M7：Paper Trading 多日推进 / 持仓滚动 / T+1 可卖数量更新 / 调仓卖出 / 多日 snapshot / 多日 quality check。


---

M6 收尾文件到这里就齐了。下一步建议先把这些文件落盘，然后跑一次：

```powershell
git status

确认 M6 所有新增文件都在版本控制视野里。