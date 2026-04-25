
---

# 2) `docs/modules/m4/05_api_or_contract.md`

```markdown id="9w5v2y"
# M4 ｜ 05_api_or_contract

## 本模块契约目标

M4 的核心不是提供 HTTP API，而是先定义平台内部的稳定契约。

当前优先定义 4 类契约：

1. strategy definition contract
2. strategy version contract
3. parameter schema contract
4. signal contract

这些契约后续将被：

- M5 screen
- M5 backtest
- M6 paper trading
- M7 risk

共同消费。

---

## 一、Strategy Definition Contract

### 语义
表示“这条策略是什么”。

### 最小字段

- `strategy_code`
- `strategy_name`
- `strategy_type`
- `engine_type`
- `market_scope`
- `bar_frequency`
- `lifecycle_status`

### 当前样例

```json
{
  "strategy_code": "alpha_selection",
  "strategy_name": "Alpha Selection",
  "strategy_type": "selection",
  "engine_type": "rule",
  "market_scope": "CN_A",
  "bar_frequency": "1d",
  "lifecycle_status": "active"
}