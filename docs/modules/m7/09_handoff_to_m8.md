# M7 Handoff to M8

项目名称：stock_quant_v2  
当前阶段：M7 已完成，准备进入 M8 接口 / 调度 / 运维。

## 1. M7 最终结论

M7 Paper Trading Multi-Day & Rebalance 已完成增强闭环：

```text
strategy_signal / target_position
→ 真实 target_quantity sizing
→ current position carry
→ target diff
→ BUY / SELL / HOLD order
→ paper fill
→ position after fill
→ T+1 available_quantity
→ realized_pnl
→ portfolio snapshot
→ multi-day chain
```

最终验收：

```text
M7.6 多日连续自动推进：PASS
M7.6 realized_pnl 累计口径：PASS
M7.7 真实 target_quantity sizing：PASS
M7 Paper Trading Multi-Day & Rebalance 增强闭环：PASS
```

## 2. 最终 run 快照

```text
portfolio_id = 1
target_position_run_id = 155

day 1:
source_position_run_id = 143
carry_position_run_id = 145
order_run_id = 146
fill_run_id = 147
position_run_id = 148
previous_snapshot_run_id = 144
snapshot_run_id = 149

day 2:
source_position_run_id = 148
carry_position_run_id = 150
order_run_id = 151
fill_run_id = 152
position_run_id = 153
previous_snapshot_run_id = 149
snapshot_run_id = 154

final_position_run_id = 153
final_snapshot_run_id = 154
```

## 3. M8 建议范围

M8 不建议一开始就做完整 FastAPI。建议先做 M8.1 Run Monitor + CLI 运维入口。

M8.1 最小目标：

- 能查询任意 ops_run 状态
- 能查询 paper trading chain 的 order/fill/position/snapshot 汇总
- 能查询 portfolio 最新 snapshot
- 能导出 M7 多日链路摘要
- 能诊断失败 run 的失败点
- 能为后续 scheduler / API 提供服务层

## 4. M8.1 建议目录

```text
src/stock_quant_v2/ops_domain/
src/stock_quant_v2/ops_domain/dto/
src/stock_quant_v2/ops_domain/repositories/
src/stock_quant_v2/ops_domain/services/
src/stock_quant_v2/ops_domain/tasks/

src/stock_quant_v2/ops_domain/services/run_monitor_service.py
src/stock_quant_v2/ops_domain/tasks/query_run_status.py

src/stock_quant_v2/scripts/m8_query_run.py
src/stock_quant_v2/scripts/m8_query_paper_chain.py
src/stock_quant_v2/scripts/m8_query_portfolio_snapshot.py
src/stock_quant_v2/scripts/m8_export_paper_chain_summary.py
```

## 5. M8.1 第一批 CLI 建议

### 5.1 查询 run

```powershell
$env:M8_RUN_ID="154"
python -m stock_quant_v2.scripts.m8_query_run
```

### 5.2 查询 paper chain

```powershell
$env:M8_PORTFOLIO_ID="1"
$env:M8_ORDER_RUN_ID="146"
$env:M8_FILL_RUN_ID="147"
$env:M8_POSITION_RUN_ID="148"
$env:M8_SNAPSHOT_RUN_ID="149"
python -m stock_quant_v2.scripts.m8_query_paper_chain
```

### 5.3 查询 portfolio snapshot

```powershell
$env:M8_PORTFOLIO_ID="1"
$env:M8_SNAPSHOT_RUN_ID="154"
python -m stock_quant_v2.scripts.m8_query_portfolio_snapshot
```

### 5.4 导出链路摘要

```powershell
$env:M8_PORTFOLIO_ID="1"
$env:M8_OUTPUT_DIR="artifacts/m8/paper_chain"
python -m stock_quant_v2.scripts.m8_export_paper_chain_summary
```

## 6. M8 需要继承的 M7 决策

- 不直接修改 strategy_signal
- 交易域只消费 signal / target_position，不重写策略逻辑
- target_position 是 signal 到 trading 的桥梁
- order/fill/position/snapshot 都必须有 run_id
- snapshot 是 portfolio 运维查询的核心对象
- paper trading 允许 fallback price，但必须在 M8 readiness / diagnostics 中显式暴露
- M8 API / Scheduler 必须围绕 Run 组织，不直接暴露底层混乱细节

## 7. M8 启动所需文件

建议新聊天启动时提供：

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

## 8. M8 验收标准建议

M8.1 完成标准：

- 可通过 CLI 查询 run 基础信息
- 可通过 CLI 查询 M7 paper chain 汇总
- 可通过 CLI 查询 latest / specific portfolio snapshot
- 可导出 JSON/Markdown 链路摘要
- 查询结果能覆盖 SUCCESS / FAILED / RUNNING
- 不新增业务交易逻辑，只做接口、查询、监控和导出
