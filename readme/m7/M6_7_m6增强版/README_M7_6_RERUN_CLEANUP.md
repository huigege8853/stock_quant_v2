# M7.6 Rerun Cleanup Hotfix

This fixes rerun cleanup order after a successful M7.6 run.

The failure occurs when rerunning with existing `trading_paper_order` rows while `trading_paper_fill` rows still reference those orders through `trading_paper_fill.order_id -> trading_paper_order.id`.

## Recommended one-time cleanup

```powershell
python tools/cleanup_m7_6_rerun_artifacts.py
```

Then rerun M7.6:

```powershell
$env:M7_CHAIN_PREVIOUS_OUTPUTS="true"
$env:M7_STOP_ON_ERROR="true"
$env:M7_REPLACE_EXISTING="false"
$env:M7_DAILY_PLANS_FILE="tmp/m7_6_daily_plans.json"
python -m stock_quant_v2.scripts.bootstrap_m7_paper_trading_multiday_chain
```

## Optional env overrides

```powershell
$env:M7_PORTFOLIO_ID="1"
$env:M7_CLEAN_CARRY_POSITION_RUN_IDS="145,150"
$env:M7_CLEAN_POSITION_RUN_IDS="148,153"
$env:M7_CLEAN_ORDER_RUN_IDS="146,151"
$env:M7_CLEAN_FILL_RUN_IDS="147,152"
$env:M7_CLEAN_SNAPSHOT_RUN_IDS="149,154"
```

## SQL alternative

```powershell
psql $env:DATABASE_URL
```

```sql
\set portfolio_id 1
\i sql/m7_6_cleanup_rerun_artifacts.sql
```
