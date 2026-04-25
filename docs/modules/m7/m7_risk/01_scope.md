# M7-Risk Scope

M7-Risk 目标是在不破坏策略清晰度的前提下，建立平台统一风控与约束层。

## 边界

策略层不内嵌平台级风控。  
M7-Risk 不修改 strategy_signal。  
M7-Risk 不修改原始 target_position run。  
M7-Risk 生成新的 risk-adjusted target_position run。  
交易域必须消费风控后的 target_position run。

## M7-Risk.1 最小闭环

第一阶段覆盖：

- risk_rule
- risk_profile
- risk_profile_rule
- risk_decision
- target_position 风控过滤与调整
- 风控后 target_position run
- 风控原因码与决策记录

首批规则：

- R001_MAX_POSITION_COUNT
- R002_MAX_SINGLE_POSITION_WEIGHT
- R003_SUSPENDED_FILTER
- R004_PRICE_LIMIT_FILTER
- R005_MISSING_PRICE_FILTER
- R006_LOT_SIZE_CHECK
