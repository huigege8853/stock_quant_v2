# M8.4 Next Chat Brief

项目名称：stock_quant_v2

当前阶段：M8.4 Ops Hygiene / Stale Run Cleanup 已完成。

## 1. 当前结论

```text
M8.1 Run Monitor + CLI 运维入口：PASS
M8.2 Ops Report Export Center / Runbook：PASS
M8.3 Daily Ops Orchestration / Scheduler Preparation：PASS
M8.4 Ops Hygiene / Stale Run Cleanup：PASS
2. M8.4 已完成 CLI
m8_ops_run_hygiene_check
m8_query_stale_runs
m8_mark_stale_runs_dry_run
m8_mark_stale_runs_apply
3. Run 状态治理结果

清理前：

FAILED = 16
RUNNING = 46
SUCCESS = 89

清理后：

FAILED = 16
STALE = 20
SUCCESS = 115
RUNNING = 0
4. 当前关键链路
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
5. 当前验证结果
m8_ops_run_hygiene_check = PASS
m8_ops_status_summary = PASS
m8_daily_ops_check = WARN

说明：

daily_ops_check 的 WARN 是 strict profile 预期。
risk decision 存在 30 个 REJECT。
adjusted target 被清零。
failures = []
6. 当前边界
不新增数据库表
不修改 Alembic
不接真实 Scheduler
不自动触发交易链
仅完成 ops_run 历史状态治理
7. 下一步建议

进入：

M8.5 Scheduler Adapter / Manual-to-Scheduled Ops

建议先做：

m8_scheduler_plan
m8_scheduler_health_check
m8_windows_task_template
m8_daily_ops_entrypoint
docs/runbooks/m8_scheduler_runbook.md

M8.5 目标：

把当前手动 daily ops check / daily ops report 流程封装成稳定入口
准备 Windows Task Scheduler / cron / APScheduler 的接入方案
先生成计划和模板，不直接启用真实定时任务
8. M8.5 暂不做
暂不自动跑交易链
暂不自动应用风控结果
暂不自动清理 stale run
暂不自动下单
9. 新聊天开场建议
项目名称：stock_quant_v2

当前阶段：准备进入 M8.5 Scheduler Adapter / Manual-to-Scheduled Ops。

已完成：
M8.1 Run Monitor + CLI 运维入口：PASS
M8.2 Ops Report Export Center / Runbook：PASS
M8.3 Daily Ops Orchestration / Scheduler Preparation：PASS
M8.4 Ops Hygiene / Stale Run Cleanup：PASS

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
建立 M8.5 Scheduler Adapter，先生成 daily ops entrypoint、scheduler plan、Windows Task Scheduler 模板和 runbook，不直接启用真实定时任务。

---

# 4. 当前判定

```text
M8.4 Ops Hygiene / Stale Run Cleanup：PASS

下一步建议进入：

M8.5 Scheduler Adapter / Manual-to-Scheduled Ops

先把 M8.3 的 daily ops 手动流程包装成稳定入口和调度模板，但不要急着自动触发交易链。