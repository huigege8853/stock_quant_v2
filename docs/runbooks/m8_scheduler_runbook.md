M8 Scheduler Runbook

项目名称：stock_quant_v2  
模块：M8.5 Scheduler Adapter / Manual-to-Scheduled Ops

## 1. 当前目标

M8.5 不是正式自动交易调度器。

当前只做：

```text
daily ops entrypoint
scheduler health check
scheduler plan
Windows Task Scheduler template

当前不做：

不自动触发交易链
不自动应用风控结果
不自动清理 stale run
不自动下单
不自动注册 Windows Task Scheduler
2. 每日入口

手动运行：

$env:M8_PORTFOLIO_ID="1"
$env:M8_RISK_PROFILE_CODE="paper_cn_a_risk3_strict_v1"
$env:M8_REPORT_OUTPUT_DIR="artifacts/m8/daily_ops"
$env:M8_FAIL_ON_WARN="false"

python -m stock_quant_v2.scripts.m8_daily_ops_entrypoint

预期：

scheduler_exit_code = 0
overall_status = PASS

strict profile 下内部 daily ops 可能是 WARN，这是预期。

3. 调度健康检查
python -m stock_quant_v2.scripts.m8_scheduler_health_check

通过条件：

daily_ops_not_fail = PASS
hygiene_pass = PASS
ops_status_pass = PASS
scheduler_exit_code = 0
4. 生成调度计划
python -m stock_quant_v2.scripts.m8_scheduler_plan

输出动作：

HEALTH_CHECK
DAILY_OPS_ENTRYPOINT
GENERATE_WINDOWS_TASK_TEMPLATE
5. 生成 Windows Task Scheduler 模板
$env:M8_SCHEDULER_TEMPLATE_OUTPUT_DIR="artifacts/m8/scheduler"
$env:M8_SCHEDULER_TASK_NAME="stock_quant_v2_m8_daily_ops"
$env:M8_SCHEDULER_TIME="18:30"
$env:M8_PROJECT_ROOT="D:\01_a_Project\10_python\01_Projects\Projet_stock_quant_v2\stock_quant_v2"

python -m stock_quant_v2.scripts.m8_windows_task_template

生成：

artifacts/m8/scheduler/stock_quant_v2_m8_daily_ops.ps1
artifacts/m8/scheduler/stock_quant_v2_m8_daily_ops.xml
artifacts/m8/scheduler/stock_quant_v2_m8_daily_ops_README.md
6. 手动测试模板
powershell -NoProfile -ExecutionPolicy Bypass -File "artifacts/m8/scheduler/stock_quant_v2_m8_daily_ops.ps1"

通过后，再考虑注册任务。

7. 注册任务

注意：XML 默认 disabled。注册后仍需人工检查再启用。

schtasks /Create /TN "stock_quant_v2_m8_daily_ops" /XML "artifacts/m8/scheduler/stock_quant_v2_m8_daily_ops.xml"
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
9. 状态解释
scheduler_exit_code = 0

可以作为计划任务成功。

scheduler_exit_code = 1

存在失败检查，不应继续。

scheduler_exit_code = 2

仅在 M8_FAIL_ON_WARN=true 时出现，代表 WARN 也被视为失败。

当前建议：

M8_FAIL_ON_WARN=false

因为 strict profile 的 30 个 REJECT 是预期风控结果。


---

# 5. M8.5 验收标准

跑完后如果满足：

```text
m8_scheduler_health_check：PASS，scheduler_exit_code = 0
m8_scheduler_plan：PASS
m8_daily_ops_entrypoint：PASS，scheduler_exit_code = 0
m8_windows_task_template：PASS
PowerShell 模板手动执行成功

则 M8.5 可以判定：

M8.5 Scheduler Adapter / Manual-to-Scheduled Ops：PASS

先跑这四个脚本，把输出贴我，我继续给你收口 M8.5 acceptance SQL / 文档。