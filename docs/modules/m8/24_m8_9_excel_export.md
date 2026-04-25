# M8.9 Excel Export Center

项目名称：stock_quant_v2  
模块：M8.9 Excel 导出中心  
状态：待验收

## 1. 目标

补齐 M8 报告导出中心中的 Excel 产物能力。

## 2. 已新增 CLI

```text
m8_export_excel_human_review_pack
m8_export_excel_daily_ops
m8_export_excel_ops_summary

# M8.9 Excel Export Center

项目名称：stock_quant_v2  
模块：M8.9 Excel 导出中心  
状态：待验收

## 1. 目标

补齐 M8 报告导出中心中的 Excel 产物能力。

## 2. 已新增 CLI

```text
m8_export_excel_human_review_pack
m8_export_excel_daily_ops
m8_export_excel_ops_summary
3. 输出目录
artifacts/m8/excel
4. 输出文件
m8_human_review_pack_p1_2026-04-23.xlsx
m8_daily_ops_p1_2026-04-23.xlsx
m8_ops_summary_p1_2026-04-23.xlsx
5. 当前边界
不改数据库
不触发交易链
不自动下单
不自动调仓
6. 验收命令
$env:M8_PORTFOLIO_ID="1"
$env:M8_RISK_PROFILE_CODE="paper_cn_a_risk3_strict_v1"
$env:M8_EXCEL_OUTPUT_DIR="artifacts/m8/excel"

python -m stock_quant_v2.scripts.m8_export_excel_human_review_pack
python -m stock_quant_v2.scripts.m8_export_excel_daily_ops
python -m stock_quant_v2.scripts.m8_export_excel_ops_summary
7. 通过标准
三个 CLI 均 overall_status = PASS
三个 .xlsx 文件均存在