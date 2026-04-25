# M8 CLI Runbook

项目名称：stock_quant_v2  
模块：M8.1 / M8.2  
用途：Run Monitor、Paper Chain 查询、Risk 查询、报告导出

## 1. 当前原则

M8 当前只做 CLI 运维入口和本地报告导出：

```text
不新增数据库表
不修改 Alembic
不修改交易/风控结果
不引入 FastAPI
不引入 Scheduler

2. 推荐日常顺序
2.1 自动识别最新链路
$env:M8_PORTFOLIO_ID="1"
$env:M8_RISK_PROFILE_CODE="paper_cn_a_risk3_strict_v1"
python -m stock_quant_v2.scripts.m8_query_latest_runs

复制输出中的：

powershell_env.trading_chain
powershell_env.risk_chain
2.2 查询 Paper Chain
python -m stock_quant_v2.scripts.m8_query_paper_chain

预期：

overall_status = PASS
2.3 查询 Risk Decision
python -m stock_quant_v2.scripts.m8_query_risk_decision

预期：

overall_status = PASS
2.4 查询 Target Diff
python -m stock_quant_v2.scripts.m8_query_target_diff
2.5 导出日报
$env:M8_REPORT_OUTPUT_DIR="artifacts/m8/daily_ops"
python -m stock_quant_v2.scripts.m8_export_daily_ops_report
3. 单项报告导出
3.1 Paper Chain Report
$env:M8_REPORT_OUTPUT_DIR="artifacts/m8/paper_chain"
python -m stock_quant_v2.scripts.m8_export_paper_chain_report
3.2 Portfolio Snapshot Report
$env:M8_REPORT_OUTPUT_DIR="artifacts/m8/portfolio_snapshot"
python -m stock_quant_v2.scripts.m8_export_portfolio_snapshot_report
3.3 Run Summary Report
$env:M8_RUN_ID="167"
$env:M8_REPORT_OUTPUT_DIR="artifacts/m8/run_summary"
python -m stock_quant_v2.scripts.m8_export_run_summary_report
3.4 Risk Report
$env:M8_REPORT_OUTPUT_DIR="artifacts/m8/risk"
python -m stock_quant_v2.scripts.m8_export_risk_report
4. 当前关键验收 Run
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
5. 输出目录
artifacts/m8/risk
artifacts/m8/paper_chain
artifacts/m8/portfolio_snapshot
artifacts/m8/run_summary
artifacts/m8/daily_ops
6. 完成判定

M8 CLI 当前日常检查通过条件：

m8_query_latest_runs overall_status = PASS
m8_query_paper_chain overall_status = PASS
m8_query_risk_decision overall_status = PASS
m8_query_target_diff overall_status = PASS
m8_export_daily_ops_report overall_status = PASS

---