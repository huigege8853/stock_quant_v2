# M7 Open Items

M7 Paper Trading Multi-Day & Rebalance 增强闭环已通过，以下事项不阻塞 M7 验收。

## 1. Data Readiness / target universe 行情完整性

本次 M7.7 真实 target_quantity sizing 后，目标池 30 个标的在 effective_date=2026-04-22 均缺少当日 core_daily_bar 行情。

当前处理：

- Paper trading fill 使用 fallback price。
- 如果 effective_date NEXT_OPEN 缺失，则可回退到 estimated_price / 最近历史 close。
- 该逻辑用于保证 paper trading 验证链路不中断。

后续应在 M2/M8 增加：

- target universe effective_date open 完整性检查
- data readiness / watermark
- 缺口扫描与修复
- 缺价标的列表输出
- 是否允许 fallback 的显式配置

## 2. 风控约束增强

后续可加入：

- 停牌过滤
- 涨跌停过滤
- 单票最大权重
- 最大换手率
- 行业约束
- 最大持仓数约束
- 最小现金缓冲
- 最小成交金额
- 低流动性过滤

## 3. Ledger 增强

当前 M7 重点完成 position/snapshot，后续可补：

- REBALANCE_STARTED
- ORDER_CREATED
- FILL_EXECUTED
- POSITION_UPDATED
- CASH_CHANGED
- SNAPSHOT_CREATED
- REBALANCE_FINISHED
- TARGET_SIZED
- PRICE_FALLBACK_USED
- DATA_READINESS_WARNING

## 4. 结果写入 metric / series

后续可将 M7 日调仓结果写入：

- ops_run_metric_snapshot
- ops_run_series_snapshot
- ops_run_artifact

建议记录：

- order_count
- fill_count
- buy/sell count
- cash_delta
- market_value
- total_equity
- realized_pnl
- unrealized_pnl
- open_position_count
- closed_position_count
- turnover_amount
- fallback_price_count

## 5. API / Scheduler

后续 M8 可封装：

- daily paper trading CLI
- paper trading date range CLI
- run monitor
- portfolio snapshot query
- scheduler
- report export
- failure diagnostics

## 6. target quantity sizing 进一步增强

M7.7 当前完成最小真实 sizing：

- equal weight
- sizing capital
- target price
- 100 股手数向下取整
- target_amount / target_quantity 写入 target_position

后续可增强：

- 根据可用现金动态缩放
- 根据单票最大权重限制
- 根据价格缺失直接剔除
- 根据停牌/涨跌停剔除
- 根据行业约束调整
- 根据 lot rounding 后剩余现金二次分配

## 7. 成交模型进一步增强

当前 paper trading 成交模型可继续增强：

- 使用 explicit execution_assumption_profile
- 支持成交失败 / 部分成交
- 支持涨跌停无法成交
- 支持停牌无法成交
- 支持成交价来源标记
- 支持 fallback price warning
