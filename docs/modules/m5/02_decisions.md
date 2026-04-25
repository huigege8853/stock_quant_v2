
---

# 2. `docs/modules/m5/02_decisions.md`

```markdown
# M5｜Decision Log

## D-M5-001｜M5 以 ops_run 为中心

所有 screen、backtest、execution plan、result skeleton 都必须绑定 `ops_run.id`。

原因：

- 保证研究运行可追踪。
- 保证 screen / backtest / artifact / metric / series 可统一查询。
- 为后续 walk-forward、parameter search、report 预留统一运行模型。

## D-M5-002｜M5 不修改 M4 strategy_signal

M5 只消费 M4 `strategy_signal`，不修改 signal contract。

`strategy_signal` 仍然只表达研究判断，不表达：

- target_weight
- target_qty
- order_qty
- position
- fill
- portfolio state

这些对象属于 M6 paper trading 或 backtest 内部执行层。

## D-M5-003｜screen_result 不复制 signal 明细

`research_screen_result` 只保存 screen 摘要：

- selected_count
- eligible_universe_size
- score_min
- score_max
- score_avg
- result_status

逐标的明细继续来自 `strategy_signal`。

导出明细时写入 `ops_run_artifact`，不新建 screen detail 表。

## D-M5-004｜backtest_request 只表达请求契约

`research_backtest_request` 保存：

- 策略版本
- signal / screen 来源
- 执行假设
- benchmark
- 时间范围
- 初始资金
- 调仓频率
- 组合构建方式
- 回测引擎配置

不在 request 中保存真实执行结果。

## D-M5-005｜backtest_result 只保存摘要

`research_backtest_result` 保存摘要结果，不保存长序列。

长序列进入：

- `ops_run_series_snapshot`

文件产物进入：

- `ops_run_artifact`

指标进入：

- `ops_run_metric_snapshot`

## D-M5-006｜execution_assumption_profile 独立实体化

手续费、滑点、成交价规则、T+1、涨跌停、停牌、手数、现金规则等全部进入 `research_execution_assumption_profile`。

不得写入：

- `strategy_signal`
- 策略核心逻辑
- backtrader adapter 硬编码

## D-M5-007｜benchmark_definition 当前不 seed 默认值

当前 benchmark 不设默认。

原因：

- 用户明确要求先不设默认 benchmark。
- M5 当前重点是 run / request / result / artifact 契约。
- 后续真实回测阶段再明确基准选择。

## D-M5-008｜benchmark_definition 第一轮不强制外键绑定 core_market_index

`research_benchmark_definition.market_index_id` 当前保留 nullable bigint，不在 ORM 层强制 FK。

原因：

- 当前数据库中实际指数主表命名需以后确认。
- benchmark 当前不 seed 默认。
- 不应让 benchmark 骨架阻塞 M5 主链。

## D-M5-009｜SQLAlchemy model 层暂不声明跨域 ForeignKey

M5 ORM model 中跨域字段使用普通 `BigInteger`，不写 `ForeignKey(...)`。

数据库级约束由 Alembic migration 管理。

原因：

- 避免 SQLAlchemy metadata 导入顺序导致跨模块表解析失败。
- research_domain 不应强依赖所有 M1/M2/M3/M4 model 的加载顺序。
- 后续需要 relationship 时再统一补充。

## D-M5-010｜Backtrader 通过 adapter 接入

Backtrader 不进入平台核心模型。

M5 当前设定三个 adapter / bridge：

- `BacktraderDataFeedAdapter`
- `BacktraderStrategyBridge`
- `BacktraderAnalyzerBridge`

平台核心仍然掌握：

- Run
- Request
- Result
- Metric
- Series
- Artifact
- Execution Assumption
- Benchmark

## D-M5-011｜M5.6 只生成 execution plan，不执行真实回测

M5.6 生成：

- data_feed_plan
- strategy_bridge_plan
- analyzer_bridge_plan
- backtest_execution_plan_json artifact
- backtest namespace metrics

但不启动真实 backtrader。

原因：

- 先验证边界。
- 先确认数据覆盖。
- 先确认 signal → strategy bridge 转换。
- 避免真实执行时混入 schema / contract 问题。

## D-M5-012｜M5.7 后再进入真实 backtrader

M5.7 先补文档收口。

完成文档后再进入：

```text
M5.8 Real Backtrader Minimal Execution