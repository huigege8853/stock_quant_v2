
---

# 4. `docs/modules/m6/03_schema.md`

```md
# M6 Schema｜Paper Trading 数据模型

## 1. 核心表

### trading_paper_account

账户资金容器。

核心字段：

```text
id
account_code
account_name
account_type
market_code
base_currency
initial_cash
status
opened_at
closed_at
created_at
updated_at

trading_paper_portfolio

Paper trading 组合。

核心字段：

id
account_id
portfolio_code
portfolio_name
strategy_version_id
execution_assumption_profile_id
source_signal_run_id
source_screen_request_id
portfolio_construction_mode
rebalance_frequency
max_position_count
long_only
initial_cash
start_date
end_date
status
trading_paper_target_position

交易域目标持仓。

核心字段：

id
run_id
portfolio_id
source_signal_run_id
source_screen_request_id
strategy_signal_id
as_of_date
effective_date
instrument_id
target_side
target_weight
target_amount
target_quantity
rank_no
score
reason_code
target_source
construction_mode
status
status_reason

状态：

PENDING
ORDERED
SKIPPED
CANCELED
trading_paper_order

模拟订单。

核心字段：

id
run_id
portfolio_id
target_position_id
instrument_id
order_date
effective_date
order_side
order_type
price_fill_rule
time_in_force
target_quantity
order_quantity
estimated_price
estimated_gross_amount
estimated_fee
estimated_net_amount
status
reject_reason

状态：

NEW
ACCEPTED
REJECTED
CANCELED
FILLED
PARTIALLY_FILLED
trading_paper_fill

模拟成交。

核心字段：

id
run_id
portfolio_id
order_id
instrument_id
fill_date
fill_price
fill_quantity
gross_amount
commission_amount
stamp_duty_amount
transfer_fee_amount
slippage_amount
total_fee_amount
net_amount
cash_delta
price_source
fill_rule
fill_status

状态：

COMPLETED
REJECTED
CANCELED
trading_paper_position

EOD 持仓快照。

核心字段：

id
run_id
portfolio_id
instrument_id
position_date
quantity
available_quantity
frozen_quantity
avg_cost
cost_amount
market_price
market_value
unrealized_pnl
realized_pnl
total_pnl
position_status

当前 M6 首日买入语义：

quantity > 0
available_quantity = 0
position_status = OPEN
trading_paper_portfolio_snapshot

组合 EOD 快照。

核心字段：

id
run_id
portfolio_id
snapshot_date
cash_balance
market_value
total_equity
gross_exposure
net_exposure
holding_count
daily_pnl
cumulative_pnl
daily_return
cumulative_return
turnover_amount
turnover_rate

核心公式：

total_equity = cash_balance + market_value
cash_balance = initial_cash + sum(fill.cash_delta)
trading_paper_trade_ledger

交易审计流水。

核心字段：

id
run_id
portfolio_id
event_date
event_type
instrument_id
target_position_id
order_id
fill_id
position_id
portfolio_snapshot_id
quantity_delta
cash_delta
amount_delta
reason_code
message
payload_json
created_at

当前事件：

TARGET_CREATED
ORDER_ACCEPTED
FILL_COMPLETED
POSITION_UPDATED
SNAPSHOT_CREATED
QUALITY_CHECKED
2. 统一结果表

M6 复用 M5 已落地的统一 Run Result 表：

ops_run_metric_snapshot
ops_run_series_snapshot

M6 namespace：

metric_namespace = M6_PAPER_TRADING
series_namespace = M6_PAPER_TRADING

当前写入：

metric = 22
series = 9
3. 当前最终链路 run_id
target_run_id = 111
order_run_id = 112
fill_run_id = 113
position_snapshot_run_id = 114
ledger_run_id = 115