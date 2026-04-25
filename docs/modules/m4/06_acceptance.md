# M4 ｜ 06_acceptance

## 本阶段验收目标

M4 第一轮目标不是完成全部策略域，而是确认以下最小主链已经可运行、可落库、可复用：

1. `strategy_definition` 已落地。
2. `strategy_version` 已落地并能被标记为 current。
3. `strategy_parameter_schema` 已落地并能表达参数约束。
4. `strategy_signal` 已落地并承接统一 signal contract。
5. 至少 1 条规则策略主链已跑通。
6. Signal 只表达研究判断，不直接表达仓位。

---

## 本轮验收对象

- strategy: `alpha_selection`
- version: `v1`
- feature set: `fs_daily_alpha_v1`
- output contract: `signal_v1`
- as_of_date: `2024-03-29`
- expected effective_date: `2024-04-01`

---

## 已通过验收项

### 1. strategy core 落地
已确认以下表可用：

- `strategy_definition`
- `strategy_version`
- `strategy_parameter_schema`
- `strategy_signal`

### 2. alpha_selection:v1 已可运行
`alpha_selection:v1` 已能消费 `fs_daily_alpha_v1` 并产出 selection signal。

### 3. signal contract 已贯通
已确认 signal 层输出以下核心语义：

- `subject_type = instrument`
- `signal_role = selection`
- `signal_side = long`
- `signal_action = select`
- `reason_code = TOP_N_SELECTED`

### 4. 时间语义正确
已确认：

- `as_of_date = 2024-03-29`
- `effective_date = 2024-04-01`

这说明 signal 生效日期已与当日快照日期正确分离。

### 5. 首轮实际运行结果
首轮实际运行结果如下：

- `selected_count = 30`
- `eligible_universe_size = 5027`
- `score_min = 0.78414561`
- `score_max = 0.84932365`
- `score_avg = 0.8006165`

---

## 当前不纳入本轮阻塞项

以下事项当前不阻塞 M4 首链成立，但应在 M4 稳定版收尾前明确：

1. `feat_tradable_flag` 的语义需锁定。
2. `bootstrap_m4_rule_strategy_chain.py` 仍需继续下沉到 `strategy_domain`。
3. 需补齐最小单元测试。
4. 需补齐 M4 交接文档与 next_chat_brief。

---

## 验收 SQL

执行：

- `sql/m4_1_acceptance.sql`

重点检查：

1. strategy core 是否存在。
2. `alpha_selection:v1` 是否存在且 `is_current = true`。
3. parameter schema 是否存在。
4. `2024-03-29` 的 signal 数量是否正确。
5. `effective_date` 是否全部为 `2024-04-01`。
6. 是否没有同一 run 内的重复 signal。
7. signal 是否全部挂到 `ops_run`。
8. signal 是否全部挂到 `instrument_id`。

---

## 当前阶段结论

**M4 最小可用规则策略主链已通过验收。**

这意味着项目已从：

- M3：指标 / 因子 / 特征 / 标签闭环

推进到：

- M4：策略对象化 + 参数 schema + 统一 signal contract + 最小规则策略主链

后续可以继续进入：

- M4 稳定版收尾
- M4 timing 策略扩展
- M5 screen / backtest 接入

## SQL 结果判读标准

### A. strategy_definition
应至少存在 1 行：

- `strategy_code = alpha_selection`
- `strategy_type = selection`
- `engine_type = rule`
- `lifecycle_status = active`

### B. strategy_version
应满足：

- `alpha_selection:v1` 存在
- `is_current = true`
- `output_contract_version = signal_v1`

### C. strategy_parameter_schema
应满足：

- `strategy_version_id` 与 `alpha_selection:v1` 对应
- `schema_version_code = jsonschema_v1`
- `parameter_schema_json` 非空
- `example_payload_json` 非空

### D. strategy_signal 数量
对于本轮验收样本：

- `as_of_date = 2024-03-29`
- `effective_date = 2024-04-01`
- `signal_count = 30`

如果 signal_count 不为 30，说明：
- 运行参数不同
- feature 输入边界变化
- 或策略逻辑被改动

### E. signal 分布
应主要表现为：

- `subject_type = instrument`
- `signal_role = selection`
- `signal_side = long`
- `signal_action = select`
- `reason_code = TOP_N_SELECTED`

### F. effective_date
对于 `2024-03-29` 的首轮验收，所有 signal 都应满足：

- `effective_date = 2024-04-01`

若存在其他日期，说明交易日推导逻辑异常。

### G. run 血缘
所有 signal 都应满足：

- `run_id` 非空
- 能 join 到 `ops_run`
- `ops_run.run_type = strategy_signal_build`

### H. instrument 绑定
当前 alpha_selection 首链应满足：

- `instrument_id` 全部非空

若后续引入 timing / market signal，则该标准只适用于 instrument 型 signal。

### I. 重复信号
查询重复键时应返回 0 行。  
如果返回非 0 行，说明唯一性约束或写入逻辑有问题。

### J. 排名和分数
按 `rank_in_batch` 升序看：

- `raw_score` 应整体非增
- `normalized_score` 应整体非增
- `confidence_score` 当前与 `normalized_score` 一致