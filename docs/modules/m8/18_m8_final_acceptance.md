# M8 Final Acceptance

项目名称：stock_quant_v2  
模块：M8 运维域  
状态：PASS

## 1. 总体验收结论

M8 已完成从 Run Monitor、报告导出、每日运维检查、Run 状态治理、调度适配到人工复核包的完整闭环。

最终结论：

```text
M8 运维域：PASS

2. 子模块状态
M8.1 Run Monitor + CLI 运维入口：PASS
M8.2 Ops Report Export Center / Runbook：PASS
M8.3 Daily Ops Orchestration / Scheduler Preparation：PASS
M8.4 Ops Hygiene / Stale Run Cleanup：PASS
M8.5 Scheduler Adapter / Manual-to-Scheduled Ops：PASS
M8.6 Ops Dashboard / Human Review Pack：PASS
M8.7 Final M8 Acceptance / Module Handoff：PASS
3. 当前关键链路
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
4. 当前关键 KPI
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
5. strict profile 说明

当前使用：

paper_cn_a_risk3_strict_v1

该 profile 下：

risk_reject_count = 30
adjusted target quantity = 0
adjusted target amount = 0

这是预期风控结果，不是系统失败。

因此：

daily_ops_check = WARN
ops_kpi = WARN

属于人工复核提示，非失败。失败判断以 failures = []、scheduler_exit_code = 0 和核心检查 PASS 为准。

6. M8 已完成 CLI 清单
M8.1 Query
m8_query_run
m8_query_latest_runs
m8_query_paper_chain
m8_query_portfolio_snapshot
m8_query_risk_profile
m8_query_risk_decision
m8_query_target_diff
m8_export_risk_report
M8.2 Export
m8_export_paper_chain_report
m8_export_portfolio_snapshot_report
m8_export_run_summary_report
m8_export_daily_ops_report
M8.3 Daily Ops
m8_daily_ops_check
m8_daily_ops_plan
m8_ops_status_summary
M8.4 Hygiene
m8_ops_run_hygiene_check
m8_query_stale_runs
m8_mark_stale_runs_dry_run
m8_mark_stale_runs_apply
M8.5 Scheduler Adapter
m8_scheduler_health_check
m8_scheduler_plan
m8_daily_ops_entrypoint
m8_windows_task_template
M8.6 Human Review
m8_query_ops_kpi
m8_export_human_review_pack
m8_export_ops_summary_pack
7. M8 已完成 SQL
sql/m8_1_acceptance.sql
sql/m8_2_acceptance.sql
sql/m8_3_acceptance.sql
sql/m8_4_acceptance.sql
sql/m8_5_acceptance.sql
sql/m8_6_acceptance.sql
sql/m8_final_acceptance.sql
8. M8 已完成 Runbook
docs/runbooks/m8_cli_runbook.md
docs/runbooks/m8_troubleshooting.md
docs/runbooks/m8_daily_ops_runbook.md
docs/runbooks/m8_scheduler_runbook.md
docs/runbooks/m8_human_review_runbook.md
9. M8 已完成验收文档
docs/modules/m8/06_acceptance.md
docs/modules/m8/08_m8_2_acceptance.md
docs/modules/m8/10_m8_3_acceptance.md
docs/modules/m8/12_m8_4_acceptance.md
docs/modules/m8/14_m8_5_acceptance.md
docs/modules/m8/16_m8_6_acceptance.md
docs/modules/m8/18_m8_final_acceptance.md
10. 当前边界

M8 完成的是运维域闭环，但仍然保持以下边界：

不自动触发交易链
不自动应用风控结果
不自动下单
不做真实券商交易
不做 FastAPI Dashboard
不自动注册 Windows Task Scheduler
11. 最终状态
M8 运维域：PASS