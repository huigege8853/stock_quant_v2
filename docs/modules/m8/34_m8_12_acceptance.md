# M8.12 Acceptance｜Scheduler Registration Manual / Final Enhanced Acceptance

项目名称：stock_quant_v2  
模块：M8.12 Scheduler Registration Manual / Final Enhanced Acceptance  
状态：PASS

## 1. 验收结论

M8.12 已完成 Windows Task Scheduler 注册手册、注册前检查和注册包导出。

最终结论：

```text
M8.12 Scheduler Registration Manual / Final Enhanced Acceptance：PASS

2. 当前边界
不强制启用真实计划任务
不自动注册 Windows Task Scheduler
不触发交易链
不自动下单
只生成注册检查、注册包、最终增强验收
3. 已完成 CLI
m8_scheduler_registration_check
m8_enhanced_final_check
m8_export_scheduler_registration_pack
4. Scheduler Registration Check

结果：

overall_status = WARN
scheduler_exit_code = 0
startup_status = WARN
alert_status = WARN
highest_alert_level = WARN
failures = []

文件检查：

scheduler_files_pass = true
template_checks_pass = true
scheduler_health_pass = true
scheduler_exit_code_zero = true
startup_not_fail = true
alert_no_critical = true

模板检查：

PS1_HAS_DAILY_OPS_ENTRYPOINT = PASS
PS1_HAS_FAIL_ON_WARN_FALSE = PASS
PS1_HAS_PORTFOLIO_ID = PASS
PS1_HAS_PROFILE_CODE = PASS
XML_HAS_POWERSHELL_COMMAND = PASS
XML_HAS_PS1_PATH = PASS
XML_DISABLED_BY_DEFAULT = PASS
README_EXISTS_AND_HAS_REGISTER_COMMAND = PASS
5. Enhanced Final Check

结果：

overall_status = WARN
failures = []
scheduler_exit_code = 0
api_route_count = 32
highest_alert_level = WARN

核心检查：

ops_kpi_not_fail = true
startup_not_fail = true
registration_not_fail = true
alert_no_critical = true
scheduler_exit_code_zero = true
running_zero = true
api_app_pass = true
route_count_positive = true
risk_decision_count_ok = true
risk_reject_expected = true
6. Registration Pack Export

结果：

registration_status = WARN
enhanced_final_status = WARN
overall_status = PASS

输出：

artifacts/m8/scheduler_registration/m8_scheduler_registration_pack_p1_2026-04-23.json
artifacts/m8/scheduler_registration/m8_scheduler_registration_pack_p1_2026-04-23.md
artifacts/m8/scheduler_registration/m8_scheduler_registration_pack_p1_2026-04-23_commands.csv
artifacts/m8/scheduler_registration/m8_scheduler_registration_pack_p1_2026-04-23_checklist.csv

Artifact 检查：

M8.12 scheduler registration artifact check: PASS
7. 当前关键 KPI
snapshot_date = 2026-04-23
total_equity = 10032531.13334439
holding_count = 30

order_count = 28
fill_count = 28
position_count = 30
snapshot_count = 1

risk_decision_count = 90
risk_pass_count = 60
risk_warn_count = 0
risk_reject_count = 30
risk_adjust_count = 0

target_quantity_delta = -605400.00000000
target_amount_delta = -9794717.00000000

scheduler_exit_code = 0
scheduler_status = PASS
hygiene_status = PASS

RUNNING = 0
STALE = 20
FAILED = 16
SUCCESS = 115
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
9. 手动注册命令

手动测试 PS1：

powershell -NoProfile -ExecutionPolicy Bypass -File "artifacts\m8\scheduler\stock_quant_v2_m8_daily_ops.ps1"

注册任务：

schtasks /Create /TN "stock_quant_v2_m8_daily_ops" /XML "artifacts\m8\scheduler\stock_quant_v2_m8_daily_ops.xml"

启用任务：

schtasks /Change /TN "stock_quant_v2_m8_daily_ops" /ENABLE

禁用任务：

schtasks /Change /TN "stock_quant_v2_m8_daily_ops" /DISABLE

删除任务：

schtasks /Delete /TN "stock_quant_v2_m8_daily_ops" /F
10. 验收 SQL
sql/m8_12_acceptance.sql
11. 最终状态
M8.12 Scheduler Registration Manual / Final Enhanced Acceptance：PASS