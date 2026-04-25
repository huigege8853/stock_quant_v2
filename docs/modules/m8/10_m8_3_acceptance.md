# M8.3 Acceptance｜Daily Ops Orchestration / Scheduler Preparation

项目名称：stock_quant_v2  
模块：M8.3 Daily Ops Orchestration / Scheduler Preparation  
状态：PASS

## 1. 验收结论

M8.3 已完成“手动每日运维编排检查”第一版。

当前不引入真实 Scheduler，只提供手动 CLI：

```text
m8_daily_ops_check
m8_daily_ops_plan
m8_ops_status_summary

最终结论：

M8.3 Daily Ops Orchestration / Scheduler Preparation：PASS
2. 当前边界
不引入 APScheduler
不引入 cron
不引入 Windows Task Scheduler
不新增数据库表
不修改 Alembic
不自动触发交易链
只做每日运维检查、计划输出、状态汇总
3. 关键验收链路
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
4. Daily Ops Check 验收

命令：

$env:M8_PORTFOLIO_ID="1"
$env:M8_RISK_PROFILE_CODE="paper_cn_a_risk3_strict_v1"
$env:M8_EXPORT_DAILY_REPORT="false"
python -m stock_quant_v2.scripts.m8_daily_ops_check

结果：

latest_runs_pass = PASS
paper_chain_pass = PASS
risk_decision_pass = PASS
target_diff_pass = PASS
snapshot_exists = PASS
failures = []
overall_status = WARN

说明：

WARN 是预期结果。
strict profile 下存在 30 个 REJECT，并且 source target 到 adjusted target 被清零。
这属于风控结果，不属于系统失败。

Warnings：

RISK_REJECT_EXISTS
TARGET_QUANTITY_DIFF_EXISTS
TARGET_AMOUNT_DIFF_EXISTS
5. Daily Ops Check + Report Export 验收

命令：

$env:M8_PORTFOLIO_ID="1"
$env:M8_RISK_PROFILE_CODE="paper_cn_a_risk3_strict_v1"
$env:M8_EXPORT_DAILY_REPORT="true"
$env:M8_REPORT_OUTPUT_DIR="artifacts/m8/daily_ops"
python -m stock_quant_v2.scripts.m8_daily_ops_check

结果：

daily_report_export_pass = PASS
daily_report.overall_status = PASS
overall_status = WARN
failures = []

输出：

artifacts/m8/daily_ops/m8_daily_ops_p1_2026-04-23.json
artifacts/m8/daily_ops/m8_daily_ops_p1_2026-04-23.md
6. Daily Ops Plan 验收

命令：

$env:M8_PORTFOLIO_ID="1"
$env:M8_RISK_PROFILE_CODE="paper_cn_a_risk3_strict_v1"
python -m stock_quant_v2.scripts.m8_daily_ops_plan

结果：

check_status = WARN
overall_status = PASS

动作全部 READY：

QUERY_LATEST_RUNS
QUERY_PAPER_CHAIN
QUERY_RISK_DECISION
QUERY_TARGET_DIFF
EXPORT_DAILY_OPS_REPORT
7. Ops Status Summary 验收

命令：

$env:M8_PORTFOLIO_ID="1"
$env:M8_RISK_PROFILE_CODE="paper_cn_a_risk3_strict_v1"
python -m stock_quant_v2.scripts.m8_ops_status_summary

结果：

latest_trading_chain_complete = true
latest_risk_chain_complete = true
recent_run_count = 20
overall_status = PASS
8. 重要观察

ops_status_summary 中仍存在一些历史 RUNNING run，例如部分 PAPER_TRADING placeholder run。

当前 M8.3 仍判定 PASS，原因是：

latest trading chain 完整
latest risk chain 完整
核心 paper/risk/target diff 检查通过
历史 RUNNING run 不阻断当前 M8.3

后续可以在 M8.4 或 M8 Ops Hygiene 中补：

m8_ops_run_hygiene_check
m8_mark_stale_runs

用于识别和处理长期 RUNNING 的占位 run。

9. 验收 SQL
sql/m8_3_acceptance.sql

覆盖：

latest target rows
latest order rows
latest fill rows
latest position rows
latest snapshot rows
snapshot total equity
risk decision rows
risk reject count
risk warn count
risk adjust count
strict adjusted target zero
risk run success
risk profile exists
10. 最终状态
M8.3 Daily Ops Orchestration / Scheduler Preparation：PASS