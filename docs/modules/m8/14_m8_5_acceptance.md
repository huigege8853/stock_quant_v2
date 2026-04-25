M8.5 Acceptance｜Scheduler Adapter / Manual-to-Scheduled Ops

项目名称：stock_quant_v2  
模块：M8.5 Scheduler Adapter / Manual-to-Scheduled Ops  
状态：PASS

## 1. 验收结论

M8.5 已完成调度适配层第一版。

最终结论：

```text
M8.5 Scheduler Adapter / Manual-to-Scheduled Ops：PASS
2. 本阶段目标

M8.5 不是正式自动交易调度器。

当前只做：

daily ops entrypoint
scheduler health check
scheduler plan
Windows Task Scheduler template
PowerShell template manual test

当前不做：

不自动触发交易链
不自动应用风控结果
不自动清理 stale run
不自动下单
不自动注册 Windows Task Scheduler
3. 已完成 CLI
m8_scheduler_health_check
m8_scheduler_plan
m8_daily_ops_entrypoint
m8_windows_task_template
4. Scheduler Health Check 验收

命令：

$env:M8_PORTFOLIO_ID="1"
$env:M8_RISK_PROFILE_CODE="paper_cn_a_risk3_strict_v1"
$env:M8_REPORT_OUTPUT_DIR="artifacts/m8/daily_ops"

python -m stock_quant_v2.scripts.m8_scheduler_health_check

结果：

daily_ops_status = WARN
hygiene_status = PASS
ops_status = PASS
scheduler_exit_code = 0
overall_status = PASS

说明：

daily_ops_status = WARN 是 strict profile 的预期风控 WARN。
只要 failures = [] 且 scheduler_exit_code = 0，调度健康检查通过。
5. Scheduler Plan 验收

命令：

$env:M8_PORTFOLIO_ID="1"
$env:M8_RISK_PROFILE_CODE="paper_cn_a_risk3_strict_v1"
$env:M8_REPORT_OUTPUT_DIR="artifacts/m8/daily_ops"
$env:M8_SCHEDULER_TASK_NAME="stock_quant_v2_m8_daily_ops"
$env:M8_SCHEDULER_TIME="18:30"

python -m stock_quant_v2.scripts.m8_scheduler_plan

结果：

overall_status = PASS
scheduler_exit_code = 0

动作：

HEALTH_CHECK
DAILY_OPS_ENTRYPOINT
GENERATE_WINDOWS_TASK_TEMPLATE
6. Daily Ops Entrypoint 验收

命令：

$env:M8_PORTFOLIO_ID="1"
$env:M8_RISK_PROFILE_CODE="paper_cn_a_risk3_strict_v1"
$env:M8_REPORT_OUTPUT_DIR="artifacts/m8/daily_ops"
$env:M8_FAIL_ON_WARN="false"

python -m stock_quant_v2.scripts.m8_daily_ops_entrypoint

结果：

scheduler_exit_code = 0
overall_status = PASS
daily_report.overall_status = WARN
daily_report.daily_report.overall_status = PASS

说明：

外层 entrypoint PASS，代表调度入口可执行。
内部 daily_ops_check WARN，代表 strict profile 产生预期风控 WARN。
日报导出 PASS。
7. Windows Task Template 验收

命令：

$env:M8_PORTFOLIO_ID="1"
$env:M8_RISK_PROFILE_CODE="paper_cn_a_risk3_strict_v1"
$env:M8_REPORT_OUTPUT_DIR="artifacts/m8/daily_ops"
$env:M8_SCHEDULER_TEMPLATE_OUTPUT_DIR="artifacts/m8/scheduler"
$env:M8_SCHEDULER_TASK_NAME="stock_quant_v2_m8_daily_ops"
$env:M8_SCHEDULER_TIME="18:30"
$env:M8_PROJECT_ROOT="D:\01_a_Project\10_python\01_Projects\Projet_stock_quant_v2\stock_quant_v2"

python -m stock_quant_v2.scripts.m8_windows_task_template

结果：

overall_status = PASS

生成：

artifacts/m8/scheduler/stock_quant_v2_m8_daily_ops.ps1
artifacts/m8/scheduler/stock_quant_v2_m8_daily_ops.xml
artifacts/m8/scheduler/stock_quant_v2_m8_daily_ops_README.md
8. PowerShell 模板手动执行验收

命令：

powershell -NoProfile -ExecutionPolicy Bypass -File "artifacts/m8/scheduler/stock_quant_v2_m8_daily_ops.ps1"

结果：

scheduler_exit_code = 0
overall_status = PASS
M8.5 daily ops entrypoint completed.
9. 当前关键链路
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
10. 当前 Run 状态
FAILED = 16
STALE = 20
SUCCESS = 115
RUNNING = 0
11. 验收 SQL
sql/m8_5_acceptance.sql

覆盖：

RUNNING 清零
latest trading chain run 状态
latest trading chain 业务数据
latest risk chain 业务数据
strict profile 预期 REJECT
daily ops snapshot
12. 最终状态
M8.5 Scheduler Adapter / Manual-to-Scheduled Ops：PASS