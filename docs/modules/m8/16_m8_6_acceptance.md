# M8.6 Acceptance｜Ops Dashboard / Human Review Pack

项目名称：stock_quant_v2  
模块：M8.6 Ops Dashboard / Human Review Pack  
状态：PASS

## 1. 验收结论

M8.6 已完成人工复核包第一版。

最终结论：

```text
M8.6 Ops Dashboard / Human Review Pack：PASS

2. 本阶段目标

M8.6 当前不是 FastAPI Dashboard，也不是自动交易调度器。

当前只做：

m8_query_ops_kpi
m8_export_human_review_pack
m8_export_ops_summary_pack
人工复核 Markdown / JSON / CSV

当前不做：

不做 FastAPI Dashboard
不注册真实定时任务
不自动触发交易链
不自动应用风控结果
不自动改交易/风控数据
3. 已完成 CLI
m8_query_ops_kpi
m8_export_human_review_pack
m8_export_ops_summary_pack
4. Ops KPI 验收

命令：

$env:M8_PORTFOLIO_ID="1"
$env:M8_RISK_PROFILE_CODE="paper_cn_a_risk3_strict_v1"

python -m stock_quant_v2.scripts.m8_query_ops_kpi

结果：

overall_status = WARN
failures = []
running_count = 0
scheduler_exit_code = 0
scheduler_status = PASS
hygiene_status = PASS
risk_reject_count = 30
target_quantity_delta = -605400.00000000
target_amount_delta = -9794717.00000000

说明：

WARN 是 strict profile 的预期人工复核提示。
risk decision 存在 30 个 REJECT。
adjusted target 被清零。
这不是系统失败。
5. Human Review Pack 验收

命令：

$env:M8_PORTFOLIO_ID="1"
$env:M8_RISK_PROFILE_CODE="paper_cn_a_risk3_strict_v1"
$env:M8_HUMAN_REVIEW_OUTPUT_DIR="artifacts/m8/human_review"

python -m stock_quant_v2.scripts.m8_export_human_review_pack

结果：

overall_status = PASS
ops_kpi_status = WARN
daily_ops_status = WARN
scheduler_health_status = PASS
hygiene_status = PASS

输出：

artifacts/m8/human_review/m8_human_review_pack_p1_2026-04-23.json
artifacts/m8/human_review/m8_human_review_pack_p1_2026-04-23.md
artifacts/m8/human_review/m8_human_review_pack_p1_2026-04-23_kpi.csv
artifacts/m8/human_review/m8_human_review_pack_p1_2026-04-23_risk_reasons.csv
artifacts/m8/human_review/m8_human_review_pack_p1_2026-04-23_run_status.csv
6. Ops Summary Pack 验收

命令：

$env:M8_PORTFOLIO_ID="1"
$env:M8_RISK_PROFILE_CODE="paper_cn_a_risk3_strict_v1"
$env:M8_HUMAN_REVIEW_OUTPUT_DIR="artifacts/m8/human_review"

python -m stock_quant_v2.scripts.m8_export_ops_summary_pack

结果：

overall_status = PASS
ops_kpi_status = WARN

输出：

artifacts/m8/human_review/m8_ops_summary_pack_p1_2026-04-23.json
artifacts/m8/human_review/m8_ops_summary_pack_p1_2026-04-23.md
artifacts/m8/human_review/m8_ops_summary_pack_p1_2026-04-23_recent_runs.csv
7. 当前关键 KPI
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
8. 当前关键链路
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
9. 人工复核重点
1. total_equity 是否合理
2. holding_count 是否合理
3. order/fill/position/snapshot 数量是否匹配
4. risk reject 是否为预期
5. target diff 是否为预期
6. scheduler_exit_code 是否为 0
7. RUNNING 是否为 0
8. failures 是否为空
10. 验收 SQL
sql/m8_6_acceptance.sql

覆盖：

RUNNING 清零
run 状态计数
latest trading chain 数据
latest snapshot KPI
latest risk decision
strict profile REJECT
strict profile no WARN / no ADJUST
adjusted target 清零
risk profile 存在
11. 最终状态
M8.6 Ops Dashboard / Human Review Pack：PASS