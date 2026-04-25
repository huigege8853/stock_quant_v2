M8 API Runbook

项目名称：stock_quant_v2  
模块：M8.8 FastAPI API / OpenAPI 草案

## 1. 当前边界

M8.8 当前是只读和安全导出 API。

当前支持：

```text
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

当前不支持：

不触发真实交易链
不自动下单
不自动调仓
不提供 mark_stale_runs_apply API
不做认证鉴权复杂化
不做生产部署
2. 启动 API
uvicorn stock_quant_v2.api.app:app --host 127.0.0.1 --port 8008 --reload
3. 文档入口
http://127.0.0.1:8008/docs
http://127.0.0.1:8008/openapi.json
4. 健康检查
Invoke-RestMethod "http://127.0.0.1:8008/health"
5. 常用接口
5.1 查询 Run
Invoke-RestMethod "http://127.0.0.1:8008/api/v1/m8/runs/167"
5.2 查询 Latest Runs
Invoke-RestMethod "http://127.0.0.1:8008/api/v1/m8/latest-runs?portfolio_id=1&profile_code=paper_cn_a_risk3_strict_v1"
5.3 查询 Ops KPI
Invoke-RestMethod "http://127.0.0.1:8008/api/v1/m8/ops-kpi?portfolio_id=1&profile_code=paper_cn_a_risk3_strict_v1"
5.4 查询 Scheduler Health
Invoke-RestMethod "http://127.0.0.1:8008/api/v1/m8/scheduler-health?portfolio_id=1&profile_code=paper_cn_a_risk3_strict_v1"
6. 导出 OpenAPI
$env:M8_API_DOC_OUTPUT_DIR="artifacts/m8/api"
python -m stock_quant_v2.scripts.m8_api_openapi_export

输出：

artifacts/m8/api/m8_openapi.json
artifacts/m8/api/m8_api_endpoints.md
7. 当前关键链路
portfolio_id = 1
target_run_id = 160
order_run_id = 146
fill_run_id = 147
position_run_id = 153
snapshot_run_id = 154
risk_run_id = 167
source_target_run_id = 160
adjusted_target_run_id = 166
risk_profile_code = paper_cn_a_risk3_strict_v1