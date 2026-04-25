# M7-Risk Final Acceptance

项目名称：stock_quant_v2  
模块：M7 统一风控域  
状态：PASS

## 1. 最终结论

M7 风控域已完成：

```text
M7-Risk.1 Unified Risk Decision Layer：PASS
M7-Risk.2 Profile Variants：PASS
M7-Risk.3 Exposure / Market Switch / Liquidity：PASS
```

最终状态：

```text
M7 风控域：PASS
```

## 2. 已完成对象

```text
risk_rule
risk_profile
risk_profile_rule
risk_decision
```

## 3. 已完成规则

```text
R001_MAX_POSITION_COUNT
R002_MAX_SINGLE_POSITION_WEIGHT
R003_SUSPENDED_FILTER
R004_PRICE_LIMIT_FILTER
R005_MISSING_PRICE_FILTER
R006_LOT_SIZE_CHECK
R007_INDUSTRY_MAX_WEIGHT
R009_MARKET_RISK_SWITCH
R011_LIQUIDITY_FILTER
```

## 4. 已完成链路

```text
strategy_signal
→ target_position 原始目标仓位
→ risk_profile / risk_rule
→ risk_decision
→ adjusted target_position
→ trading rebalance
→ paper fill
→ position
→ portfolio snapshot
```

## 5. 核心验收项

### 5.1 风控层与策略层边界清晰

已满足：

```text
不修改 strategy_signal
不在策略层内嵌平台级风控
不修改原始 target_position run
风控层生成 adjusted target run
交易域消费风控后的 target run
```

### 5.2 同一 Signal 在不同风险配置下得到不同目标仓位

已满足：

```text
source_target_run_id = 155

default profile:
adjusted_target_run_id = 160
target_quantity_total = 605400

conservative profile:
adjusted_target_run_id = 161
target_quantity_total = 547400
adjust_count = 30

data strict profile:
adjusted_target_run_id = 162
target_quantity_total = 0
reject_count = 30
```

Profile compare：

```text
overall_status = PASS
different_target_quantity_totals = true
has_reject_or_adjust_profile = true
```

### 5.3 风险拒绝 / 降权 / 调整有统一记录

已满足：

```text
risk_decision 统一记录 PASS / WARN / REJECT / ADJUST
conservative profile adjust_count = 30
data strict profile reject_count = 30
risk3 conservative adjust_count = 30
risk3 strict reject_count = 30
```

### 5.4 风控后目标仓位可被交易域消费

已满足：

```text
target_position_run_id = 160
day_count = 2
success_count = 2
failed_count = 0
final_position_run_id = 153
final_snapshot_run_id = 154
status = SUCCESS
```

## 6. 关键 Run

```text
M7.7 source target:
target_position_run_id = 155

M7-Risk.1 default:
risk_run_id = 159
adjusted_target_run_id = 160

M7-Risk.2 conservative:
risk_run_id = 162
adjusted_target_run_id = 161

M7-Risk.2 data strict:
risk_run_id = 163
adjusted_target_run_id = 162

M7-Risk.3 conservative:
risk_run_id = 164
adjusted_target_run_id = 165

M7-Risk.3 strict:
risk_run_id = 167
adjusted_target_run_id = 166

Trading final:
order_run_id = 146 / 151
fill_run_id = 147 / 152
position_run_id = 148 / 153
snapshot_run_id = 149 / 154
```

## 7. 风控执行顺序

M7-Risk.1/2：

```text
10  R001_MAX_POSITION_COUNT
20  R002_MAX_SINGLE_POSITION_WEIGHT
30  R003_SUSPENDED_FILTER
40  R004_PRICE_LIMIT_FILTER
50  R005_MISSING_PRICE_FILTER
60  R006_LOT_SIZE_CHECK
```

M7-Risk.3：

```text
70   R007_INDUSTRY_MAX_WEIGHT
90   R009_MARKET_RISK_SWITCH
110  R011_LIQUIDITY_FILTER
```

## 8. 当前数据缺口

已发现但不阻塞：

```text
缺少目标池 effective_date price
缺少 instrument_status
缺少 price_limit
缺少 industry classification
```

M7 风控域的处理方式：

```text
default / observe / conservative profile：WARN 或 ADJUST
strict profile：REJECT
所有结果统一进入 risk_decision
```

## 9. 后续建议

M7 风控域已可收口。后续建议进入：

```text
M8.1 Run Monitor + CLI 运维入口
```

M8 应提供：

```text
risk profile 查询
risk decision 查询
adjusted target 查询
paper chain 查询
portfolio snapshot 查询
风险报告导出
```
