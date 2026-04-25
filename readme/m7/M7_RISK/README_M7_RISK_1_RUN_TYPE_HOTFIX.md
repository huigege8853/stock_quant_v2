# M7-Risk.1 run_type hotfix

## Problem

`ops_run.run_type` is `varchar(32)`, but the initial M7-Risk.1 patch used:

```text
PAPER_TARGET_POSITION_RISK_ADJUSTED
```

This is too long and causes:

```text
value too long for type character varying(32)
```

## Fix

Replace it with:

```text
RISK_ADJ_TARGET
```

## Usage

```powershell
python tools/apply_m7_risk_1_run_type_hotfix.py
```

Then rerun:

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
