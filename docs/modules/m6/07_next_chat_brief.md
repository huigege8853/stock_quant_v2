

# 8. `docs/modules/m6/07_next_chat_brief.md`

```md
# M6 Next Chat Brief

项目名称：stock_quant_v2

当前阶段：M6 Paper Trading 域已完成最小闭环。

## 已完成模块

```text
M1 元数据与数据库框架
M2 数据主链
M3 indicator / factor / feature / label
M4 strategy_signal / alpha_selection:v1
M5 screen / backtest / metric / series / quality check
M6 paper trading minimal chain
M6 最终验收结果
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
M6 当前核心结论
M6 不修改 strategy_signal
M6 target_position 是交易域目标持仓
M6 paper_order / paper_fill / paper_position 独立建模
M6 不接真实券商
M6 使用 execution_assumption_profile
M6 order 阶段可用估算价
M6 fill 阶段严格 NEXT_OPEN
M6 cash 必须按 run 隔离
M6 最终结果写入 ops_run_metric_snapshot / ops_run_series_snapshot
M6 一键总编排已通过
关键脚本
bootstrap_m6_paper_account.py
bootstrap_m6_target_position_chain.py
bootstrap_m6_paper_order_chain.py
bootstrap_m6_paper_fill_chain.py
bootstrap_m6_paper_position_snapshot_chain.py
bootstrap_m6_trade_ledger_chain.py
bootstrap_m6_run_results_chain.py
check_m6_paper_trading_quality.py
bootstrap_m6_paper_trading_first_chain.py
一键运行命令
python -m stock_quant_v2.scripts.bootstrap_m6_paper_trading_first_chain

下一阶段建议：M7

M7 建议进入：

Paper Trading 多日推进
持仓滚动
T+1 可卖数量更新
调仓卖出
组合再平衡
基础风控约束