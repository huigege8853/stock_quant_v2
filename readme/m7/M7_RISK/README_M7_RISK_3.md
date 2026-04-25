# M7-Risk.3 Industry Exposure / Market Switch / Liquidity

## 1. Seed profiles

```powershell
python -m stock_quant_v2.scripts.bootstrap_m7_risk3_profiles
```

## 2. Apply conservative Risk3 overlay

Recommended source target run is the M7-Risk.1 default adjusted run:

```text
source_target_run_id = 160
```

Run:

```powershell
$env:M7_PORTFOLIO_ID="1"
$env:M7_RISK3_SOURCE_TARGET_RUN_ID="160"
$env:M7_RISK3_PROFILE_CODE="paper_cn_a_risk3_conservative_v1"
$env:M7_RISK3_CURRENT_POSITION_RUN_ID="143"
$env:M7_RISK3_AS_OF_DATE="2026-04-21"
$env:M7_RISK3_EFFECTIVE_DATE="2026-04-22"
$env:M7_RISK3_REPLACE_EXISTING="false"

python -m stock_quant_v2.scripts.bootstrap_m7_apply_risk3_to_target
```

Record the output `adjusted_target_run_id`.

## 3. Quality check

```powershell
$env:M7_PORTFOLIO_ID="1"
$env:M7_RISK3_SOURCE_TARGET_RUN_ID="160"
$env:M7_RISK3_ADJUSTED_TARGET_RUN_ID="<adjusted_target_run_id>"

python -m stock_quant_v2.scripts.check_m7_risk3_quality
```

Expected:

```text
overall_status = PASS
has_risk3_reason = true
has_warn_or_adjust_or_reject = true
```

## 4. Optional strict profile

```powershell
$env:M7_RISK3_PROFILE_CODE="paper_cn_a_risk3_strict_v1"
$env:M7_RISK3_REPLACE_EXISTING="false"

python -m stock_quant_v2.scripts.bootstrap_m7_apply_risk3_to_target
```

Strict profile may reject targets if industry / liquidity data is incomplete.

## 5. Trading integration

Replace target_position_run_id in `tmp/m7_6_daily_plans.json` with the new M7-Risk.3 adjusted target run id and rerun paper trading.
