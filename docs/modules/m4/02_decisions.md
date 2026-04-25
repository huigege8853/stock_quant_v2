# M4 ｜ 02_decisions

## 本阶段决策目标

M4 的任务不是立刻做完所有策略域，而是先把策略从“脚本”提升为“平台对象”，并用一条最小规则策略主链验证：

- strategy_definition
- strategy_version
- strategy_parameter_schema
- strategy_signal

这四个核心对象可真正支撑研究域与交易域的统一语言。

---

## 已锁定决策

### D1. M4 第一轮只落四个核心对象
本轮先落：

- `strategy_definition`
- `strategy_version`
- `strategy_parameter_schema`
- `strategy_signal`

**不在本轮先落 `strategy_instance`。**

原因：

1. 当前首要目标是让策略“可定义、可版本化、可参数化、可统一输出 signal”。
2. `strategy_instance` 更适合在 M5 screen / backtest / parameter_search 扩展时独立升格。
3. 当前 run 级参数已可通过 `ops_run.context_json` 与 `strategy_signal.parameter_payload_json` 追踪。

---

### D2. strategy_signal 是统一信号契约，不是仓位契约
`strategy_signal` 只表达研究判断，不直接表达：

- target_weight
- target_qty
- cash_budget
- order_qty

这些都属于后续 M5/M6 的研究执行与 paper trading 领域。

---

### D3. strategy_signal.run_id 强绑定 ops_run.id
已锁定：

- `strategy_signal.run_id` → `ops_run.id`
- `nullable = false`

原因：

1. 平台当前已明确采用 Run 中心模型。
2. signal 是一次运行的产物，必须纳入统一 run 血缘。
3. 这保证 screen / backtest / paper 后续都能在 run 维度回溯。

---

### D4. strategy_signal.instrument_id 允许为空，但对单标的 signal 强绑定 meta_instrument.id
已锁定：

- `strategy_signal.instrument_id` → `meta_instrument.id`
- `nullable = true`

原因：

1. 当前 selection signal 是单标的，必须能追到 instrument。
2. 未来 timing / market / portfolio signal 可能不对应单一 instrument。
3. 因此允许为空，但单标的情况下必须填。

---

### D5. 唯一键保留 run 维度
已锁定唯一约束：

- `(run_id, strategy_version_id, as_of_date, subject_key, signal_action)`

原因：

1. 同一策略在同一天可能因不同 run / 参数 /环境被重复执行。
2. 平台要支持可复现与可对比，而不是天然覆盖。

---

### D6. effective_date 由交易日历推导
已锁定：

- `effective_date` 从 `meta_trading_calendar` 推导下一交易日

原因：

1. 交易日历属于平台 canonical calendar
2. 不应从 `core_daily_bar` 反推交易日
3. 避免被停牌、缺样本等业务主题污染

---

### D7. M4 第一条策略主链固定为 alpha_selection:v1
已锁定：

- strategy_code = `alpha_selection`
- version_code = `v1`
- feature_set = `fs_daily_alpha_v1:v1`

原因：

1. M3 已经真实验收通过 `fs_daily_alpha_v1`
2. 这是当前最稳、最短、最可复用的最小主链
3. 有利于先把 signal contract 验证通过

---

### D8. tradable_flag 当前不作为 M4 首链阻塞项
已锁定：

1. `feat_tradable_flag` 的当前数据语义尚未最终收口
2. 为避免阻塞 M4 首链，当前默认参数为：
   - `require_tradable_flag = false`
3. 后续应回到 M3 / definition 层统一锁定其语义，而不是长期在 M4 层绕过

---

### D9. bootstrap 脚本收薄，领域逻辑下沉到 strategy_domain
已锁定：

- `bootstrap_m4_rule_strategy_chain.py` 只做 orchestration
- feature 读取 / 参数校验 / 打分 / signal row 构造 都下沉到 `strategy_domain`

原因：

1. 脚本不是长期承载业务逻辑的合适位置
2. 后续 screen / backtest / paper 都要复用这些能力
3. 提前把 M4 收成 domain 层，可以降低 M5 成本

---

## 当前未锁定项

### O1. tradable_flag 最终语义
待补决策：

- `feat_tradable_flag = 1` 是否表示可交易
- `feat_tradable_flag = 0` 是否表示可交易
- 是否需要把 M3 输出定义调整为更直观的一致语义

### O2. timing 策略首链
待补决策：

- 是否在 M4 稳定版内补一条 `market:CN_A` 的 timing signal
- timing 的输入依赖是 market_breadth / market_index 还是单独市场状态快照

### O3. reason_code 字典扩充
当前已用：

- `TOP_N_SELECTED`

后续应补：

- `BELOW_MIN_SCORE`
- `FEATURE_MISSING`
- `NOT_TRADABLE`
- `MARKET_RISK_ON`
- `MARKET_RISK_OFF`

---

## 当前阶段结论

**M4 当前已经从“表设计完成”推进到“规则策略主链已跑通”。**

下一步不应回退重做主链，而应继续：

1. 固化 tradable_flag 语义
2. 增补 acceptance / test / documentation
3. 扩 timing 骨架
4. 为 M5 screen / backtest 做接口准备