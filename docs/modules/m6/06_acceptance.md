
---

# 7. `docs/modules/m6/06_acceptance.md`

```md
# M6 Acceptance｜验收记录

## 1. 最终一键总编排命令

```powershell
$env:M6_PAPER_ACCOUNT_CODE="paper_cn_a_default"
$env:M6_PAPER_PORTFOLIO_CODE="paper_alpha_selection_v1_default"
$env:M6_STRATEGY_VERSION_ID="1"
$env:M6_EXECUTION_ASSUMPTION_PROFILE_ID="1"
$env:M6_SOURCE_SIGNAL_RUN_ID="81"
$env:M6_SOURCE_SCREEN_REQUEST_ID="3"
$env:M6_AS_OF_DATE="2026-04-17"
$env:M6_EFFECTIVE_DATE="2026-04-20"
$env:M6_TARGET_COUNT="30"
$env:M6_INITIAL_CASH="10000000"
$env:M6_PORTFOLIO_CONSTRUCTION_MODE="EQUAL_WEIGHT_SELECTED"

Remove-Item Env:M6_PAPER_PORTFOLIO_ID -ErrorAction SilentlyContinue
Remove-Item Env:M6_TARGET_RUN_ID -ErrorAction SilentlyContinue
Remove-Item Env:M6_ORDER_RUN_ID -ErrorAction SilentlyContinue
Remove-Item Env:M6_FILL_RUN_ID -ErrorAction SilentlyContinue
Remove-Item Env:M6_LEDGER_RUN_ID -ErrorAction SilentlyContinue
Remove-Item Env:M6_POSITION_SNAPSHOT_RUN_ID -ErrorAction SilentlyContinue

python -m stock_quant_v2.scripts.bootstrap_m6_paper_trading_first_chain

2. 最终输出
status = SUCCESS
overall_status = PASS
portfolio_id = 1
source_signal_run_id = 81
source_screen_request_id = 3
as_of_date = 2026-04-17
effective_date = 2026-04-20
target_run_id = 111
order_run_id = 112
fill_run_id = 113
position_snapshot_run_id = 114
ledger_run_id = 115
metric_written = 22
series_written = 9
3. 数量验收
target_count = 30
order_count = 30
fill_count = 30
position_count = 30
snapshot_count = 1
ledger_count = 122
metric_count = 22
series_count = 9
4. 状态验收
target = ORDERED 30
order = FILLED 30
fill = COMPLETED 30
position = OPEN 30
5. 资金与权益验收
initial_cash = 10000000.00000000
cash_balance = 45709.00960389
market_value = 9989383.00000000
total_equity = 10035092.00960389

cash_diff = 0
equity_diff = 0
6. 质量检查
overall_status = PASS

target_count_check = True
target_status_check = True
order_count_check = True
order_status_check = True
fill_count_check = True
fill_status_check = True
position_count_check = True
position_status_check = True
snapshot_count_check = True
holding_count_check = True
cash_formula_check = True
equity_formula_check = True
cash_non_negative_check = True
signal_source_exists_check = True
7. 验收结论

M6 Paper Trading 最小闭环通过验收。


---