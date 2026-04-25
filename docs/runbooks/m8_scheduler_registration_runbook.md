# M8 Scheduler Registration Runbook

项目名称：stock_quant_v2  
模块：M8.12 Scheduler Registration Manual / Final Enhanced Acceptance

## 1. 当前目标

M8.12 提供 Windows Task Scheduler 注册手册和启用前检查。

当前不做：

```text
不强制启用真实计划任务
不自动注册 Windows Task Scheduler
不触发交易链
不自动下单

2. 注册前检查
$env:M8_PORTFOLIO_ID="1"
$env:M8_RISK_PROFILE_CODE="paper_cn_a_risk3_strict_v1"
$env:M8_PROJECT_ROOT="D:\01_a_Project\10_python\01_Projects\Projet_stock_quant_v2\stock_quant_v2"
$env:M8_SCHEDULER_TEMPLATE_OUTPUT_DIR="artifacts/m8/scheduler"
$env:M8_SCHEDULER_TASK_NAME="stock_quant_v2_m8_daily_ops"

python -m stock_quant_v2.scripts.m8_scheduler_registration_check

通过条件：

overall_status = PASS 或 WARN
failures = []
scheduler_exit_code = 0
highest_alert_level != CRITICAL
template_checks_pass = true
scheduler_files_pass = true
3. M8 增强版最终检查
python -m stock_quant_v2.scripts.m8_enhanced_final_check

通过条件：

overall_status = PASS 或 WARN
failures = []
running_zero = true
api_app_pass = true
route_count_positive = true
risk_decision_count_ok = true
risk_reject_expected = true
4. 导出注册包
$env:M8_SCHEDULER_REG_OUTPUT_DIR="artifacts/m8/scheduler_registration"
python -m stock_quant_v2.scripts.m8_export_scheduler_registration_pack

输出：

artifacts/m8/scheduler_registration/m8_scheduler_registration_pack_p1_2026-04-23.json
artifacts/m8/scheduler_registration/m8_scheduler_registration_pack_p1_2026-04-23.md
artifacts/m8/scheduler_registration/m8_scheduler_registration_pack_p1_2026-04-23_commands.csv
artifacts/m8/scheduler_registration/m8_scheduler_registration_pack_p1_2026-04-23_checklist.csv
5. 手动测试 PS1
powershell -NoProfile -ExecutionPolicy Bypass -File "artifacts/m8/scheduler/stock_quant_v2_m8_daily_ops.ps1"

预期：

M8.5 daily ops entrypoint completed.
6. 手动注册任务

确认 PS1 手动执行成功后，再注册：

schtasks /Create /TN "stock_quant_v2_m8_daily_ops" /XML "artifacts/m8/scheduler/stock_quant_v2_m8_daily_ops.xml"
7. 人工检查后启用
schtasks /Change /TN "stock_quant_v2_m8_daily_ops" /ENABLE
8. 禁用任务
schtasks /Change /TN "stock_quant_v2_m8_daily_ops" /DISABLE
9. 删除任务
schtasks /Delete /TN "stock_quant_v2_m8_daily_ops" /F
10. 当前建议

当前阶段建议只保留模板和注册包，不急于启用真实计划任务。