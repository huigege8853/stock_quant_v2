# M8.10 Acceptance｜Ops Alert / Log / Audit 轻量治理

项目名称：stock_quant_v2  
模块：M8.10 Ops Alert / Log / Audit  
状态：PASS

## 1. 验收结论

M8.10 已完成轻量告警、日志查询、审计快照能力。

最终结论：

```text
M8.10 Ops Alert / Log / Audit 轻量治理：PASS

2. 本阶段目标

补齐 M8 原始职责中的：

告警
日志
审计

当前采用轻量实现，不新增数据库表，不接实时推送。

3. 当前边界
不接邮件 / 短信 / 企业微信
不做实时推送
不新增复杂事件总线
不新增数据库表
不改交易数据
不改风控数据
4. 已完成 CLI
m8_ops_alert_check
m8_export_alert_report
m8_query_ops_logs
m8_export_audit_snapshot
5. Alert Check 验收

命令：

$env:M8_PORTFOLIO_ID="1"
$env:M8_RISK_PROFILE_CODE="paper_cn_a_risk3_strict_v1"

python -m stock_quant_v2.scripts.m8_ops_alert_check

结果：

overall_status = WARN
highest_level = WARN
CRITICAL = 0
WARN = 4
INFO = 1

Alert 明细：

FAILED_RUNS_EXIST = WARN
STALE_RUNS_EXIST = INFO
RISK_REJECT_EXISTS = WARN
TARGET_QUANTITY_DIFF_EXISTS = WARN
TARGET_AMOUNT_DIFF_EXISTS = WARN

说明：

没有 CRITICAL alert。
WARN 是当前 strict profile 与历史 FAILED run 的预期人工复核提示。
6. Alert Report 验收

命令：

$env:M8_ALERT_OUTPUT_DIR="artifacts/m8/alert"
python -m stock_quant_v2.scripts.m8_export_alert_report

结果：

alert_status = WARN
highest_level = WARN
overall_status = PASS

输出：

artifacts/m8/alert/m8_alert_report_p1_2026-04-23.json
artifacts/m8/alert/m8_alert_report_p1_2026-04-23.md
artifacts/m8/alert/m8_alert_report_p1_2026-04-23_alerts.csv
7. Ops Logs 验收

命令：

$env:M8_LIMIT="20"
$env:M8_LOG_ERROR_ONLY="true"
python -m stock_quant_v2.scripts.m8_query_ops_logs

结果：

overall_status = PASS
log_count = 20

日志样例覆盖：

STALE run cleanup logs
FAILED historical run logs
ERROR / WARN log_level
8. Audit Snapshot 验收

命令：

$env:M8_AUDIT_OUTPUT_DIR="artifacts/m8/audit"
python -m stock_quant_v2.scripts.m8_export_audit_snapshot

结果：

overall_status = PASS

输出：

artifacts/m8/audit/m8_audit_snapshot_p1_2026-04-23.json
artifacts/m8/audit/m8_audit_snapshot_p1_2026-04-23.md
artifacts/m8/audit/m8_audit_snapshot_p1_2026-04-23_run_status.csv
artifacts/m8/audit/m8_audit_snapshot_p1_2026-04-23_run_type_status.csv
artifacts/m8/audit/m8_audit_snapshot_p1_2026-04-23_error_logs.csv
9. Artifact 验收
M8.10 alert audit artifact check: PASS

建议额外确认：

Test-Path "artifacts/m8/alert/m8_alert_report_p1_2026-04-23_alerts.csv"
10. 当前关键 KPI
snapshot_date = 2026-04-23
total_equity = 10032531.13334439
holding_count = 30

risk_decision_count = 90
risk_pass_count = 60
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
11. 当前关键链路
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
12. 验收 SQL
sql/m8_10_acceptance.sql

覆盖：

RUNNING 清零
FAILED run WARN 依据
STALE run INFO 依据
latest trading chain data
snapshot KPI
risk decision rows
strict reject count
strict no WARN / ADJUST
adjusted target zero
ops logs available
risk profile exists
13. 最终状态
M8.10 Ops Alert / Log / Audit 轻量治理：PASS