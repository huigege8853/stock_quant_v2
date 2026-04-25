# M7-Risk.3 Acceptance｜Exposure / Market Switch / Liquidity

项目名称：stock_quant_v2  
模块：M7-Risk.3  
状态：PASS

## 1. 验收结论

M7-Risk.3 已完成以下增强风控规则：

```text
R007_INDUSTRY_MAX_WEIGHT
R009_MARKET_RISK_SWITCH
R011_LIQUIDITY_FILTER
```

最终结论：

```text
M7-Risk.3 行业暴露 / 市场风险开关 / 流动性约束：PASS
```

## 2. 设计原则

M7-Risk.3 不推翻 M7-Risk.1 / M7-Risk.2，而是在已经通过的风控后 target run 上继续叠加增强风控：

```text
M7.7 original target_position_run_id = 155
M7-Risk.1 default adjusted_target_run_id = 160
M7-Risk.3 source_target_run_id = 160
M7-Risk.3 adjusted_target_run_id = 165 / 166
```

原则：

```text
不修改 strategy_signal
不修改原始 target_position
不修改 M7-Risk.1 产出的 target run
M7-Risk.3 生成新的 adjusted target run
所有 PASS / WARN / REJECT / ADJUST 写入 risk_decision
```

## 3. Conservative Profile 验收

Profile：

```text
risk_profile_code = paper_cn_a_risk3_conservative_v1
risk_run_id = 164
source_target_run_id = 160
adjusted_target_run_id = 165
portfolio_id = 1
```

结果：

```text
source_target_count = 30
adjusted_target_count = 30
decision_count = 90

pass_count = 30
warn_count = 30
reject_count = 0
adjust_count = 30

source_target_quantity_total = 605400.00000000
adjusted_target_quantity_total = 543700.00000000
status = SUCCESS
```

质量检查：

```text
target_count = 30
target_quantity_total = 543700.00000000
target_amount_total = 8784949.00000000

rejected_target_count = 0
adjusted_target_count = 30
passed_target_count = 0

decision_count = 90
pass_count = 30
warn_count = 30
reject_count = 0
adjust_count = 30

overall_status = PASS
```

原因码：

```text
R009_MARKET_RISK_REDUCE = ADJUST 30
R011_LIQUIDITY_FILTER = PASS 30
R007_MISSING_INDUSTRY = WARN 30
```

解释：

```text
市场风险开关触发 REDUCE，将组合目标数量从 605400 降至 543700。
行业分类缺失被记录为 WARN。
流动性约束通过。
```

## 4. Strict Profile 验收

Profile：

```text
risk_profile_code = paper_cn_a_risk3_strict_v1
risk_run_id = 167
source_target_run_id = 160
adjusted_target_run_id = 166
portfolio_id = 1
```

结果：

```text
source_target_count = 30
adjusted_target_count = 30
decision_count = 90

pass_count = 60
warn_count = 0
reject_count = 30
adjust_count = 0

source_target_quantity_total = 605400.00000000
adjusted_target_quantity_total = 0E-8
status = SUCCESS
```

质量检查：

```text
target_count = 30
target_quantity_total = 0E-8
target_amount_total = 0E-8

rejected_target_count = 30
adjusted_target_count = 0
passed_target_count = 0

decision_count = 90
pass_count = 60
warn_count = 0
reject_count = 30
adjust_count = 0

overall_status = PASS
```

原因码：

```text
R007_MISSING_INDUSTRY = REJECT 30
R009_MARKET_RISK_SWITCH_SKIPPED_AFTER_REJECT = PASS 30
R011_LIQUIDITY_FILTER_SKIPPED_AFTER_REJECT = PASS 30
```

解释：

```text
strict profile 下，行业分类缺失直接触发 REJECT。
每个标的被 R007 拒绝后，后续 R009 / R011 不再改变该标的，仅记录 skipped_after_reject。
```

## 5. M7-Risk.3 已验证能力

```text
行业暴露规则进入 risk_rule / risk_profile_rule
市场风险开关可调整目标仓位
流动性约束可参与风控决策
风控执行顺序有效
已拒绝标的后续规则不会重复调整
风险结果统一进入 risk_decision
不同 profile 能产生不同目标仓位
```

## 6. 数据状态说明

本轮暴露了行业数据缺口：

```text
industry_coverage_count = 0
industry_missing_count = 30
```

这不阻塞 M7-Risk.3，因为：

```text
observe/conservative profile 可 WARN
strict profile 可 REJECT
风险决策均已统一落库
```

后续 M2/M8 可补充行业标签数据接入与数据完备性检查。
