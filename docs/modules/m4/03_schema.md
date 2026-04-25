# M4 ｜ 03_schema

## 本模块目标

M4 的核心职责，是把策略从“散落脚本”提升为平台级对象，并统一：

- 策略定义
- 策略版本
- 参数 schema
- signal contract

本轮不追求完成全部策略域，而是先以 `alpha_selection:v1` 跑通最小规则策略主链。

---

## 一、核心表总览

本轮 M4 落地以下 4 张核心表：

1. `strategy_definition`
2. `strategy_version`
3. `strategy_parameter_schema`
4. `strategy_signal`

它们分别负责：

- `strategy_definition`：策略稳定身份
- `strategy_version`：策略可执行版本
- `strategy_parameter_schema`：参数结构与校验约束
- `strategy_signal`：统一输出契约

---

## 二、strategy_definition

### 表职责
表示“这是什么策略”，而不是“这一版怎么实现”。

### 主要字段

- `id`
- `strategy_code`
- `strategy_name`
- `strategy_type`
- `engine_type`
- `market_scope`
- `bar_frequency`
- `description`
- `lifecycle_status`
- `owner`
- `tags_json`
- `created_at`
- `updated_at`

### 当前约束

- 主键：`pk_sd`
- 唯一键：`uq_sd__code`
- 索引：`ix_sd__type_status`

### 当前首条样本

- `strategy_code = alpha_selection`
- `strategy_name = Alpha Selection`
- `strategy_type = selection`
- `engine_type = rule`
- `market_scope = CN_A`
- `bar_frequency = 1d`

---

## 三、strategy_version

### 表职责
表示某一条策略的某一个“可执行、可复现、可追踪”的版本快照。

### 主要字段

- `id`
- `strategy_definition_id`
- `version_code`
- `version_no`
- `is_current`
- `lifecycle_status`
- `implementation_ref`
- `dependency_spec_json`
- `output_contract_version`
- `default_parameter_values_json`
- `logic_hash`
- `effective_from`
- `retired_at`
- `description`
- `created_at`
- `updated_at`

### 当前约束

- 主键：`pk_sv`
- 外键：`fk_sv__def_id` → `strategy_definition.id`
- 唯一键：
  - `uq_sv__def_ver_code`
  - `uq_sv__def_ver_no`
- 索引：
  - `ix_sv__def_current`
  - `ix_sv__status`

### 当前首条样本

- strategy: `alpha_selection`
- version: `v1`
- output contract: `signal_v1`

### dependency_spec_json 当前示例语义

```json
{
  "market_scope": "CN_A",
  "bar_frequency": "1d",
  "price_basis": "adj_strict",
  "signal_effective_lag_trading_days": 1,
  "feature_set": {
    "code": "fs_daily_alpha_v1",
    "version": "v1"
  },
  "required_features": [
    "feat_mom_20",
    "feat_trend_strength_20",
    "feat_volatility_rank_20",
    "feat_tradability_score",
    "feat_tradable_flag"
  ],
  "forbidden_inputs": ["label_*"]
}