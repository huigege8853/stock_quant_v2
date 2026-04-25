# M8.12 Scheduler Registration Manual / Final Enhanced Acceptance

项目名称：stock_quant_v2  
模块：M8.12 Scheduler Registration Manual / Final Enhanced Acceptance  
状态：待验收

## 1. 目标

M8.12 用于补齐：

```text
正式 Scheduler 注册手册
Scheduler 启用前检查清单
M8 增强版最终检查
M8 增强版交接准备
2. 当前边界
不强制启用真实计划任务
不自动注册 Windows Task Scheduler
不触发交易链
不自动下单
只生成注册检查、注册包、最终增强验收
3. 已新增 CLI
m8_scheduler_registration_check
m8_enhanced_final_check
m8_export_scheduler_registration_pack
4. 验收命令
$env:M8_PORTFOLIO_ID="1"
$env:M8_RISK_PROFILE_CODE="paper_cn_a_risk3_strict_v1"
$env:M8_PROJECT_ROOT="D:\01_a_Project\10_python\01_Projects\Projet_stock_quant_v2\stock_quant_v2"
$env:M8_SCHEDULER_TEMPLATE_OUTPUT_DIR="artifacts/m8/scheduler"
$env:M8_SCHEDULER_TASK_NAME="stock_quant_v2_m8_daily_ops"

python -m stock_quant_v2.scripts.m8_scheduler_registration_check
python -m stock_quant_v2.scripts.m8_enhanced_final_check

$env:M8_SCHEDULER_REG_OUTPUT_DIR="artifacts/m8/scheduler_registration"
python -m stock_quant_v2.scripts.m8_export_scheduler_registration_pack
5. 通过标准
m8_scheduler_registration_check = PASS 或 WARN
m8_enhanced_final_check = PASS 或 WARN
m8_export_scheduler_registration_pack = PASS
failures = []
scheduler_exit_code = 0
highest_alert_level != CRITICAL
artifact check = PASS
6. 输出
artifacts/m8/scheduler_registration/m8_scheduler_registration_pack_p1_2026-04-23.json
artifacts/m8/scheduler_registration/m8_scheduler_registration_pack_p1_2026-04-23.md
artifacts/m8/scheduler_registration/m8_scheduler_registration_pack_p1_2026-04-23_commands.csv
artifacts/m8/scheduler_registration/m8_scheduler_registration_pack_p1_2026-04-23_checklist.csv