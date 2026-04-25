M8.3 Next Chat Brief

项目名称：stock_quant_v2

当前阶段：M8.3 Daily Ops Orchestration / Scheduler Preparation 已完成。

## 1. 当前结论

```text
M8.1 Run Monitor + CLI 运维入口：PASS
M8.2 Ops Report Export Center / Runbook：PASS
M8.3 Daily Ops Orchestration / Scheduler Preparation：PASS
2. M8.1 已完成
m8_query_run
m8_query_latest_runs
m8_query_paper_chain
m8_query_portfolio_snapshot
m8_query_risk_profile
m8_query_risk_decision
m8_query_target_diff
m8_export_risk_report
3. M8.2 已完成
m8_export_paper_chain_report
m8_export_portfolio_snapshot_report
m8_export_run_summary_report
m8_export_daily_ops_report
docs/runbooks/m8_cli_runbook.md
docs/runbooks/m8_troubleshooting.md
4. M8.3 已完成
m8_daily_ops_check
m8_daily_ops_plan
m8_ops_status_summary
docs/runbooks/m8_daily_ops_runbook.md
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
6. M8.3 验证结果
m8_daily_ops_check = WARN
m8_daily_ops_check + export = WARN, daily_report_export_pass = PASS
m8_daily_ops_plan = PASS
m8_ops_status_summary = PASS

说明：

WARN 是 strict profile 预期结果。
risk decision 存在 30 个 REJECT。
adjusted target 被清零。
failures = []
7. 当前发现

ops_status_summary 显示历史 run 状态中有：

FAILED = 16
RUNNING = 46
SUCCESS = 89

其中部分旧的 PAPER_TRADING placeholder run 仍为 RUNNING。当前不阻断 M8.3，但建议下一阶段处理。

8. 下一步建议

进入：

M8.4 Ops Hygiene / Stale Run Cleanup

优先做：

m8_ops_run_hygiene_check
m8_query_stale_runs
m8_mark_stale_runs_dry_run
m8_mark_stale_runs_apply

目标：

识别长期 RUNNING run
区分真实运行中 vs placeholder 未关闭
先 dry-run，不直接修改
必要时把陈旧 RUNNING 标记为 STALE / FAILED / SUCCESS
形成 run 状态治理规范
9. M8.4 暂不做
暂不接真实 Scheduler
暂不自动触发交易链
暂不新增数据库表
暂不改 M7 结果数据
10. 新聊天开场建议
项目名称：stock_quant_v2

当前阶段：准备进入 M8.4 Ops Hygiene / Stale Run Cleanup。

已完成：
M8.1 Run Monitor + CLI 运维入口：PASS
M8.2 Ops Report Export Center / Runbook：PASS
M8.3 Daily Ops Orchestration / Scheduler Preparation：PASS

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
建立 M8.4 run 状态治理入口，先做 stale RUNNING run 的查询与 dry-run，不直接改库。

---

# 4. 当前阶段判定

```text
M8.3 Daily Ops Orchestration / Scheduler Preparation：PASS

下一步建议进入：

M8.4 Ops Hygiene / Stale Run Cleanup

先处理你现在 ops_status_summary 里看到的历史 RUNNING = 46，尤其是旧的 PAPER_TRADING 占位 run。