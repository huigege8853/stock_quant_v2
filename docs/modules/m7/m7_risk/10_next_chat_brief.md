# M7-Risk Final Next Chat Brief

项目名称：stock_quant_v2

当前阶段：M7 风控域已完成。

## 1. 当前结论

```text
M7-Risk.1 Unified Risk Decision Layer：PASS
M7-Risk.2 Profile Variants：PASS
M7-Risk.3 Exposure / Market Switch / Liquidity：PASS

M7 风控域：PASS
```

## 2. 当前已完成

```text
risk_rule
risk_profile
risk_profile_rule
risk_decision

R001 最大持仓数
R002 单票最大权重
R003 停牌过滤
R004 涨跌停过滤
R005 缺价检查
R006 手数检查
R007 行业最大权重
R009 市场风险开关
R011 流动性约束
```

## 3. 关键验收 Run

```text
source target:
target_position_run_id = 155

default risk:
risk_run_id = 159
adjusted_target_run_id = 160

conservative risk:
risk_run_id = 162
adjusted_target_run_id = 161

data strict risk:
risk_run_id = 163
adjusted_target_run_id = 162

risk3 conservative:
risk_run_id = 164
adjusted_target_run_id = 165

risk3 strict:
risk_run_id = 167
adjusted_target_run_id = 166
```

## 4. 交易域最终联通

交易域消费：

```text
target_position_run_id = 160
```

最终结果：

```text
day_count = 2
success_count = 2
failed_count = 0
final_position_run_id = 153
final_snapshot_run_id = 154
status = SUCCESS
```

## 5. 下一阶段建议

进入 M8.1：

```text
Run Monitor + CLI 运维入口
```

先做 CLI，不急着做 FastAPI。

M8.1 建议产出：

```text
m8_query_run
m8_query_paper_chain
m8_query_portfolio_snapshot
m8_query_risk_profile
m8_query_risk_decision
m8_export_risk_report
```

## 6. 新聊天开场建议

```text
项目名称：stock_quant_v2

当前阶段：准备进入 M8.1 Run Monitor + CLI 运维入口。

已完成：
M7 Paper Trading Multi-Day & Rebalance
M7.7 Target Quantity Sizing
M7-Risk.1 Unified Risk Decision Layer
M7-Risk.2 Profile Variants
M7-Risk.3 Exposure / Market Switch / Liquidity

M7 风控域最终状态：PASS。

本轮目标：
建立 M8.1 运维查询层，先做 CLI 查询 run、paper chain、portfolio snapshot、risk profile、risk decision 和报告导出。
```
