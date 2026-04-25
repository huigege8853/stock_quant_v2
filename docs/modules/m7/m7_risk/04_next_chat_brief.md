# M7-Risk Next Chat Brief

项目名称：stock_quant_v2  
当前模块：M7-Risk 统一风控域  
当前状态：M7-Risk 最小闭环已完成并验收 PASS。

## 1. 当前已完成

M7-Risk 已完成：

```text
M7-Risk.1 Unified Risk Decision Layer
M7-Risk.2 Profile Variants
```

核心对象已落地：

```text
risk_rule
risk_profile
risk_profile_rule
risk_decision
```

已打通链路：

```text
source target_position_run_id = 155
→ risk decision
→ adjusted target_position_run_id = 160 / 161 / 162
→ trading paper rebalance
```

## 2. 最终验收 Run

```text
portfolio_id = 1
source_target_run_id = 155

default profile:
risk_run_id = 159
adjusted_target_run_id = 160

conservative profile:
risk_run_id = 162
adjusted_target_run_id = 161

data strict profile:
risk_run_id = 163
adjusted_target_run_id = 162
```

## 3. Profile Variant 验收结果

```text
default profile:
target_quantity_total = 605400
adjust_count = 0
reject_count = 0

conservative profile:
target_quantity_total = 547400
adjust_count = 30
reject_count = 0

data strict profile:
target_quantity_total = 0
adjust_count = 0
reject_count = 30

overall_status = PASS
```

这证明：

```text
同一批 Signal / target_position
在不同 risk_profile 下
可以得到不同目标仓位。
```

## 4. 与交易域联通状态

交易域已成功消费：

```text
target_position_run_id = 160
```

并完成 2 天 paper trading：

```text
day_count = 2
success_count = 2
failed_count = 0
final_position_run_id = 153
final_snapshot_run_id = 154
status = SUCCESS
```

## 5. 已锁定原则

```text
策略层不内嵌平台级风控。
strategy_signal 不修改。
原始 target_position 不修改。
风控层生成新的 adjusted target_position run。
risk_decision 记录所有 PASS / WARN / REJECT / ADJUST。
交易域必须消费风控后的 target_position run。
```

## 6. 下一步选择

有两个方向：

### A. 继续 M7-Risk.3

继续补风控增强：

```text
行业暴露约束
市场风险开关
最大换手率
流动性约束
ST 过滤
风控报表导出
```

### B. 进入 M8

进入接口 / 调度 / 运维：

```text
Run Monitor
Paper Chain Query
Portfolio Snapshot Query
Risk Decision Query
Daily Scheduler
Report Export
```

推荐：

```text
如果目标是完整满足 M7 风控域 PRD，继续 M7-Risk.3。
如果目标是让平台可运维运行，进入 M8.1。
```
