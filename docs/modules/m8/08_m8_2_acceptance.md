# M8.2 Acceptance｜Ops Report Export Center / Runbook

项目名称：stock_quant_v2  
模块：M8.2 Ops Report Export Center / Runbook  
状态：PASS

## 1. 验收结论

M8.2 已完成基于 M8.1 查询层的报告导出中心第一版。

最终结论：

```text
M8.2 Ops Report Export Center / Runbook：PASS

2. 已完成导出 CLI
m8_export_paper_chain_report
m8_export_portfolio_snapshot_report
m8_export_run_summary_report
m8_export_daily_ops_report
3. 已完成 Runbook
docs/runbooks/m8_cli_runbook.md
docs/runbooks/m8_troubleshooting.md
4. 当前验收链路
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
5. Paper Chain Report 验收

命令：

$env:M8_PORTFOLIO_ID="1"
$env:M8_TARGET_RUN_ID="160"
$env:M8_ORDER_RUN_ID="146"
$env:M8_FILL_RUN_ID="147"
$env:M8_POSITION_RUN_ID="153"
$env:M8_SNAPSHOT_RUN_ID="154"
$env:M8_REPORT_OUTPUT_DIR="artifacts/m8/paper_chain"
python -m stock_quant_v2.scripts.m8_export_paper_chain_report

结果：

overall_status = PASS
order_rows = 28
fill_rows = 28
position_rows = 30
snapshot_rows = 1

输出文件：

artifacts/m8/paper_chain/m8_paper_chain_p1_t160_o146_f147_p153_s154.json
artifacts/m8/paper_chain/m8_paper_chain_p1_t160_o146_f147_p153_s154.md
artifacts/m8/paper_chain/m8_paper_chain_p1_t160_o146_f147_p153_s154_targets.csv
artifacts/m8/paper_chain/m8_paper_chain_p1_t160_o146_f147_p153_s154_orders.csv
artifacts/m8/paper_chain/m8_paper_chain_p1_t160_o146_f147_p153_s154_fills.csv
artifacts/m8/paper_chain/m8_paper_chain_p1_t160_o146_f147_p153_s154_positions.csv
artifacts/m8/paper_chain/m8_paper_chain_p1_t160_o146_f147_p153_s154_snapshots.csv
6. Portfolio Snapshot Report 验收

命令：

$env:M8_REPORT_OUTPUT_DIR="artifacts/m8/portfolio_snapshot"
python -m stock_quant_v2.scripts.m8_export_portfolio_snapshot_report

结果：

overall_status = PASS

输出文件：

artifacts/m8/portfolio_snapshot/m8_portfolio_snapshot_p1_r154_2026-04-23.json
artifacts/m8/portfolio_snapshot/m8_portfolio_snapshot_p1_r154_2026-04-23.md
artifacts/m8/portfolio_snapshot/m8_portfolio_snapshot_p1_r154_2026-04-23.csv
7. Run Summary Report 验收

命令：

$env:M8_RUN_ID="167"
$env:M8_REPORT_OUTPUT_DIR="artifacts/m8/run_summary"
python -m stock_quant_v2.scripts.m8_export_run_summary_report

结果：

run_id = 167
run_type = RISK3
overall_status = PASS

输出文件：

artifacts/m8/run_summary/m8_run_summary_r167.json
artifacts/m8/run_summary/m8_run_summary_r167.md
artifacts/m8/run_summary/m8_run_summary_r167_metrics.csv
artifacts/m8/run_summary/m8_run_summary_r167_artifacts.csv
8. Daily Ops Report 验收

命令：

$env:M8_PORTFOLIO_ID="1"
$env:M8_RISK_PROFILE_CODE="paper_cn_a_risk3_strict_v1"
$env:M8_REPORT_OUTPUT_DIR="artifacts/m8/daily_ops"
python -m stock_quant_v2.scripts.m8_export_daily_ops_report

结果：

latest_runs_pass = true
paper_chain_pass = true
risk_decision_pass = true
target_diff_pass = true
overall_status = PASS

输出文件：

artifacts/m8/daily_ops/m8_daily_ops_p1_2026-04-23.json
artifacts/m8/daily_ops/m8_daily_ops_p1_2026-04-23.md
9. 验收 SQL
sql/m8_2_acceptance.sql

覆盖：

target rows
order rows
fill rows
position rows
snapshot rows
fill-order join
snapshot total equity
risk run
risk decision count
risk reject count
target diff zero
risk profile
10. 本阶段边界

M8.2 当前只做本地导出与 runbook：

不新增数据库表
不修改 Alembic
不写入 ops_run_artifact
不改 M7/M8.1 结果
不引入 FastAPI
不引入 Scheduler
11. 最终状态
M8.2 Ops Report Export Center / Runbook：PASS