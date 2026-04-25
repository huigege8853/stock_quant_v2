# M6 Decisions

## D-M6-001｜M6 使用 trading_paper_* 表名前缀

M6 Paper Trading 域统一使用 `trading_paper_*` 作为物理表名前缀。

逻辑对象仍称为 paper_account / paper_portfolio / paper_target_position / paper_order / paper_fill / paper_position / paper_portfolio_snapshot / paper_trade_ledger。

## D-M6-002｜第一轮 target_position 使用 30 只等权

M6 第一轮消费 `signal_run_id=53` 和 `screen_request_id=3`，按 `EQUAL_WEIGHT_SELECTED` 生成 30 只等权目标持仓。

该 target_weight 是 M6 交易域自行生成的 target_position 字段，不复用 M5 backtest 内部 target_weight。

## D-M6-003｜第一轮 initial_cash 使用 10000000

M6 第一轮 paper_account / paper_portfolio 初始资金使用 `10000000 CNY`，与 M5 验证资金保持一致，便于对照，但不复用 M5 backtest_result 作为交易状态。

## D-M6-004｜order_qty 使用 fee-aware + STRICT_CASH

M6 第一轮生成 paper_order 时，按预估成交价、滑点、手续费和手数约束计算 order_qty，避免现金为负。

## D-M6-005｜EOD snapshot 使用 effective_date close 估值

M6 第一轮成交价使用 effective_date open + slippage，组合日终估值使用 effective_date close。