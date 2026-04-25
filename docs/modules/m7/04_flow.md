# M7 Flow

## M7.1 Carry Forward

trading_paper_position run 114
 trading_paper_position run 116

规则：

- quantity 不变
- available_quantity 从 0 更新为 quantity
- T+1 生效

## M7.2 Rebalance Order

current position run 116
+ target position run 111
+ template order run 119
 order run 141

结果：

- BUY = 3
- SELL = 6
- HOLD = 21
- inserted_order_count = 9

## M7.3-A Fill

order run 141
 fill run 142

结果：

- fill_count = 9
- buy_fill_count = 3
- sell_fill_count = 6
- buy_stamp_duty_total = 0
- sell_stamp_duty_total = 1506.74581500
- cash_delta = 1502133.72694050

## M7.3-B Position After Fill

position run 116
+ fill run 142
 position run 143

结果：

- current_quantity_total = 619500
- new_quantity_total = 466000
- new_available_quantity_total = 465700
- open_position_count = 27
- closed_position_count = 3
- realized_pnl_total = 9610.70168250

## M7.3-C Snapshot

previous snapshot run 114
+ position run 143
+ fill run 142
 snapshot run 144

结果：

- cash_balance = 1547842.73654439
- market_value = 8485436.00000000
- total_equity = 10033278.73654439
- realized_pnl = 9610.70168250

## M7.4 Daily Chain

一键入口：

python -m stock_quant_v2.scripts.bootstrap_m7_rebalance_daily_chain

最终 run：

- root run = 140
- order run = 141
- fill run = 142
- position run = 143
- snapshot run = 144
