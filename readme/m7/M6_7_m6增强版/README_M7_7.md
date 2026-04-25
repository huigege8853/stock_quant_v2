# M7.7 Real Target Quantity Sizing

目标：摆脱 `TEMPLATE_ORDER`，在 `trading_paper_target_position` 内直接生成真实 `target_quantity`。

## 修改内容

- `SignalToTargetService.build_equal_weight_targets()` 不再只写 `target_weight`。
- 新增基于资金、权重、价格、A 股 100 股手数的 sizing：
  - `target_amount = floor_to_lot(deployable_capital * target_weight / sizing_price) * sizing_price`
  - `target_quantity = floor_to_lot(deployable_capital * target_weight / sizing_price, 100)`
- 默认价格使用 `as_of_date` 的 `core_daily_bar.close_price`，如果没有当天价格，则取 `<= as_of_date` 的最近收盘价，避免使用未来价格。
- 默认 capital 优先取 portfolio 最新 snapshot 的 `total_equity`，否则使用 portfolio.initial_cash。
- 不修改 `strategy_signal`。
- 不新增表和迁移。

## 运行 target quantity 生成

```powershell
$env:M7_PORTFOLIO_ID="1"
$env:M7_SOURCE_SIGNAL_RUN_ID="81"
$env:M7_SOURCE_SCREEN_REQUEST_ID="3"
$env:M7_AS_OF_DATE="2026-04-21"
$env:M7_EFFECTIVE_DATE="2026-04-22"
$env:M7_TARGET_PRICE_DATE="2026-04-21"
$env:M7_TARGET_COUNT="30"
$env:M7_TARGET_LOT_SIZE="100"
$env:M7_TARGET_CASH_BUFFER_RATE="0.02"
$env:M7_TARGET_SIZING_MODE="EQUAL_WEIGHT_BY_EQUITY"

python -m stock_quant_v2.scripts.bootstrap_m7_target_quantity_chain
```

输出里的 `target_position_run_id` 用于后续 M7 rebalance。

## 验收

```powershell
psql $env:DATABASE_URL
```

```sql
\set target_position_run_id <输出的 target_position_run_id>
\set portfolio_id 1
\i sql/m7_7_target_quantity_acceptance.sql
```

期望：

- `target_quantity_not_null_check = true`
- `positive_target_quantity_check = true`
- `lot_size_100_check = true`
- `target_amount_positive_check = true`

## 用真实 target_position 跑 M7.6 rebalance

把 `tmp/m7_6_daily_plans.json` 中第一天的：

```json
"target_position_run_id": 111,
"template_order_run_id": 126,
"target_quantity_source": "TEMPLATE_ORDER"
```

改为：

```json
"target_position_run_id": <新的 target_position_run_id>,
"target_quantity_source": "TARGET_POSITION"
```

并删除 `template_order_run_id`，或保留但不会被使用。

然后按 M7.6 清理旧 run 后重新跑：

```powershell
python tools/cleanup_m7_6_rerun_artifacts.py

$env:M7_CHAIN_PREVIOUS_OUTPUTS="true"
$env:M7_STOP_ON_ERROR="true"
$env:M7_REPLACE_EXISTING="false"
$env:M7_DAILY_PLANS_FILE="tmp/m7_6_daily_plans.json"
python -m stock_quant_v2.scripts.bootstrap_m7_paper_trading_multiday_chain
```
