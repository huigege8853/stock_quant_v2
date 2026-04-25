M8.8 Acceptance｜FastAPI API / OpenAPI 草案

项目名称：stock_quant_v2  
模块：M8.8 FastAPI API / OpenAPI 草案  
状态：PASS

## 1. 验收结论

M8.8 已完成 FastAPI API 第一版，并导出 OpenAPI 草案。

最终结论：

```text
M8.8 FastAPI API / OpenAPI 草案：PASS
2. 当前边界

M8.8 当前只做只读查询和安全导出。

当前支持：

Run 查询
Latest Runs 查询
Paper Chain 查询
Risk Profile 查询
Risk Decision 查询
Target Diff 查询
Portfolio Snapshot 查询
Daily Ops Check
Scheduler Health Check
Ops KPI
Daily Ops Report 导出
Human Review Pack 导出
Ops Summary Pack 导出
Windows Task Template 生成
OpenAPI 导出

当前不支持：

不触发真实交易链
不自动下单
不自动调仓
不提供 mark_stale_runs_apply API
不做生产鉴权
不做生产部署
3. 已验证 API
3.1 Health
Invoke-RestMethod "http://127.0.0.1:8008/health"

API 已可访问。

3.2 Run 查询
Invoke-RestMethod "http://127.0.0.1:8008/api/v1/m8/runs/167"

结果：

overall_status = PASS
run_id = 167
run_type = RISK3
status = SUCCESS
3.3 Latest Runs
Invoke-RestMethod "http://127.0.0.1:8008/api/v1/m8/latest-runs?portfolio_id=1&profile_code=paper_cn_a_risk3_strict_v1"

结果：

overall_status = PASS

trading_chain:
target_run_id = 160
order_run_id = 146
fill_run_id = 147
position_run_id = 153
snapshot_run_id = 154

risk_chain:
risk_run_id = 167
source_target_run_id = 160
adjusted_target_run_id = 166
3.4 Ops KPI
Invoke-RestMethod "http://127.0.0.1:8008/api/v1/m8/ops-kpi?portfolio_id=1&profile_code=paper_cn_a_risk3_strict_v1"

结果：

overall_status = WARN
failures = []
running_count = 0
scheduler_exit_code = 0
hygiene_status = PASS
risk_reject_count = 30
target_quantity_delta = -605400.00000000
target_amount_delta = -9794717.00000000

说明：

WARN 是 strict profile 的预期风控提示，不是 API 失败。
3.5 Scheduler Health
Invoke-RestMethod "http://127.0.0.1:8008/api/v1/m8/scheduler-health?portfolio_id=1&profile_code=paper_cn_a_risk3_strict_v1"

结果：

overall_status = PASS
scheduler_exit_code = 0
daily_ops_status = WARN
hygiene_status = PASS
ops_status = PASS
failures = []
4. OpenAPI 导出验收

命令：

$env:M8_API_DOC_OUTPUT_DIR="artifacts/m8/api"
python -m stock_quant_v2.scripts.m8_api_openapi_export

结果：

overall_status = PASS

输出：

artifacts/m8/api/m8_openapi.json
artifacts/m8/api/m8_api_endpoints.md

文件检查：

M8.8 API artifact check: PASS
5. 当前关键链路
portfolio_id = 1

trading_chain:
target_run_id = 160
order_run_id = 146
fill_run_id = 147
position_run_id = 153
snapshot_run_id = 154

risk_chain:
risk_run_id = 167
source_target_run_id = 160
adjusted_target_run_id = 166

risk_profile_code = paper_cn_a_risk3_strict_v1
6. 验收 SQL
sql/m8_8_acceptance.sql

覆盖：

run 167 exists
RUNNING = 0
latest trading chain data
latest snapshot KPI
latest risk decision data
strict reject count
adjusted target zero
risk profile exists
7. 最终状态
M8.8 FastAPI API / OpenAPI 草案：PASS

---

# 3. 更新 M8 最终状态

现在 M8 不再只是 CLI-first MVP，而是已经补上了：

```text
FastAPI API
OpenAPI 草案
API Runbook
API artifact

因此当前 M8 状态可以更新为：

M8 运维域增强版：PASS

但仍然还没覆盖完整终态里的：

Excel 导出中心
轻量告警 / 日志 / 审计治理
环境配置与启动检查
正式 Scheduler 注册手册