# M7-Risk.1 Patch

## 1. Apply migration

```powershell
python -m stock_quant_v2.scripts.db_upgrade
```

如果你的 db_upgrade 没有封装 alembic，可用：

```powershell
alembic upgrade head
```

## 2. Seed default risk profile

```powershell
$env:M7_RISK_PROFILE_CODE="paper_cn_a_default_risk_v1"
python -m stock_quant_v2.scripts.bootstrap_m7_risk_profile
```

## 3. Apply risk to target_position

假设 M7.7 原始 target run 是 155：

```powershell
$env:M7_PORTFOLIO_ID="1"
$env:M7_RISK_SOURCE_TARGET_RUN_ID="155"
$env:M7_RISK_PROFILE_CODE="paper_cn_a_default_risk_v1"
$env:M7_RISK_CURRENT_POSITION_RUN_ID="143"
$env:M7_RISK_AS_OF_DATE="2026-04-21"
$env:M7_RISK_EFFECTIVE_DATE="2026-04-22"
$env:M7_RISK_REPLACE_EXISTING="false"

python -m stock_quant_v2.scripts.bootstrap_m7_apply_risk_to_target
```

输出中的 `adjusted_target_run_id` 是交易域下一步应该消费的新 target run。

## 4. Quality check

```powershell
$env:M7_PORTFOLIO_ID="1"
$env:M7_RISK_SOURCE_TARGET_RUN_ID="155"
$env:M7_RISK_ADJUSTED_TARGET_RUN_ID="<上一步输出的 adjusted_target_run_id>"

python -m stock_quant_v2.scripts.check_m7_risk_quality
```

预期：

```text
overall_status = PASS
decision_exists = true
same_target_row_count = true
has_reject_or_adjust_or_warn = true
```

## 5. Rebalance consumes risk-adjusted target run

把 `tmp/m7_6_daily_plans.json` 里的：

```json
"target_position_run_id": 155
```

替换成：

```json
"target_position_run_id": <adjusted_target_run_id>
```

并保持：

```json
"target_quantity_source": "TARGET_POSITION"
```

然后清理旧产物并重跑 M7 paper chain。
