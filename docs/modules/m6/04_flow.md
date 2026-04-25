
---

# 5. `docs/modules/m6/04_flow.md`

```md
# M6 Flow｜Paper Trading 最小闭环流程

## 1. 总流程

```text
M4 strategy_signal
→ M6 target_position
→ M6 paper_order
→ M6 paper_fill
→ M6 paper_position
→ M6 portfolio_snapshot
→ M6 trade_ledger
→ ops_run_metric_snapshot / ops_run_series_snapshot
→ quality_check

2. M6.1 account / portfolio

脚本：

python -m stock_quant_v2.scripts.bootstrap_m6_paper_account

输入：

M6_PAPER_ACCOUNT_CODE
M6_PAPER_PORTFOLIO_CODE
M6_STRATEGY_VERSION_ID
M6_EXECUTION_ASSUMPTION_PROFILE_ID
M6_SOURCE_SIGNAL_RUN_ID
M6_SOURCE_SCREEN_REQUEST_ID
M6_START_DATE
M6_INITIAL_CASH

输出：

trading_paper_account
trading_paper_portfolio
3. M6.2 target_position

脚本：

python -m stock_quant_v2.scripts.bootstrap_m6_target_position_chain

输入：

source_signal_run_id = 81
screen_request_id = 3
as_of_date = 2026-04-17
effective_date = 2026-04-20
target_count = 30

输出：

trading_paper_target_position 30 rows
4. M6.3 paper_order

脚本：

python -m stock_quant_v2.scripts.bootstrap_m6_paper_order_chain

逻辑：

读取 target_position
读取 portfolio.initial_cash
读取 execution_assumption_profile
生成 BUY MARKET NEXT_OPEN paper_order

注意：

order 阶段 estimated_price 可用最近 close 做预算
成交价不在 order 阶段确定
5. M6.4 paper_fill

脚本：

python -m stock_quant_v2.scripts.bootstrap_m6_paper_fill_chain

逻辑：

读取 ACCEPTED paper_order
读取 effective_date open
按 NEXT_OPEN + slippage 成交
生成 paper_fill
订单状态更新为 FILLED

要求：

strict NEXT_OPEN
effective_date open 不存在则不能成交
6. M6.5 / M6.6 position / snapshot

脚本：

python -m stock_quant_v2.scripts.bootstrap_m6_paper_position_snapshot_chain

逻辑：

读取 COMPLETED paper_fill
按 fill 汇总 position
用 effective_date close 估值
生成 portfolio_snapshot
7. M6.7 quality check

脚本：

python -m stock_quant_v2.scripts.check_m6_paper_trading_quality

检查：

target_count = 30
order_count = 30
fill_count = 30
position_count = 30
snapshot_count = 1
cash_balance = initial_cash + sum(fill.cash_delta)
total_equity = cash_balance + market_value
8. M6.8 trade ledger

脚本：

python -m stock_quant_v2.scripts.bootstrap_m6_trade_ledger_chain

输出：

trading_paper_trade_ledger 122 rows
9. M6.9 run results

脚本：

python -m stock_quant_v2.scripts.bootstrap_m6_run_results_chain

输出：

ops_run_metric_snapshot 22 rows
ops_run_series_snapshot 9 rows
10. M6.10 一键总编排

脚本：

python -m stock_quant_v2.scripts.bootstrap_m6_paper_trading_first_chain

最终结果：

status = SUCCESS
overall_status = PASS