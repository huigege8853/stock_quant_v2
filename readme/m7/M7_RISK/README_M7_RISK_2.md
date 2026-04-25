# M7-Risk.2 Profile Variants

目标：验证“同一批 target_position 在不同 risk_profile 下产生不同风控后目标仓位”。

## 1. 初始化 profile variants

```powershell
python -m stock_quant_v2.scripts.bootstrap_m7_risk_profile_variants
```

会创建 / 更新：

```text
paper_cn_a_default_risk_v1
paper_cn_a_conservative_risk_v1
paper_cn_a_data_strict_risk_v1
```

## 2. 对同一个 source target run 分别执行风控

原始 target run：

```text
source_target_run_id = 155
```

### default profile

```powershell
$env:M7_PORTFOLIO_ID="1"
$env:M7_RISK_SOURCE_TARGET_RUN_ID="155"
$env:M7_RISK_PROFILE_CODE="paper_cn_a_default_risk_v1"
$env:M7_RISK_CURRENT_POSITION_RUN_ID="143"
$env:M7_RISK_AS_OF_DATE="2026-04-21"
$env:M7_RISK_EFFECTIVE_DATE="2026-04-22"
$env:M7_RISK_ADJUSTED_TARGET_RUN_ID="160"
$env:M7_RISK_REPLACE_EXISTING="true"

python -m stock_quant_v2.scripts.bootstrap_m7_apply_risk_to_target
```

### conservative profile

```powershell
$env:M7_RISK_PROFILE_CODE="paper_cn_a_conservative_risk_v1"
$env:M7_RISK_ADJUSTED_TARGET_RUN_ID="161"
$env:M7_RISK_REPLACE_EXISTING="true"

python -m stock_quant_v2.scripts.bootstrap_m7_apply_risk_to_target
```

Expected: R002 max single weight triggers ADJUST. Target quantity total should decrease.

### data strict profile

```powershell
$env:M7_RISK_PROFILE_CODE="paper_cn_a_data_strict_risk_v1"
$env:M7_RISK_ADJUSTED_TARGET_RUN_ID="162"
$env:M7_RISK_REPLACE_EXISTING="true"

python -m stock_quant_v2.scripts.bootstrap_m7_apply_risk_to_target
```

Expected: R005 missing effective price triggers REJECT for current data gap. Target quantity total may go to 0.

## 3. Compare profiles

```powershell
$env:M7_PORTFOLIO_ID="1"
$env:M7_RISK_SOURCE_TARGET_RUN_ID="155"
$env:M7_RISK_COMPARE_ADJUSTED_RUN_IDS="160,161,162"

python -m stock_quant_v2.scripts.check_m7_risk_profile_compare
```

Expected:

```text
overall_status = PASS
different_target_quantity_totals = true
has_reject_or_adjust_profile = true
```

This satisfies the PRD requirement:
“同一条 Signal 在不同风险配置下可得到不同目标仓位。”
