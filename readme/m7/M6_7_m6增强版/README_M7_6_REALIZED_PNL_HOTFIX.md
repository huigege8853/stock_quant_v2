# M7.6 realized_pnl continuity hotfix

## Problem

M7.6 multiday chain is technically successful, but after a full-exit day the next day can have an empty position run. The previous implementation calculated `portfolio_snapshot.realized_pnl` only from current position rows. When there are no position rows, realized PnL resets to zero.

## Patch

Run from project root:

```powershell
python tools/apply_m7_6_realized_pnl_hotfix.py
```

This patches:

```text
src/stock_quant_v2/trading_domain/services/paper_portfolio_snapshot_m7_service.py
```

Rule added:

```text
If current position run has no open positions, no closed positions, and current position-level realized_pnl is 0,
then inherit previous_snapshot.realized_pnl.
Otherwise keep existing M7 behavior and use realized_pnl from current position run.
```

## Rerun

Because runs 145-154 already produced rows, either use new run ids or rerun with replace enabled:

```powershell
$env:M7_CHAIN_PREVIOUS_OUTPUTS="true"
$env:M7_STOP_ON_ERROR="true"
$env:M7_REPLACE_EXISTING="true"
$env:M7_DAILY_PLANS_FILE="tmp/m7_6_daily_plans.json"

python -m stock_quant_v2.scripts.bootstrap_m7_paper_trading_multiday_chain
```

Expected key change:

```text
snapshot_run_id=154.realized_pnl should inherit snapshot_run_id=149.realized_pnl instead of becoming 0E-8.
```

## Acceptance SQL

Copy `sql/m7_6_snapshot_realized_pnl_acceptance.sql` into your project and run:

```psql
\set first_snapshot_run_id 149
\set second_snapshot_run_id 154
\set portfolio_id 1
\i sql/m7_6_snapshot_realized_pnl_acceptance.sql
```

Expected:

```text
realized_pnl_carry_forward_check = true
```
