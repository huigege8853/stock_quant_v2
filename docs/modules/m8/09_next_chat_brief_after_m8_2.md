# M8.2 Next Chat Brief

项目名称：stock_quant_v2

当前阶段：M8.2 Ops Report Export Center / Runbook 已完成。

## 1. 当前结论

```text
M8.1 Run Monitor + CLI 运维入口：PASS
M8.2 Ops Report Export Center / Runbook：PASS

2. M8.1 已完成 CLI
m8_query_run
m8_query_latest_runs
m8_query_paper_chain
m8_query_portfolio_snapshot
m8_query_risk_profile
m8_query_risk_decision
m8_query_target_diff
m8_export_risk_report
3. M8.2 已完成 CLI
m8_export_paper_chain_report
m8_export_portfolio_snapshot_report
m8_export_run_summary_report
m8_export_daily_ops_report
4. 已完成 Runbook
docs/runbooks/m8_cli_runbook.md
docs/runbooks/m8_troubleshooting.md
5. 关键验收 Run
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
6. 已验证结果
m8_query_latest_runs：PASS
m8_query_paper_chain：PASS
m8_query_risk_decision：PASS
m8_query_target_diff：PASS
m8_export_risk_report：PASS

m8_export_paper_chain_report：PASS
m8_export_portfolio_snapshot_report：PASS
m8_export_run_summary_report：PASS
m8_export_daily_ops_report：PASS
7. 当前边界
只做 CLI 查询与本地报告导出
不新增数据库表
不修改 Alembic
不写入 ops_run_artifact
不引入 FastAPI
不引入 Scheduler
8. 下一步建议

进入 M8.3：

M8.3 Daily Ops Orchestration / Scheduler Preparation

建议优先做：

m8_daily_ops_check
m8_daily_ops_plan
m8_daily_ops_runbook
m8_ops_status_summary

M8.3 先不要直接上真实 Scheduler，先做“可手动运行的每日编排检查”：

1. 自动识别 latest runs
2. 检查 M2 / M3 / M4 / M7 / M8 的关键水位和状态
3. 检查 paper chain
4. 检查 risk decision
5. 检查 target diff
6. 导出 daily ops report
7. 输出下一步建议
9. M8.3 暂不做
暂不引入 APScheduler / cron
暂不做 FastAPI
暂不新增 ops scheduler 表
暂不自动触发交易链
10. 新聊天开场建议
项目名称：stock_quant_v2

当前阶段：准备进入 M8.3 Daily Ops Orchestration / Scheduler Preparation。

已完成：
M8.1 Run Monitor + CLI 运维入口：PASS
M8.2 Ops Report Export Center / Runbook：PASS

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
建立 M8.3 每日运维编排检查入口，先做手动 CLI，不引入真实 Scheduler。

---

# 5. 当前判定

```text
M8.2 Ops Report Export Center / Runbook：PASS