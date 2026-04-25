# M8 Alert / Log / Audit Runbook

项目名称：stock_quant_v2  
模块：M8.10 Ops Alert / Log / Audit 轻量治理

## 1. 当前目标

M8.10 提供轻量告警、日志查询、审计快照。

当前不做：

```text
不接邮件 / 短信 / 企业微信
不做实时推送
不新增复杂事件总线
不新增数据库表
不改交易数据
不改风控数据
2. Alert Check
$env:M8_PORTFOLIO_ID="1"
$env:M8_RISK_PROFILE_CODE="paper_cn_a_risk3_strict_v1"

python -m stock_quant_v2.scripts.m8_ops_alert_check

当前 strict profile 下预期：

overall_status = WARN
highest_level = WARN
CRITICAL = 0

WARN 来源：

RISK_REJECT_EXISTS
TARGET_QUANTITY_DIFF_EXISTS
TARGET_AMOUNT_DIFF_EXISTS
FAILED_RUNS_EXIST

其中 risk reject 和 target diff 是 strict profile 的预期结果。

3. Alert Report
$env:M8_ALERT_OUTPUT_DIR="artifacts/m8/alert"
python -m stock_quant_v2.scripts.m8_export_alert_report

输出：

artifacts/m8/alert/m8_alert_report_p1_2026-04-23.json
artifacts/m8/alert/m8_alert_report_p1_2026-04-23.md
artifacts/m8/alert/m8_alert_report_p1_2026-04-23_alerts.csv
4. Ops Logs
$env:M8_LIMIT="20"
$env:M8_LOG_ERROR_ONLY="true"
python -m stock_quant_v2.scripts.m8_query_ops_logs

可选过滤：

$env:M8_LOG_STATUS="FAILED"
$env:M8_LOG_RUN_TYPE="PAPER_TRADING"
5. Audit Snapshot
$env:M8_AUDIT_OUTPUT_DIR="artifacts/m8/audit"
python -m stock_quant_v2.scripts.m8_export_audit_snapshot

输出：

artifacts/m8/audit/m8_audit_snapshot_p1_2026-04-23.json
artifacts/m8/audit/m8_audit_snapshot_p1_2026-04-23.md
artifacts/m8/audit/m8_audit_snapshot_p1_2026-04-23_run_status.csv
artifacts/m8/audit/m8_audit_snapshot_p1_2026-04-23_run_type_status.csv
artifacts/m8/audit/m8_audit_snapshot_p1_2026-04-23_error_logs.csv
6. 告警级别
CRITICAL = 调度失败、daily ops 失败、RUNNING 未清零、hygiene 失败
WARN     = 风控拒绝、target diff、FAILED run 存在
INFO     = STALE run 存在等可审计事项
7. 当前通过条件
m8_ops_alert_check = WARN 或 PASS
highest_level != CRITICAL
m8_export_alert_report = PASS
m8_query_ops_logs = PASS
m8_export_audit_snapshot = PASS
artifact check = PASS