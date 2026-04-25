# M8.5 Windows Task Scheduler Template

Task name:

stock_quant_v2_m8_daily_ops

Schedule time:

18:30

Generated files:

artifacts\m8\scheduler\stock_quant_v2_m8_daily_ops.ps1
artifacts\m8\scheduler\stock_quant_v2_m8_daily_ops.xml

## 1. Manual test first

Run:

powershell -NoProfile -ExecutionPolicy Bypass -File "artifacts\m8\scheduler\stock_quant_v2_m8_daily_ops.ps1"

Expected:

M8.5 daily ops entrypoint completed.

## 2. Register task manually

The generated XML is disabled by default. Register manually only after the manual test passes.

schtasks /Create /TN "stock_quant_v2_m8_daily_ops" /XML "artifacts\m8\scheduler\stock_quant_v2_m8_daily_ops.xml"

## 3. Enable manually in Task Scheduler

Open Windows Task Scheduler, inspect the task, then enable it manually.

## 4. Current boundary

This task only runs:

python -m stock_quant_v2.scripts.m8_daily_ops_entrypoint

It does not trigger trading, risk application, stale cleanup, or live orders.
