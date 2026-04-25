# M7 Scope

阶段名称：M7 Paper Trading Multi-Day & Rebalance

## 本阶段目标

M7 的目标是将 M6 的单日 Paper Trading 最小闭环扩展为多日推进与调仓闭环。

M7 已完成：

1. 多日持仓 carry forward
2. T+1 available_quantity 更新
3. 新 target 与当前 position diff
4. BUY / SELL / HOLD 调仓订单
5. SELL 不超过 available_quantity
6. BUY / SELL fill
7. SELL realized_pnl
8. SELL stamp_duty
9. BUY 当日不可卖
10. position after fill
11. portfolio_snapshot 连续快照
12. 一键日内调仓总编排
13. M7 full quality check

## 本阶段不做

1. 真实券商接入
2. 高频 / 分钟级撮合
3. 复杂风控平台
4. 多策略资金分配
5. 实盘自动交易
6. 复杂组合优化器

## 最终验收

M7.5 总质量检查：

overall_status = PASS
