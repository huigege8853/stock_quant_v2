# M8.1 Acceptance｜Run Monitor + CLI 运维入口

项目名称：stock_quant_v2  
模块：M8.1 Run Monitor + CLI 运维入口  
状态：PASS

## 1. 验收结论

M8.1 已完成第一批与第二批 CLI 运维查询能力。

最终结论：

```text
M8.1 Run Monitor + CLI 运维入口：PASS

2. 已完成 CLI
m8_query_run
m8_query_latest_runs
m8_query_paper_chain
m8_query_portfolio_snapshot
m8_query_risk_profile
m8_query_risk_decision
m8_query_target_diff
m8_export_risk_report
3. 已完成能力
3.1 Run 查询

支持按 M8_RUN_ID 查询：

ops_run
ops_run_step
ops_run_metric_snapshot
ops_run_series_snapshot
ops_run_artifact

已验证：

M8_RUN_ID = 167
run_type = RISK3
status = SUCCESS
3.2 Risk Profile 查询

已验证：

M8_RISK_PROFILE_CODE = paper_cn_a_risk3_strict_v1
profile_count = 1

Profile 规则：

R007_INDUSTRY_MAX_WEIGHT
R009_MARKET_RISK_SWITCH
R011_LIQUIDITY_FILTER
3.3 Risk Decision 查询

已验证：

portfolio_id = 1
source_target_run_id = 160
adjusted_target_run_id = 166
risk_run_id = 167

decision_count = 90
pass_count = 60
warn_count = 0
reject_count = 30
adjust_count = 0
overall_status = PASS

原因码：

R007_MISSING_INDUSTRY = REJECT 30
R009_MARKET_RISK_SWITCH_SKIPPED_AFTER_REJECT = PASS 30
R011_LIQUIDITY_FILTER_SKIPPED_AFTER_REJECT = PASS 30
3.4 Portfolio Snapshot 查询

已验证：

portfolio_id = 1
snapshot_run_id = 154
snapshot_date = 2026-04-23
holding_count = 30
total_equity = 10032531.13334439
snapshot_exists = true
3.5 Paper Chain 查询

已验证链路：

target_run_id = 160
order_run_id = 146
fill_run_id = 147
position_run_id = 153
snapshot_run_id = 154

查询结果：

target_exists = true
order_exists = true
fill_exists = true
position_exists = true
snapshot_exists = true
overall_status = PASS
3.6 Latest Runs 自动识别

已验证自动识别：

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

并输出可复制 PowerShell 环境变量。

3.7 Target Diff 查询

已验证 strict profile target diff：

source_target_run_id = 160
adjusted_target_run_id = 166
risk_run_id = 167

source target_count = 30
source target_quantity_total = 605400.00000000
source target_amount_total = 9794717.00000000

adjusted target_count = 30
adjusted rejected_target_count = 30
adjusted target_quantity_total = 0
adjusted target_amount_total = 0

target_quantity_delta = -605400.00000000
target_amount_delta = -9794717.00000000

归因：

reject_count = 30
reason_code = R007_MISSING_INDUSTRY
final_decision_type = REJECT
3.8 Risk Report 导出

已验证导出：

artifacts/m8/risk/m8_risk_report_p1_src160_adj166.json
artifacts/m8/risk/m8_risk_report_p1_src160_adj166_decisions.csv
artifacts/m8/risk/m8_risk_report_p1_src160_adj166.md

导出结果：

overall_status = PASS
4. 本阶段原则

M8.1 当前只做只读查询与本地报告导出：

不新增数据库表
不修改 Alembic
不改 M7 风控结果
不改交易域数据
不引入 FastAPI
不引入 Scheduler
5. 验收 SQL

对应 SQL：

sql/m8_1_acceptance.sql

验收项覆盖：

run exists
risk profile exists
risk profile rule count
source target exists
adjusted target exists
adjusted target zero
risk decision count
risk reject count
R007 reject count
paper order exists
paper fill exists
paper position exists
paper snapshot exists
target diff strict zero
6. 最终状态
M8.1 Run Monitor + CLI 运维入口：PASS

---