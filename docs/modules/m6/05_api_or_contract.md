
---

# 6. `docs/modules/m6/05_api_or_contract.md`

```md
# M6 API / Contract｜Paper Trading 内部契约

## 1. 输入契约

### source signal

```text
source_signal_run_id
source_screen_request_id
as_of_date
effective_date
target_count

当前验收：

source_signal_run_id = 81
source_screen_request_id = 3
as_of_date = 2026-04-17
effective_date = 2026-04-20
target_count = 30
portfolio
portfolio_id
strategy_version_id
execution_assumption_profile_id
initial_cash

当前验收：

portfolio_id = 1
strategy_version_id = 1
execution_assumption_profile_id = 1
initial_cash = 10000000
2. TargetPosition Contract

输入：

strategy_signal rows
portfolio construction rule

输出：

trading_paper_target_position

约束：

target_side = LONG
target_weight = 1 / selected_count
status = PENDING → ORDERED
3. PaperOrder Contract

输入：

target_position
portfolio cash
execution profile
estimated price

输出：

trading_paper_order

约束：

order_side = BUY
order_type = MARKET
price_fill_rule = NEXT_OPEN
time_in_force = DAY
order_quantity = 100 的整数倍
estimated_net_amount 不超过可用现金预算
4. PaperFill Contract

输入：

ACCEPTED paper_order
effective_date open
execution profile

输出：

trading_paper_fill

约束：

fill_rule = NEXT_OPEN
price_source = CORE_DAILY_BAR_OPEN
fill_status = COMPLETED
BUY 不收 stamp_duty
cash_delta = -net_amount
5. Position Contract

输入：

COMPLETED paper_fill
effective_date close

输出：

trading_paper_position

约束：

position_status = OPEN
available_quantity = 0
market_value = quantity * close
unrealized_pnl = market_value - cost_amount
6. PortfolioSnapshot Contract

输入：

paper_position
paper_fill cash_delta
portfolio initial_cash

输出：

trading_paper_portfolio_snapshot

约束：

cash_balance = initial_cash + sum(fill.cash_delta)
total_equity = cash_balance + market_value
holding_count = count(position.quantity > 0)
7. Quality Contract

质量检查必须全部为 True：

target_count_check
target_status_check
order_count_check
order_status_check
fill_count_check
fill_status_check
position_count_check
position_status_check
snapshot_count_check
holding_count_check
cash_formula_check
equity_formula_check
cash_non_negative_check
signal_source_exists_check