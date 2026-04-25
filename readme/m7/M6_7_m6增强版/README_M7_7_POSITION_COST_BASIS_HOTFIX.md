# M7.7 Position Cost Basis Hotfix

## Problem

After M7.7 target quantity sizing and order price fallback, the multi-day chain reached snapshot valuation, but failed because newly bought positions had zero cost/price fields:

- avg_cost = 0
- cost_amount = 0
- market_price = 0
- market_value = 0

The root cause is in `PaperPositionApplyFillService._apply_buy`: new positions are created from fill rows, and the previous logic only used `_set_if_exists(...)` for cost fields. Since a fill row does not naturally contain `avg_cost`, `cost_amount`, `market_price`, etc., the final position insert payload used required defaults, which were zeros.

## Fix

The patch materializes cost and valuation fields in the working position row for BUY fills:

- avg_cost / cost_price / average_cost
- cost_amount / total_cost
- market_price / last_price / close_price / price
- market_value
- unrealized_pnl
- total_pnl

This does not change database schema.

## Apply

```powershell
python tools/apply_m7_7_position_cost_basis_hotfix.py
```

Then clean and rerun:

```powershell
$env:DATABASE_URL="postgresql+psycopg://stock:stock@127.0.0.1:54322/stock_quant_v2"
python tools/cleanup_m7_6_rerun_artifacts.py

$env:M7_CHAIN_PREVIOUS_OUTPUTS="true"
$env:M7_STOP_ON_ERROR="true"
$env:M7_REPLACE_EXISTING="false"
$env:M7_DAILY_PLANS_FILE="tmp/m7_6_daily_plans.json"

python -m stock_quant_v2.scripts.bootstrap_m7_paper_trading_multiday_chain
```
