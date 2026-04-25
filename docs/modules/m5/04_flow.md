
---

# 4. `docs/modules/m5/04_flow.md`

```markdown
# M5｜Flow

## 1. M5 总体最小闭环

```text
M4 strategy_signal
→ M5 screen_request
→ M5 screen_result
→ ops_run_metric_snapshot(screen)
→ M5 backtest_request
→ M5 backtest_result skeleton
→ Backtrader execution plan
→ ops_run_artifact
→ ops_run_metric_snapshot(backtest)