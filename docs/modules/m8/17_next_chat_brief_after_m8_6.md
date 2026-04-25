M8.6 Next Chat Brief

项目名称：stock_quant_v2

当前阶段：M8.6 Ops Dashboard / Human Review Pack 已完成。

## 1. 当前结论

```text
M8.1 Run Monitor + CLI 运维入口：PASS
M8.2 Ops Report Export Center / Runbook：PASS
M8.3 Daily Ops Orchestration / Scheduler Preparation：PASS
M8.4 Ops Hygiene / Stale Run Cleanup：PASS
M8.5 Scheduler Adapter / Manual-to-Scheduled Ops：PASS
M8.6 Ops Dashboard / Human Review Pack：PASS
2. M8.6 已完成 CLI
m8_query_ops_kpi
m8_export_human_review_pack
m8_export_ops_summary_pack
3. 已完成人工复核包
artifacts/m8/human_review/m8_human_review_pack_p1_2026-04-23.json
artifacts/m8/human_review/m8_human_review_pack_p1_2026-04-23.md
artifacts/m8/human_review/m8_human_review_pack_p1_2026-04-23_kpi.csv
artifacts/m8/human_review/m8_human_review_pack_p1_2026-04-23_risk_reasons.csv
artifacts/m8/human_review/m8_human_review_pack_p1_2026-04-23_run_status.csv
artifacts/m8/human_review/m8_ops_summary_pack_p1_2026-04-23.json
artifacts/m8/human_review/m8_ops_summary_pack_p1_2026-04-23.md
artifacts/m8/human_review/m8_ops_summary_pack_p1_2026-04-23_recent_runs.csv
4. 当前关键 KPI
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
5. 当前关键链路
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
6. 当前边界
不做 FastAPI Dashboard
不注册真实定时任务
不自动触发交易链
不自动应用风控结果
不自动改交易/风控数据
7. 下一步建议

进入：

M8.7 Final M8 Acceptance / Module Handoff

建议目标：

汇总 M8.1-M8.6 所有 CLI
汇总所有验收 SQL
汇总所有 runbook
生成 M8 完整交接文档
生成 M9 开启 brief

建议新增：

docs/modules/m8/18_m8_final_acceptance.md
docs/modules/m8/19_m8_handoff.md
docs/modules/m8/20_next_chat_brief_for_m9.md
sql/m8_final_acceptance.sql
8. M8.7 暂不做
不新增业务能力
不新增调度能力
不修改交易/风控数据
只做最终验收和交接
9. 新聊天开场建议
项目名称：stock_quant_v2

当前阶段：准备进入 M8.7 Final M8 Acceptance / Module Handoff。

已完成：
M8.1 Run Monitor + CLI 运维入口：PASS
M8.2 Ops Report Export Center / Runbook：PASS
M8.3 Daily Ops Orchestration / Scheduler Preparation：PASS
M8.4 Ops Hygiene / Stale Run Cleanup：PASS
M8.5 Scheduler Adapter / Manual-to-Scheduled Ops：PASS
M8.6 Ops Dashboard / Human Review Pack：PASS

当前 run 状态：
FAILED = 16
STALE = 20
SUCCESS = 115
RUNNING = 0

当前关键链路：
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

本轮目标：
收口 M8 全模块最终验收、交接文档和 M9 开启 brief。

---

# 5. 当前判定

```text
M8.6 Ops Dashboard / Human Review Pack：PASS

下一步建议进入：

M8.7 Final M8 Acceptance / Module Handoff

这一步只做 M8 总验收和交接，不新增功能。