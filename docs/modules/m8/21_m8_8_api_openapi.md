M8.8 FastAPI API / OpenAPI 草案

项目名称：stock_quant_v2  
模块：M8.8 FastAPI API / OpenAPI 草案  
状态：待验收

## 1. 目标

M8.8 目标是把 M8 CLI-first 运维能力暴露为 FastAPI API，并生成 OpenAPI 草案。

## 2. 当前边界

```text
只做查询和安全导出
不触发真实交易链
不自动下单
不自动调仓
不提供 stale apply API
不做生产鉴权
3. 新增文件
src/stock_quant_v2/api/__init__.py
src/stock_quant_v2/api/app.py
src/stock_quant_v2/api/deps.py
src/stock_quant_v2/api/routers/__init__.py
src/stock_quant_v2/api/routers/m8_ops.py
src/stock_quant_v2/scripts/m8_api_openapi_export.py
docs/runbooks/m8_api_runbook.md
docs/modules/m8/21_m8_8_api_openapi.md
4. API 路由
GET  /health
GET  /api/v1/m8/runs/{run_id}
GET  /api/v1/m8/latest-runs
GET  /api/v1/m8/paper-chain
GET  /api/v1/m8/portfolio-snapshot
GET  /api/v1/m8/risk-profile
GET  /api/v1/m8/risk-decision
GET  /api/v1/m8/target-diff
GET  /api/v1/m8/daily-ops/check
GET  /api/v1/m8/daily-ops/plan
GET  /api/v1/m8/ops-status
GET  /api/v1/m8/hygiene-check
GET  /api/v1/m8/scheduler-health
GET  /api/v1/m8/ops-kpi
POST /api/v1/m8/export/daily-ops-report
POST /api/v1/m8/export/human-review-pack
POST /api/v1/m8/export/ops-summary-pack
POST /api/v1/m8/scheduler/windows-task-template
5. 验收命令
uvicorn stock_quant_v2.api.app:app --host 127.0.0.1 --port 8008 --reload
Invoke-RestMethod "http://127.0.0.1:8008/health"
Invoke-RestMethod "http://127.0.0.1:8008/api/v1/m8/runs/167"
Invoke-RestMethod "http://127.0.0.1:8008/api/v1/m8/latest-runs?portfolio_id=1&profile_code=paper_cn_a_risk3_strict_v1"
Invoke-RestMethod "http://127.0.0.1:8008/api/v1/m8/ops-kpi?portfolio_id=1&profile_code=paper_cn_a_risk3_strict_v1"
Invoke-RestMethod "http://127.0.0.1:8008/api/v1/m8/scheduler-health?portfolio_id=1&profile_code=paper_cn_a_risk3_strict_v1"
$env:M8_API_DOC_OUTPUT_DIR="artifacts/m8/api"
python -m stock_quant_v2.scripts.m8_api_openapi_export
6. 通过标准
API 可启动
/health 返回 ok
/runs/167 返回 PASS
/latest-runs 返回 PASS
/ops-kpi 返回 WARN 或 PASS，且 failures=[]
/scheduler-health 返回 PASS，scheduler_exit_code=0
OpenAPI JSON 成功导出

---

# 9. 本轮验收标准

跑完后贴这几段输出：

```text
uvicorn 启动日志
/health 返回
/runs/167 返回 overall_status
/latest-runs 返回 overall_status
/ops-kpi 返回 overall_status
/scheduler-health 返回 overall_status
m8_api_openapi_export 返回

如果都正常，M8.8 就可以收口为：

M8.8 FastAPI API / OpenAPI 草案：PASS