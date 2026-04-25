# M7-Risk Acceptance

项目名称：stock_quant_v2  
模块：M7-Risk 统一风控域  
状态：PASS

## 1. 验收结论

M7-Risk 已完成最小风控闭环，并通过 profile variant 验收。

```text
M7-Risk.1 Unified Risk Decision Layer：PASS
M7-Risk.2 Profile Variants：PASS
M7 风控域最小闭环：PASS
```

## 2. 已完成能力

M7-Risk 已落地以下对象：

```text
risk_rule
risk_profile
risk_profile_rule
risk_decision
```

M7-Risk 已完成以下链路：

```text
原始 target_position_run_id
→ risk_profile / risk_rule
→ risk_decision
→ adjusted target_position_run_id
→ trading rebalance 消费风控后 target run
→ paper trading chain SUCCESS
```

## 3. M7-Risk.1 最终验收

原始 target run：

```text
source_target_run_id = 155
```

默认风控 profile：

```text
risk_profile_code = paper_cn_a_default_risk_v1
risk_run_id = 159
adjusted_target_run_id = 160
portfolio_id = 1
```

风控结果：

```text
source_target_count = 30
adjusted_target_count = 30
decision_count = 180
pass_count = 90
warn_count = 90
reject_count = 0
adjust_count = 0

source_target_quantity_total = 605400.00000000
adjusted_target_quantity_total = 605400.00000000
status = SUCCESS
```

质量检查：

```text
source_target_exists = true
adjusted_target_exists = true
decision_exists = true
same_target_row_count = true
has_reject_or_adjust_or_warn = true
overall_status = PASS
```

## 4. M7-Risk.1 交易域联通验收

交易域已消费风控后的：

```text
target_position_run_id = 160
```

多日 paper trading 链路结果：

```text
day_count = 2
success_count = 2
failed_count = 0
final_position_run_id = 153
final_snapshot_run_id = 154
status = SUCCESS
```

Day 1：

```text
buy_order_count = 10
sell_order_count = 18
hold_count = 2
inserted_order_count = 28

new_quantity_total = 605400.00000000
new_available_quantity_total = 456800.00000000

cash_balance = 237814.13334439
market_value = 9794717.00000000
total_equity = 10032531.13334439
realized_pnl = 5077.52739750
```

Day 2：

```text
buy_order_count = 0
sell_order_count = 0
hold_count = 30

new_quantity_total = 605400.00000000
new_available_quantity_total = 605400.00000000
realized_pnl = 5077.52739750
```

## 5. M7-Risk.2 Profile Variants 验收

同一个原始 target run：

```text
source_target_run_id = 155
portfolio_id = 1
```

三个风险配置结果：

### 5.1 Default profile

```text
profile_code = paper_cn_a_default_risk_v1
adjusted_target_run_id = 160

target_count = 30
target_quantity_total = 605400.00000000
target_amount_total = 9794717.00000000
rejected_target_count = 0
adjusted_target_count = 0
passed_target_count = 30

decision_count = 180
pass_count = 90
warn_count = 90
reject_count = 0
adjust_count = 0
```

### 5.2 Conservative profile

```text
profile_code = paper_cn_a_conservative_risk_v1
adjusted_target_run_id = 161

target_count = 30
target_quantity_total = 547400.00000000
target_amount_total = 8769914.00000000
rejected_target_count = 0
adjusted_target_count = 30
passed_target_count = 0

decision_count = 180
pass_count = 60
warn_count = 90
reject_count = 0
adjust_count = 30
```

### 5.3 Data strict profile

```text
profile_code = paper_cn_a_data_strict_risk_v1
adjusted_target_run_id = 162

target_count = 30
target_quantity_total = 0E-8
target_amount_total = 0E-8
rejected_target_count = 30
adjusted_target_count = 0
passed_target_count = 0

decision_count = 180
pass_count = 90
warn_count = 60
reject_count = 30
adjust_count = 0
```

Profile compare 结果：

```text
has_multiple_profiles = true
all_have_targets = true
all_have_decisions = true
different_target_quantity_totals = true
has_reject_or_adjust_profile = true
overall_status = PASS
```

## 6. 已满足 PRD 验收项

### 6.1 风控层与策略层边界清晰

已满足：

```text
不修改 strategy_signal
不修改原始 target_position_run_id = 155
风控层生成 adjusted_target_run_id
交易域消费风控后的 target run
```

### 6.2 同一 Signal 在不同风险配置下可得到不同目标仓位

已满足：

```text
default:      target_quantity_total = 605400
conservative: target_quantity_total = 547400
data strict: target_quantity_total = 0
```

### 6.3 风险拒绝 / 降权 / 调整有统一记录

已满足：

```text
risk_decision decision_count = 180 per profile
conservative profile adjust_count = 30
data strict profile reject_count = 30
default profile warn_count = 90
```

## 7. 当前风险规则字典

```text
R001_MAX_POSITION_COUNT
最大持仓数

R002_MAX_SINGLE_POSITION_WEIGHT
单票最大权重

R003_SUSPENDED_FILTER
停牌过滤

R004_PRICE_LIMIT_FILTER
涨停不买 / 跌停不卖

R005_MISSING_PRICE_FILTER
缺价检查

R006_LOT_SIZE_CHECK
A 股 100 股手数复核
```

## 8. 风险执行顺序

默认执行顺序：

```text
10  R001_MAX_POSITION_COUNT
20  R002_MAX_SINGLE_POSITION_WEIGHT
30  R003_SUSPENDED_FILTER
40  R004_PRICE_LIMIT_FILTER
50  R005_MISSING_PRICE_FILTER
60  R006_LOT_SIZE_CHECK
```

## 9. 风控原因码

本轮已出现：

```text
R001_MAX_POSITION_COUNT
R002_MAX_SINGLE_POSITION_WEIGHT
R003_MISSING_STATUS
R004_MISSING_PRICE_LIMIT
R005_MISSING_EFFECTIVE_PRICE
R006_LOT_SIZE_CHECK
```

## 10. Open Items

不阻塞 M7-Risk 当前验收，但建议后续增强：

```text
行业暴露约束
市场风险开关
最大换手率
流动性过滤
ST 过滤
更完整的停牌 / 涨跌停数据接入
风控结果写入 ops_run_metric_snapshot
risk_decision 报表导出
```
