# M7.6 cleanup param hotfix

This replaces `tools/cleanup_m7_6_rerun_artifacts.py`.

Fixes:
- Missing `portfolio_ids` bind parameter.
- Handles `.env` with inline comments.
- Supports `V2_SQLALCHEMY_URL`.
- Reads `tmp/m7_6_daily_plans.json` by default or `M7_DAILY_PLANS_FILE`.
- Deletes in FK-safe order: ledger → snapshots → positions → fills → orders.

Run:

```powershell
$env:DATABASE_URL="postgresql+psycopg://stock:stock@127.0.0.1:54322/stock_quant_v2"
python tools/cleanup_m7_6_rerun_artifacts.py
```

Then rerun M7.6 with `M7_REPLACE_EXISTING=false`.
