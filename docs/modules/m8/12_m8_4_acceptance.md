# M8.4 Acceptance｜Ops Hygiene / Stale Run Cleanup

项目名称：stock_quant_v2  
模块：M8.4 Ops Hygiene / Stale Run Cleanup  
状态：PASS

## 1. 验收结论

M8.4 已完成历史 RUNNING run 治理。

最终结论：

```text
M8.4 Ops Hygiene / Stale Run Cleanup：PASS

2. 本阶段目标
识别长期 RUNNING run
区分有业务输出和无业务输出
先 dry-run，再 apply
默认保护 latest trading/risk chain
最终清理历史 RUNNING 状态
3. 已完成 CLI
m8_ops_run_hygiene_check
m8_query_stale_runs
m8_mark_stale_runs_dry_run
m8_mark_stale_runs_apply
4. 清理前状态

M8.3 阶段发现：

FAILED = 16
RUNNING = 46
SUCCESS = 89

其中部分 latest trading chain run 仍为 RUNNING，但已有业务输出。

5. 第一批清理：latest protected chain

处理 run：

146
147
153
154

处理结果：

146 → SUCCESS
147 → SUCCESS
153 → SUCCESS
154 → SUCCESS
applied_count = 4
overall_status = PASS

原因：

这些 run 是 latest trading chain 的有效组成部分，且均有业务输出。
6. 第二批清理：有业务输出的历史 run

处理 run：

116,117,119,124,125,126,131,132,133,134,136,137,138,139,141,142,143,144

处理结果：

applied_count = 18
new_status = SUCCESS
overall_status = PASS

规则：

RUNNING_WITH_OUTPUT_ROWS → SUCCESS
7. 第三批清理：无业务输出的历史 run

处理 run：

6,19,21,35,36,37,40,118,120,121,122,123,127,128,129,130,135,140

处理结果：

applied_count = 18
new_status = STALE
overall_status = PASS

规则：

RUNNING_WITHOUT_OUTPUT_ROWS → STALE
8. 清理后状态

最终 m8_ops_run_hygiene_check：

FAILED = 16
STALE = 20
SUCCESS = 115
RUNNING = 0
candidate_count = 0
protected_running_count = 0
overall_status = PASS
9. Ops Status Summary

最终 m8_ops_status_summary：

latest_trading_chain_complete = true
latest_risk_chain_complete = true
overall_status = PASS
10. Daily Ops Check

最终 m8_daily_ops_check：

latest_runs_pass = PASS
paper_chain_pass = PASS
risk_decision_pass = PASS
target_diff_pass = PASS
snapshot_exists = PASS
failures = []
overall_status = WARN

说明：

WARN 是 strict profile 的预期结果。
risk decision 存在 30 个 REJECT。
source target 到 adjusted target 被清零。
这不是系统失败。
11. 当前关键链路
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
12. 验收 SQL
sql/m8_4_acceptance.sql

覆盖：

RUNNING 清零
STALE 数量
SUCCESS 数量
latest trading chain run 状态
placeholder STALE 状态
latest trading chain 业务数据仍存在
latest risk chain 业务数据仍存在
13. 最终状态
M8.4 Ops Hygiene / Stale Run Cleanup：PASS