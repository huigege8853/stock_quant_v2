# M7 Next Chat Brief

项目名称：stock_quant_v2

当前阶段：M7 Paper Trading Multi-Day & Rebalance 已完成增强闭环。

## 当前状态

M7 已完成：

- M7.1 持仓滚动 / T+1 available_quantity
- M7.2 target diff / BUY SELL HOLD order
- M7.3-A order fill
- M7.3-B position after fill / realized_pnl / cash_delta
- M7.3-C portfolio snapshot
- M7.4 一键调仓闭环
- M7.5 full quality check
- M7.6 多日连续自动推进
- M7.6-Fix realized_pnl 累计口径
- M7.7 真实 target_quantity sizing

最终状态：

```text
M7 Paper Trading Multi-Day & Rebalance 增强闭环：PASS
```

## 最终验收 Run

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

## 最终验收结果摘要

```text
day_count = 2
success_count = 2
failed_count = 0
status = SUCCESS

target_position_count = 30
target_quantity_total = 605400.00000000
target_amount_total = 9794717.00000000

day 1:
buy_order_count = 10
sell_order_count = 18
hold_count = 2
inserted_order_count = 28

inserted_fill_count = 28
buy_fill_count = 10
sell_fill_count = 18

new_quantity_total = 605400.00000000
new_available_quantity_total = 456800.00000000

cash_balance = 237814.13334439
market_value = 9794717.00000000
total_equity = 10032531.13334439
realized_pnl = 5077.52739750

day 2:
buy_order_count = 0
sell_order_count = 0
hold_count = 30
new_quantity_total = 605400.00000000
new_available_quantity_total = 605400.00000000
realized_pnl = 5077.52739750
```

## 已锁定关键结论

- M7 不修改 strategy_signal
- M7.7 通过 target_position.target_quantity 完成真实调仓口径
- M7 不再依赖 TEMPLATE_ORDER 做真实调仓
- target_quantity_source = TARGET_POSITION 已验收
- BUY 当日不可卖，T+1 后 available_quantity 滚动为 quantity
- SELL 不可超过 available_quantity
- BUY 不收 stamp_duty
- SELL 收 stamp_duty
- realized_pnl 必须计入 closed position
- realized_pnl 在 snapshot 中采用累计口径
- 多日链路自动串联上一日 position_run_id / snapshot_run_id

## 下一阶段建议

进入 M8 接口 / 调度 / 运维。

M8 建议先做 M8.1 Run Monitor + CLI 运维入口，而不是直接做完整 API。

建议任务：

- M8.1-A 统一 run 查询
- M8.1-B paper trading chain 状态查询
- M8.1-C 最近 portfolio snapshot 查询
- M8.1-D M7 多日链路运行摘要导出
- M8.1-E 失败 run / 异常链路诊断
- M8.2 再做 scheduler / API / report export

## M8 启动时建议提供文件

```text
src/stock_quant_v2/db/models/ops/run.py
src/stock_quant_v2/db/models/ops/run_step.py
src/stock_quant_v2/db/models/ops/run_artifact.py
src/stock_quant_v2/db/models/ops/run_metric_snapshot.py
src/stock_quant_v2/db/models/ops/run_series_snapshot.py
src/stock_quant_v2/data_domain/repositories/run_repository.py
src/stock_quant_v2/db/session.py
src/stock_quant_v2/config/settings.py
```
