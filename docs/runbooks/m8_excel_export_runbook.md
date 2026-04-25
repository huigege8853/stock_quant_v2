# M8 Excel Export Runbook

项目名称：stock_quant_v2  
模块：M8.9 Excel 导出中心

## 1. 当前目标

M8.9 用于把 M8 运维数据导出为 Excel 文件。

当前支持：

```text
Human Review Pack Excel
Daily Ops Excel
Ops Summary Excel

当前不做：

不改数据库
不触发交易链
不自动下单
不自动调仓
2. 导出命令
$env:M8_PORTFOLIO_ID="1"
$env:M8_RISK_PROFILE_CODE="paper_cn_a_risk3_strict_v1"
$env:M8_EXCEL_OUTPUT_DIR="artifacts/m8/excel"

python -m stock_quant_v2.scripts.m8_export_excel_human_review_pack
python -m stock_quant_v2.scripts.m8_export_excel_daily_ops
python -m stock_quant_v2.scripts.m8_export_excel_ops_summary
3. 输出文件
artifacts/m8/excel/m8_human_review_pack_p1_2026-04-23.xlsx
artifacts/m8/excel/m8_daily_ops_p1_2026-04-23.xlsx
artifacts/m8/excel/m8_ops_summary_p1_2026-04-23.xlsx
4. strict profile 说明

当前 profile：

paper_cn_a_risk3_strict_v1

会产生：

risk_reject_count = 30
target_quantity_delta = -605400.00000000
target_amount_delta = -9794717.00000000

这是预期风控结果，不是导出失败。

5. 通过条件
三个 Excel 导出脚本 overall_status = PASS
三个 xlsx 文件均存在