M8.5 Next Chat Brief

项目名称：stock_quant_v2

当前阶段：M8.5 Scheduler Adapter / Manual-to-Scheduled Ops 已完成。

## 1. 当前结论

```text
M8.1 Run Monitor + CLI 运维入口：PASS
M8.2 Ops Report Export Center / Runbook：PASS
M8.3 Daily Ops Orchestration / Scheduler Preparation：PASS
M8.4 Ops Hygiene / Stale Run Cleanup：PASS
M8.5 Scheduler Adapter / Manual-to-Scheduled Ops：PASS
2. M8.5 已完成 CLI
m8_scheduler_health_check
m8_scheduler_plan
m8_daily_ops_entrypoint
m8_windows_task_template
3. 已完成模板
artifacts/m8/scheduler/stock_quant_v2_m8_daily_ops.ps1
artifacts/m8/scheduler/stock_quant_v2_m8_daily_ops.xml
artifacts/m8/scheduler/stock_quant_v2_m8_daily_ops_README.md
4. 手动执行结果
powershell -NoProfile -ExecutionPolicy Bypass -File "artifacts/m8/scheduler/stock_quant_v2_m8_daily_ops.ps1"

scheduler_exit_code = 0
overall_status = PASS
M8.5 daily ops entrypoint completed.
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
snapshot_date = 2026-04-23
6. 当前 Run 状态
FAILED = 16
STALE = 20
SUCCESS = 115
RUNNING = 0
7. 当前边界
不自动触发交易链
不自动应用风控结果
不自动清理 stale run
不自动下单
不自动注册 Windows Task Scheduler
8. 下一步建议

进入：

M8.6 Ops Dashboard / Human Review Pack

建议优先做：

m8_export_human_review_pack
m8_query_ops_kpi
m8_export_ops_summary_pack
docs/runbooks/m8_human_review_runbook.md

目标：

把 M8.1-M8.5 的查询、日报、风控、链路、scheduler health 汇总成一个人工复核包。
9. 暂不做
暂不接真实自动交易
暂不注册真实定时任务
暂不做 FastAPI Dashboard
暂不自动改交易数据
10. 新聊天开场建议
项目名称：stock_quant_v2

当前阶段：准备进入 M8.6 Ops Dashboard / Human Review Pack。

已完成：
M8.1 Run Monitor + CLI 运维入口：PASS
M8.2 Ops Report Export Center / Runbook：PASS
M8.3 Daily Ops Orchestration / Scheduler Preparation：PASS
M8.4 Ops Hygiene / Stale Run Cleanup：PASS
M8.5 Scheduler Adapter / Manual-to-Scheduled Ops：PASS

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
建立 M8.6 人工复核包，把 daily ops、scheduler health、paper chain、risk decision、target diff、snapshot 和 run hygiene 汇总成统一报告。

---

# 5. 当前判定

```text
M8.5 Scheduler Adapter / Manual-to-Scheduled Ops：PASS

下一步建议进入：

M8.6 Ops Dashboard / Human Review Pack

先做人工复核包，不急着启用真实定时任务。