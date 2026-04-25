M8.10 Next Step Brief

项目名称：stock_quant_v2

当前阶段：M8.10 Ops Alert / Log / Audit 轻量治理已完成。

## 1. 当前结论

```text
M8.1 Run Monitor + CLI 运维入口：PASS
M8.2 Ops Report Export Center / Runbook：PASS
M8.3 Daily Ops Orchestration / Scheduler Preparation：PASS
M8.4 Ops Hygiene / Stale Run Cleanup：PASS
M8.5 Scheduler Adapter / Manual-to-Scheduled Ops：PASS
M8.6 Ops Dashboard / Human Review Pack：PASS
M8.7 Final M8 Acceptance / Module Handoff：PASS
M8.8 FastAPI API / OpenAPI 草案：PASS
M8.9 Excel 导出中心：PASS
M8.10 Ops Alert / Log / Audit 轻量治理：PASS
2. M8.10 已完成
m8_ops_alert_check
m8_export_alert_report
m8_query_ops_logs
m8_export_audit_snapshot
3. M8.10 输出
artifacts/m8/alert/m8_alert_report_p1_2026-04-23.json
artifacts/m8/alert/m8_alert_report_p1_2026-04-23.md
artifacts/m8/alert/m8_alert_report_p1_2026-04-23_alerts.csv

artifacts/m8/audit/m8_audit_snapshot_p1_2026-04-23.json
artifacts/m8/audit/m8_audit_snapshot_p1_2026-04-23.md
artifacts/m8/audit/m8_audit_snapshot_p1_2026-04-23_run_status.csv
artifacts/m8/audit/m8_audit_snapshot_p1_2026-04-23_run_type_status.csv
artifacts/m8/audit/m8_audit_snapshot_p1_2026-04-23_error_logs.csv
4. 当前 Alert 状态
highest_level = WARN
CRITICAL = 0
WARN = 4
INFO = 1
overall_status = WARN

当前没有 CRITICAL alert。

5. 当前 M8 已覆盖能力
CLI
FastAPI API
OpenAPI 草案
Scheduler Adapter
Daily Ops
Run Monitor
Run Hygiene
Human Review Pack
JSON / Markdown / CSV / Excel 导出
轻量 Alert
Ops Logs 查询
Audit Snapshot
Runbook
6. 当前仍待补齐
环境配置与启动检查
正式 Scheduler 注册手册
M8 增强版最终验收与交接文档
7. 下一步建议

进入：

M8.11 Environment Config / Startup Check

建议新增：

m8_env_check
m8_startup_check
m8_export_env_report
docs/runbooks/m8_startup_runbook.md

目标：

检查 DATABASE_URL / V2_SQLALCHEMY_URL
检查 artifacts 目录可写
检查关键依赖 fastapi / uvicorn / openpyxl
检查 API app 可 import
检查 SessionLocal 可连接
检查核心 M8 artifacts 是否存在
输出环境配置报告
8. M8.11 暂不做
不自动修复环境
不改数据库
不改交易数据
不注册调度任务

---

# 4. 当前 M8 状态更新

现在 M8 已补齐：

```text
轻量告警
日志查询
审计快照

当前可以更新为：

M8 运维域增强版：PASS