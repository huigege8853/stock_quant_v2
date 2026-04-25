
---

# 3) `docs/modules/m4/08_open_items.md`

```markdown id="esq45j"
# M4 ｜ 08_open_items

## 当前阶段说明

M4 最小可用规则策略主链已经跑通，但 M4 还没有完全收尾。  
以下事项当前不阻塞首链成立，但应在进入 M5 前尽量明确。

---

## O1. feat_tradable_flag 语义未最终锁定

### 当前状态
`alpha_selection:v1` 主链已跑通，但 `feat_tradable_flag` 的当前数值语义尚未完全收口。

### 当前处理
- 当前默认参数：`require_tradable_flag = false`
- 不让该字段阻塞 M4 首链

### 后续动作
1. 回到 M3 / definition 层，锁定：
   - `1` 是否表示可交易
   - `0` 是否表示不可交易
2. 明确是否需要修复 M3 输出定义

---

## O2. timing 策略上游状态源未锁定

### 当前状态
timing skeleton 已形成，但当前未绑定具体数据表或 snapshot。

### 待定问题
- 是否以 `market_breadth` 为主
- 是否引入 `market_index` 或市场状态快照
- 是否单独构建 `market_state_snapshot`

### 当前建议
先不为 timing 猜具体表，先锁 signal contract。

---

## O3. strategy_instance 是否在 M5 升格

### 当前状态
M4 第一轮没有引入 `strategy_instance`。

### 待定问题
M5 在做：
- screen
- parameter_search
- walk-forward

时，是否需要把某次“strategy + version + parameter profile”的组合升格为独立对象。

### 当前建议
等 M5 真正进入 orchestration 再决定，不提前抽象。

---

## O4. selection / timing 的 reason_code 字典仍需扩展

### 当前已用
- `TOP_N_SELECTED`

### 应补内容
- `BELOW_MIN_SCORE`
- `FEATURE_MISSING`
- `NOT_TRADABLE`
- `MARKET_RISK_ON`
- `MARKET_RISK_OFF`

---

## O5. M5 对 signal 的消费路径仍需正式文档化

### 当前状态
已确定 M5 必须消费统一 signal contract，但尚未形成完整消费说明。

### 建议
在 M5 开始前，先锁定：
- screen request / result contract
- backtest request / result contract
- execution assumption contract

---

## O6. 当前 bootstrap 脚本仍可继续收薄

### 当前状态
M4 逻辑已开始下沉到 `strategy_domain`，但 orchestration 脚本仍保留部分运行组织逻辑。

### 当前建议
这是正常阶段性状态，不阻塞后续推进。
等 M5 run orchestration 设计明确后，再统一整理。