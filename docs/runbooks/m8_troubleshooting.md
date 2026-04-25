# M8 Troubleshooting

项目名称：stock_quant_v2  
模块：M8 CLI / Report Export

## 1. AmbiguousParameter

### 现象

```text
psycopg.errors.AmbiguousParameter: could not determine data type of parameter
原因

PostgreSQL 对以下写法无法判断参数类型：

(:xxx is null or column = :xxx)
修复

给参数加显式 cast：

cast(:xxx as bigint) is null
or column = cast(:xxx as bigint)

日期：

cast(:snapshot_date as date) is null
or snapshot_date = cast(:snapshot_date as date)

文本：

cast(:profile_code as text) is null
or profile_code = cast(:profile_code as text)
2. Paper Chain order/fill 为 0
现象
target_exists = true
position_exists = true
snapshot_exists = true
order_exists = false
fill_exists = false
常见原因

手动填错 M8_ORDER_RUN_ID / M8_FILL_RUN_ID，不是同一条交易链。

处理

先跑：

python -m stock_quant_v2.scripts.m8_query_latest_runs

复制输出的：

powershell_env.trading_chain

再跑：

python -m stock_quant_v2.scripts.m8_query_paper_chain
3. Risk Decision 查不到
现象
decision_exists = false
常见原因

M8_SOURCE_TARGET_RUN_ID、M8_ADJUSTED_TARGET_RUN_ID、M8_RISK_RUN_ID 不匹配。

处理

先跑：

python -m stock_quant_v2.scripts.m8_query_latest_runs

复制输出的：

powershell_env.risk_chain
4. Target Diff 查不到
现象
source_target_exists = true
adjusted_target_exists = false
risk_decision_exists = false
常见原因

adjusted target run id 填错，或者不是同一个 risk run 生成。

处理

确认：

risk_decision.source_target_run_id
risk_decision.adjusted_target_run_id
risk_decision.run_id

三者匹配。

5. 导出文件为空
现象

CSV 文件存在但为空。

常见原因

对应 run id 下没有明细行。

处理

先跑对应 query 脚本确认：

python -m stock_quant_v2.scripts.m8_query_paper_chain
python -m stock_quant_v2.scripts.m8_query_risk_decision
python -m stock_quant_v2.scripts.m8_query_portfolio_snapshot
6. 推荐排查顺序
1. m8_query_latest_runs
2. m8_query_paper_chain
3. m8_query_risk_decision
4. m8_query_target_diff
5. m8_export_daily_ops_report

---