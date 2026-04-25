# M8 Enhanced Final Acceptance

项目名称：stock_quant_v2  
模块：M8 接口、调度与运维域增强版  
状态：PASS

## 1. 总体验收结论

M8 增强版已完成：

```text
CLI
FastAPI API
OpenAPI 草案
Scheduler Adapter
Scheduler Registration Manual
Daily Ops
Run Monitor
Run Hygiene
Human Review Pack
JSON / Markdown / CSV / Excel 导出
轻量 Alert
Ops Logs 查询
Audit Snapshot
Environment Check
Startup Check
Runbook

最终结论：

M8 接口、调度与运维域增强版：PASS
2. 子模块状态
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
M8.11 Environment Config / Startup Check：PASS
M8.12 Scheduler Registration Manual / Final Enhanced Acceptance：PASS
3. 当前核心状态
RUNNING = 0
STALE = 20
FAILED = 16
SUCCESS = 115

scheduler_exit_code = 0
highest_alert_level = WARN
api_route_count = 32
failures = []
4. 当前关键链路
portfolio_id = 1
target_run_id = 160
order_run_id = 146
fill_run_id = 147
position_run_id = 153
snapshot_run_id = 154
risk_run_id = 167
source_target_run_id = 160
adjusted_target_run_id = 166
risk_profile_code = paper_cn_a_risk3_strict_v1
snapshot_date = 2026-04-23
5. 当前关键 KPI
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
6. WARN 说明

当前 WARN 是预期人工复核提示：

strict profile 产生 30 个 REJECT
adjusted target 被清零
target quantity / amount delta 非 0
历史 FAILED run 仍保留为审计对象
STALE run 保留为治理痕迹
显式 V2_SQLALCHEMY_URL 未设置但 SessionLocal 可连接

当前没有 CRITICAL alert，也没有 failures。

7. M8 原始职责覆盖情况
原始职责	当前状态
FastAPI API	已完成
CLI	已完成
Scheduler	Adapter + 注册手册已完成，未自动启用
任务编排	Daily Ops EntryPoint 已完成
运行监控	已完成
导出中心	JSON / Markdown / CSV / Excel 已完成
Runbook	已完成
OpenAPI 草案	已完成
任务调度图与状态机	Scheduler plan / registration pack 已完成
告警	轻量 Alert 已完成
日志	Ops Logs 查询已完成
审计	Audit Snapshot 已完成
环境配置管理	Env / Startup Check 已完成
8. 当前仍然不做
不接真实券商
不做真实自动交易
不自动下单
不自动调仓
不自动启用 Windows Task Scheduler
不做生产级鉴权
不做实时告警推送
9. 验收 SQL
sql/m8_1_acceptance.sql
sql/m8_2_acceptance.sql
sql/m8_3_acceptance.sql
sql/m8_4_acceptance.sql
sql/m8_5_acceptance.sql
sql/m8_6_acceptance.sql
sql/m8_8_acceptance.sql
sql/m8_9_acceptance.sql
sql/m8_10_acceptance.sql
sql/m8_11_acceptance.sql
sql/m8_12_acceptance.sql
sql/m8_enhanced_final_acceptance.sql
10. 最终状态
M8 接口、调度与运维域增强版：PASS