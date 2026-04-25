# M7.6 Paper Trading Multi-Day & Rebalance Patch

## 目标

本补丁只补 M7.6 多日连续自动推进，不改表，不改 strategy_signal，不引入 M8 API/Scheduler。

链路：

```text
上一日 final position
→ carry current position / T+1 available_quantity
→ target diff 生成 BUY / SELL / HOLD order
→ NEXT_OPEN fill
→ position after fill / realized_pnl / cash_delta
→ portfolio snapshot
→ 下一日继续使用 position_run_id / snapshot_run_id 串联
```

## 需要替换 / 新增文件

```text
src/stock_quant_v2/trading_domain/services/paper_trading_orchestrator.py
src/stock_quant_v2/trading_domain/services/paper_multiday_orchestrator.py
src/stock_quant_v2/trading_domain/tasks/run_paper_trading_daily.py
src/stock_quant_v2/trading_domain/tasks/run_paper_trading_date_range.py
src/stock_quant_v2/scripts/bootstrap_m7_paper_trading_daily_chain.py
src/stock_quant_v2/scripts/bootstrap_m7_paper_trading_multiday_chain.py
src/stock_quant_v2/scripts/bootstrap_m7_rebalance_daily_chain.py
sql/m7_6_multiday_acceptance.sql
```

## 注意

1. 这些脚本默认 run_id 已经存在于 `ops_run`，因为 trading 表有 FK 指向 `ops_run.id`。
2. 第一日必须提供 `source_position_run_id` 与 `previous_snapshot_run_id`。
3. 第二日开始，如果 `M7_CHAIN_PREVIOUS_OUTPUTS=true`，可以把 `source_position_run_id` 和 `previous_snapshot_run_id` 写成 `0`，系统会自动用上一日的 `position_run_id` / `snapshot_run_id` 串联。
4. 当前仍支持 `TEMPLATE_ORDER`，用于继续验证 M7.6；M7.7 再做真实 target quantity sizing。

## 单日运行示例

```powershell
$env:M7_PORTFOLIO_ID="1"
$env:M7_AS_OF_DATE="2026-04-21"
$env:M7_EFFECTIVE_DATE="2026-04-22"
$env:M7_SOURCE_POSITION_RUN_ID="143"
$env:M7_CARRY_POSITION_RUN_ID="145"
$env:M7_TARGET_POSITION_RUN_ID="111"
$env:M7_ORDER_RUN_ID="146"
$env:M7_FILL_RUN_ID="147"
$env:M7_POSITION_RUN_ID="148"
$env:M7_PREVIOUS_SNAPSHOT_RUN_ID="144"
$env:M7_SNAPSHOT_RUN_ID="149"
$env:M7_TEMPLATE_ORDER_RUN_ID="126"
$env:M7_TARGET_QUANTITY_SOURCE="TEMPLATE_ORDER"
$env:M7_REPLACE_EXISTING="false"

python -m stock_quant_v2.scripts.bootstrap_m7_paper_trading_daily_chain
```

## 多日运行示例

```powershell
$env:M7_CHAIN_PREVIOUS_OUTPUTS="true"
$env:M7_STOP_ON_ERROR="true"
$env:M7_REPLACE_EXISTING="false"
$env:M7_DAILY_PLANS_JSON=@'
[
  {
    "portfolio_id": 1,
    "as_of_date": "2026-04-21",
    "effective_date": "2026-04-22",
    "source_position_run_id": 143,
    "carry_position_run_id": 145,
    "target_position_run_id": 111,
    "order_run_id": 146,
    "fill_run_id": 147,
    "position_run_id": 148,
    "previous_snapshot_run_id": 144,
    "snapshot_run_id": 149,
    "template_order_run_id": 126,
    "target_quantity_source": "TEMPLATE_ORDER"
  },
  {
    "portfolio_id": 1,
    "as_of_date": "2026-04-22",
    "effective_date": "2026-04-23",
    "source_position_run_id": 0,
    "carry_position_run_id": 150,
    "target_position_run_id": 111,
    "order_run_id": 151,
    "fill_run_id": 152,
    "position_run_id": 153,
    "previous_snapshot_run_id": 0,
    "snapshot_run_id": 154,
    "template_order_run_id": 126,
    "target_quantity_source": "TEMPLATE_ORDER"
  }
]
'@

python -m stock_quant_v2.scripts.bootstrap_m7_paper_trading_multiday_chain
```

## 验收 SQL

```powershell
psql $env:DATABASE_URL
```

```sql
\set portfolio_id 1
\set final_position_run_id 153
\set final_snapshot_run_id 154
\i sql/m7_6_multiday_acceptance.sql
```
