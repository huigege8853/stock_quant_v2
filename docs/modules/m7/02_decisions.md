# M7 Decisions

## D-M7-001 不修改 strategy_signal

M7 继续沿用 M6 决策：交易域只消费 strategy_signal，不写回、不污染策略域。

## D-M7-002 target_position 与实际 position quantity 不同口径

M7 实测发现：

trading_paper_target_position.target_quantity
与
trading_paper_position.quantity

不能直接做 diff。

因此 M7 引入 target_quantity_source：

- TARGET_POSITION
- TEMPLATE_ORDER
- AUTO

测试调仓链路使用 TEMPLATE_ORDER 作为目标股数模板。

## D-M7-003 T+1 规则

BUY 当日：

available_quantity 不增加。

下一交易日 carry forward 后：

available_quantity = quantity。

## D-M7-004 SELL 约束

SELL order_quantity 必须满足：

sell_quantity <= available_quantity

## D-M7-005 SELL 手续费规则

BUY：

commission + slippage

SELL：

commission + stamp_duty + slippage

## D-M7-006 realized_pnl 必须写入 position 与 snapshot

SELL 后计算：

realized_pnl = sell_net_amount - sold_cost_amount

snapshot realized_pnl 必须包含 closed position 的 realized_pnl。

## D-M7-007 portfolio_snapshot 需要 M7 扩展字段

M7 新增 migration：

m7_0001_snap_ext

扩展字段：

- previous_snapshot_run_id
- position_run_id
- fill_run_id
- previous_cash_balance
- cash_delta
- total_cost
- unrealized_pnl
- realized_pnl
- open_position_count
- closed_position_count
