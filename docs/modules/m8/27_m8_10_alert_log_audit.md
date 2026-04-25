M8.10 Ops Alert / Log / Audit 轻量治理

项目名称：stock_quant_v2  
模块：M8.10 Ops Alert / Log / Audit  
状态：待验收

## 1. 目标

补齐 M8 原始职责中的：

```text
告警
日志
审计
2. 已新增 CLI
m8_ops_alert_check
m8_export_alert_report
m8_query_ops_logs
m8_export_audit_snapshot
3. 当前边界
不接邮件 / 短信 / 企业微信
不做实时推送
不新增复杂事件总线
不新增数据库表
不改交易数据
不改风控数据
4. 输出目录
artifacts/m8/alert
artifacts/m8/audit
5. 验收命令
$env:M8_PORTFOLIO_ID="1"
$env:M8_RISK_PROFILE_CODE="paper_cn_a_risk3_strict_v1"

python -m stock_quant_v2.scripts.m8_ops_alert_check

$env:M8_ALERT_OUTPUT_DIR="artifacts/m8/alert"
python -m stock_quant_v2.scripts.m8_export_alert_report

$env:M8_LIMIT="20"
$env:M8_LOG_ERROR_ONLY="true"
python -m stock_quant_v2.scripts.m8_query_ops_logs

$env:M8_AUDIT_OUTPUT_DIR="artifacts/m8/audit"
python -m stock_quant_v2.scripts.m8_export_audit_snapshot
6. 通过标准
m8_ops_alert_check = WARN 或 PASS
highest_level != CRITICAL
m8_export_alert_report = PASS
m8_query_ops_logs = PASS
m8_export_audit_snapshot = PASS
artifact check = PASS