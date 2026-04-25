# M7 Acceptance｜Paper Trading Multi-Day & Rebalance

项目名称：stock_quant_v2  
模块：M7 Paper Trading Multi-Day & Rebalance  
状态：PASS

## 1. 验收结论

M7 已从最小闭环升级为增强闭环，当前验收结论：

- M7.1 持仓滚动 / T+1 available_quantity：PASS
- M7.2 target diff / BUY SELL HOLD order：PASS
- M7.3-A order fill：PASS
- M7.3-B position after fill / realized_pnl / cash_delta：PASS
- M7.3-C portfolio snapshot：PASS
- M7.4 一键调仓闭环：PASS
- M7.5 full quality check：PASS
- M7.6 多日连续自动推进：PASS
- M7.6-Fix realized_pnl 累计口径：PASS
- M7.7 真实 target_quantity sizing：PASS

最终结论：

```text
M7 Paper Trading Multi-Day & Rebalance 增强闭环：PASS
```

## 2. 最终验收 Run

```text
portfolio_id = 1

target_position_run_id = 155

day 1:
as_of_date = 2026-04-21
effective_date = 2026-04-22
source_position_run_id = 143
carry_position_run_id = 145
target_position_run_id = 155
order_run_id = 146
fill_run_id = 147
position_run_id = 148
previous_snapshot_run_id = 144
snapshot_run_id = 149

day 2:
as_of_date = 2026-04-22
effective_date = 2026-04-23
source_position_run_id = 148
carry_position_run_id = 150
target_position_run_id = 155
order_run_id = 151
fill_run_id = 152
position_run_id = 153
previous_snapshot_run_id = 149
snapshot_run_id = 154

final_position_run_id = 153
final_snapshot_run_id = 154
```

## 3. M7.7 target_quantity sizing 验收结果

```text
target_position_run_id = 155
target_position_count = 30
target_quantity_total = 605400.00000000
target_amount_total = 9794717.00000000
zero_quantity_count = 0
construction_mode = EQUAL_WEIGHT_SELECTED
sizing_mode = EQUAL_WEIGHT_BY_EQUITY
status = SUCCESS
```

Python 验收结果：

```text
target_count = 30
target_quantity_total = 605400.00000000
target_amount_total = 9794717.00000000
null_quantity_count = 0
non_positive_quantity_count = 0
lot_violation_count = 0
```

## 4. 多日链路最终验收结果

```text
first_effective_date = 2026-04-22
last_effective_date = 2026-04-23
day_count = 2
success_count = 2
failed_count = 0
final_position_run_id = 153
final_snapshot_run_id = 154
status = SUCCESS
```

## 5. Day 1 调仓结果

```text
target_quantity_source = TARGET_POSITION
current_position_count = 27
target_position_count = 30

buy_order_count = 10
sell_order_count = 18
hold_count = 2
blocked_sell_count = 0
inserted_order_count = 28

current_quantity_total = 466000.00000000
target_quantity_total = 605400.00000000
```

## 6. Day 1 成交结果

```text
order_count = 28
inserted_fill_count = 28
buy_fill_count = 10
sell_fill_count = 18

total_buy_gross_amount = 1498033.00000000
total_sell_gross_amount = 188752.00000000
total_commission = 558.85120000
total_stamp_duty = 188.75200000
total_cash_delta = -1310028.60320000
```

## 7. Day 1 持仓结果

```text
current_position_count = 27
fill_count = 28
buy_fill_count = 10
sell_fill_count = 18
inserted_position_count = 30

open_position_count = 30
closed_position_count = 0

current_quantity_total = 466000.00000000
new_quantity_total = 605400.00000000
new_available_quantity_total = 456800.00000000

realized_pnl_delta = 5879.1122780000000000
cash_delta = -1310028.60320000
```

## 8. Day 1 Snapshot

```text
snapshot_run_id = 149
previous_snapshot_run_id = 144
position_run_id = 148
fill_run_id = 147

previous_cash_balance = 1547842.73654439
cash_delta = -1310028.60320000
cash_balance = 237814.13334439

market_value = 9794717.00000000
total_equity = 10032531.13334439
total_cost = 9777675.67995099

unrealized_pnl = 17041.32004901
realized_pnl = 5077.52739750

open_position_count = 30
closed_position_count = 0
status = SUCCESS
```

## 9. Day 2 连续推进结果

Day 2 未发生新调仓，30 个持仓全部 HOLD：

```text
current_position_count = 30
target_position_count = 30
buy_order_count = 0
sell_order_count = 0
hold_count = 30
inserted_order_count = 0

current_quantity_total = 605400.00000000
target_quantity_total = 605400.00000000
```

T+1 可卖数量滚动正确：

```text
Day 1 new_available_quantity_total = 456800.00000000
Day 2 target_available_quantity_total = 605400.00000000
```

Day 2 Snapshot：

```text
snapshot_run_id = 154
previous_snapshot_run_id = 149
position_run_id = 153
fill_run_id = 152

cash_balance = 237814.13334439
market_value = 9794717.00000000
total_equity = 10032531.13334439
total_cost = 9777675.67995099

unrealized_pnl = 17041.32004901
realized_pnl = 5077.52739750

open_position_count = 30
closed_position_count = 0
status = SUCCESS
```

## 10. 已验证规则

- 不修改 strategy_signal
- target_position.target_quantity 与 position.quantity 通过 sizing 后进入同一调仓口径
- M7.7 不再依赖 TEMPLATE_ORDER
- target_quantity_source = TARGET_POSITION 可完成真实调仓
- A 股 100 股手数约束通过
- BUY 当日不可卖
- SELL 不可超过 available_quantity
- BUY 不收 stamp_duty
- SELL 收 stamp_duty
- realized_pnl 必须计入 closed position
- realized_pnl 在多日 snapshot 中按累计口径继承
- portfolio_snapshot 支持 previous_snapshot_run_id / position_run_id / fill_run_id / realized_pnl / open_position_count / closed_position_count
- 多日链路支持上一日 position_run_id / snapshot_run_id 自动串联

## 11. 仍需后续处理但不阻塞 M7

- effective_date 当日 core_daily_bar 对目标池存在缺口，当前 paper trading 使用 fallback price 保证链路可验收。
- M8 / M2 Data Readiness 应在正式调度前检查 target universe 的 effective_date open 是否完整。
