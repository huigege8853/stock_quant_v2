# M7.7-Fix-1 Price Fallback Hotfix

修复点：

- `core_daily_bar` 真实字段是 `open / close`，不是 `open_price / close_price`。
- `PaperRebalanceService` 在生成 BUY order 时，如果 target_position 行没有价格，自动从 `core_daily_bar` 取 `as_of_date` 或之前最近一个交易日的 `close/open` 作为 `estimated_price`。
- fill 阶段仍然优先使用 `effective_date NEXT_OPEN`；如果 NEXT_OPEN 缺失，则使用 order.estimated_price 作为 paper trading fallback。

执行：

```powershell
python tools/apply_m7_7_price_fallback_hotfix.py
python tools/cleanup_m7_6_rerun_artifacts.py
$env:M7_CHAIN_PREVIOUS_OUTPUTS="true"
$env:M7_STOP_ON_ERROR="true"
$env:M7_REPLACE_EXISTING="false"
$env:M7_DAILY_PLANS_FILE="tmp/m7_6_daily_plans.json"
python -m stock_quant_v2.scripts.bootstrap_m7_paper_trading_multiday_chain
```
