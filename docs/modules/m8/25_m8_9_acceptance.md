# M8.9 Acceptance｜Excel Export Center

项目名称：stock_quant_v2  
模块：M8.9 Excel 导出中心  
状态：PASS

## 1. 验收结论

M8.9 已完成 Excel 导出中心第一版。

最终结论：

```text
M8.9 Excel 导出中心：PASS
2. 本阶段目标

补齐 M8 报告导出中心中的 Excel 产物能力。

当前支持：

Human Review Pack Excel
Daily Ops Excel
Ops Summary Excel

当前不做：

不改数据库
不触发交易链
不自动下单
不自动调仓
3. 已完成 CLI
m8_export_excel_human_review_pack
m8_export_excel_daily_ops
m8_export_excel_ops_summary
4. 验收命令
$env:M8_PORTFOLIO_ID="1"
$env:M8_RISK_PROFILE_CODE="paper_cn_a_risk3_strict_v1"
$env:M8_EXCEL_OUTPUT_DIR="artifacts/m8/excel"

python -m stock_quant_v2.scripts.m8_export_excel_human_review_pack
python -m stock_quant_v2.scripts.m8_export_excel_daily_ops
python -m stock_quant_v2.scripts.m8_export_excel_ops_summary
5. 验收结果
m8_export_excel_human_review_pack：overall_status = PASS
m8_export_excel_daily_ops：overall_status = PASS
m8_export_excel_ops_summary：命令执行完成
M8.9 Excel artifact check：PASS

说明：

ops_kpi_status = WARN
daily_ops_status = WARN

这是 strict profile 的预期人工复核提示，不是 Excel 导出失败。

6. 输出文件
artifacts/m8/excel/m8_human_review_pack_p1_2026-04-23.xlsx
artifacts/m8/excel/m8_daily_ops_p1_2026-04-23.xlsx
artifacts/m8/excel/m8_ops_summary_p1_2026-04-23.xlsx
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
9. 验收 SQL
sql/m8_9_acceptance.sql

覆盖：

RUNNING 清零
run status counts
latest trading chain data
snapshot KPI
risk decision rows
strict reject count
strict no WARN / ADJUST
adjusted target zero
risk profile exists
10. 最终状态
M8.9 Excel 导出中心：PASS