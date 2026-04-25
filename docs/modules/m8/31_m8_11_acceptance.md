# M8.11 Acceptance｜Environment Config / Startup Check

项目名称：stock_quant_v2  
模块：M8.11 Environment Config / Startup Check  
状态：PASS

## 1. 验收结论

M8.11 已完成环境配置检查、启动前检查和环境报告导出。

最终结论：

```text
M8.11 Environment Config / Startup Check：PASS

2. 本阶段目标

补齐 M8 原始职责中的：

环境配置管理
启动检查
启动手册
3. 当前边界
不自动修复环境
不改数据库
不改交易数据
不注册调度任务
只做检查和报告
4. 已完成 CLI
m8_env_check
m8_startup_check
m8_export_env_report
5. Env Check 验收

命令：

$env:M8_PORTFOLIO_ID="1"
$env:M8_RISK_PROFILE_CODE="paper_cn_a_risk3_strict_v1"
$env:M8_PROJECT_ROOT="D:\01_a_Project\10_python\01_Projects\Projet_stock_quant_v2\stock_quant_v2"

python -m stock_quant_v2.scripts.m8_env_check

结果：

overall_status = WARN
failures = []

核心检查：

env_vars_pass = true
dependencies_pass = true
paths_pass = true
artifacts_pass = true
imports_pass = true
db_connection_pass = true
latest_runs_pass = true

说明：

V2_SQLALCHEMY_URL 未显式设置，但 SessionLocal database connection passed。
因此该项降级为 WARN，不阻断启动。

依赖检查全部 PASS：

sqlalchemy = PASS
psycopg = PASS
fastapi = PASS
uvicorn = PASS
openpyxl = PASS
pydantic_settings = PASS
6. Startup Check 验收

命令：

python -m stock_quant_v2.scripts.m8_startup_check

结果：

overall_status = WARN
failures = []
scheduler_exit_code = 0
highest_alert_level = WARN
api_import.status = PASS
api_app.status = PASS
route_count = 32

说明：

WARN 来源于 ENV_WARN、OPS_KPI_WARN、ALERT_WARN。
当前无 CRITICAL alert，启动检查通过。
7. Env Report Export 验收

命令：

$env:M8_ENV_OUTPUT_DIR="artifacts/m8/env"
python -m stock_quant_v2.scripts.m8_export_env_report

结果：

env_status = WARN
startup_status = WARN
overall_status = PASS

输出：

artifacts/m8/env/m8_env_startup_report_p1_2026-04-23.json
artifacts/m8/env/m8_env_startup_report_p1_2026-04-23.md
artifacts/m8/env/m8_env_startup_report_p1_2026-04-23_env_vars.csv
artifacts/m8/env/m8_env_startup_report_p1_2026-04-23_dependencies.csv
artifacts/m8/env/m8_env_startup_report_p1_2026-04-23_paths.csv
artifacts/m8/env/m8_env_startup_report_p1_2026-04-23_artifacts.csv

Artifact 检查：

M8.11 env startup artifact check: PASS
8. 当前关键链路
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
snapshot_date = 2026-04-23
9. 当前启动健康状态
database connection = PASS
latest runs = PASS
API app import = PASS
API route_count = 32
scheduler_exit_code = 0
highest_alert_level = WARN
failures = []
10. 验收 SQL
sql/m8_11_acceptance.sql

覆盖：

database accessible
RUNNING 清零
run status counts
latest run status
latest trading chain data
snapshot KPI
risk decision rows
strict reject expected
adjusted target zero
risk profile exists
11. 最终状态
M8.11 Environment Config / Startup Check：PASS