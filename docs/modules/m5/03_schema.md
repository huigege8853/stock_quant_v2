
---

# 3. `docs/modules/m5/03_schema.md`

```markdown
# M5｜Schema

## 1. Research Core Tables

### 1.1 research_execution_assumption_profile

用途：定义回测 / 模拟执行假设。

核心字段：

```text
id
profile_code
version_code
profile_name
market_code
asset_class
frequency
commission_model
commission_rate
min_commission
stamp_duty_rate
transfer_fee_rate
slippage_model
slippage_bps
price_fill_rule
volume_fill_rule
t_plus_rule
lot_size
allow_fractional_share
limit_up_down_rule
suspend_rule
cash_rule
assumption_payload
is_active
created_at
updated_at