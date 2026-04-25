# M7-Risk Handoff to M8

项目名称：stock_quant_v2  
当前状态：M7-Risk 最小闭环完成，可进入 M8。

## 1. M7-Risk 交付状态

```text
M7-Risk.1 Unified Risk Decision Layer：PASS
M7-Risk.2 Profile Variants：PASS
M7 风控域最小闭环：PASS
```

## 2. M8 应继承的对象

M8 查询 / 运维需要接入：

```text
risk_rule
risk_profile
risk_profile_rule
risk_decision
trading_paper_target_position
trading_paper_order
trading_paper_fill
trading_paper_position
trading_paper_portfolio_snapshot
ops_run
```

## 3. M8 应支持的风控查询

建议 CLI / API：

```text
m8_query_risk_profile
m8_query_risk_decision
m8_query_adjusted_target
m8_compare_risk_profiles
m8_export_risk_report
```

## 4. 推荐 M8.1 CLI

### 4.1 查询 profile

```powershell
$env:M8_RISK_PROFILE_CODE="paper_cn_a_default_risk_v1"
python -m stock_quant_v2.scripts.m8_query_risk_profile
```

### 4.2 查询 risk decision

```powershell
$env:M8_RISK_SOURCE_TARGET_RUN_ID="155"
$env:M8_RISK_ADJUSTED_TARGET_RUN_ID="160"
python -m stock_quant_v2.scripts.m8_query_risk_decision
```

### 4.3 对比 profile

```powershell
$env:M8_RISK_SOURCE_TARGET_RUN_ID="155"
$env:M8_RISK_COMPARE_ADJUSTED_RUN_IDS="160,161,162"
python -m stock_quant_v2.scripts.m8_compare_risk_profiles
```

## 5. M8 run monitor 应展示

```text
risk_run_id
source_target_run_id
adjusted_target_run_id
risk_profile_code
decision_count
pass_count
warn_count
reject_count
adjust_count
source_target_quantity_total
adjusted_target_quantity_total
```

## 6. 当前重要 run

```text
source_target_run_id = 155

default:
risk_run_id = 159
adjusted_target_run_id = 160

conservative:
risk_run_id = 162
adjusted_target_run_id = 161

data strict:
risk_run_id = 163
adjusted_target_run_id = 162

paper trading:
order_run_id = 146 / 151
fill_run_id = 147 / 152
position_run_id = 148 / 153
snapshot_run_id = 149 / 154
```

## 7. M8 前置建议

进入 M8 前建议先提交 Git：

```powershell
git status
git add alembic/versions src/stock_quant_v2/db/models src/stock_quant_v2/risk_domain src/stock_quant_v2/scripts sql docs/modules/m7_risk
git commit -m "complete M7 risk domain minimum closed loop"
```
