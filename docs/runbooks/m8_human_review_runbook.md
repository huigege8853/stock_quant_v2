# M8 Human Review Runbook

项目名称：stock_quant_v2  
模块：M8.6 Ops Dashboard / Human Review Pack

## 1. 当前目标

M8.6 不是 FastAPI Dashboard。

当前只做人工复核包：

```text
m8_query_ops_kpi
m8_export_human_review_pack
m8_export_ops_summary_pack

2. 查询 KPI
$env:M8_PORTFOLIO_ID="1"
$env:M8_RISK_PROFILE_CODE="paper_cn_a_risk3_strict_v1"

python -m stock_quant_v2.scripts.m8_query_ops_kpi

预期：

overall_status = WARN
running_count = 0
scheduler_exit_code = 0
hygiene_status = PASS
3. 导出人工复核包
$env:M8_HUMAN_REVIEW_OUTPUT_DIR="artifacts/m8/human_review"

python -m stock_quant_v2.scripts.m8_export_human_review_pack

输出：

m8_human_review_pack_p1_2026-04-23.json
m8_human_review_pack_p1_2026-04-23.md
m8_human_review_pack_p1_2026-04-23_kpi.csv
m8_human_review_pack_p1_2026-04-23_risk_reasons.csv
m8_human_review_pack_p1_2026-04-23_run_status.csv
4. 导出 Ops Summary Pack
python -m stock_quant_v2.scripts.m8_export_ops_summary_pack

输出：

m8_ops_summary_pack_p1_2026-04-23.json
m8_ops_summary_pack_p1_2026-04-23.md
m8_ops_summary_pack_p1_2026-04-23_recent_runs.csv
5. 人工复核重点
1. total_equity 是否合理
2. holding_count 是否合理
3. order/fill/position/snapshot 数量是否匹配
4. risk reject 是否为预期
5. target diff 是否为预期
6. scheduler_exit_code 是否为 0
7. RUNNING 是否为 0
8. failures 是否为空
6. strict profile 说明

当前 paper_cn_a_risk3_strict_v1 下：

risk_reject_count = 30
target_quantity_delta = -605400
target_amount_delta = -9794717

这是预期风控结果，不是系统失败。

7. 通过条件
m8_query_ops_kpi = WARN 或 PASS
m8_export_human_review_pack = PASS
m8_export_ops_summary_pack = PASS
RUNNING = 0
failures = []

# 5. M8.6 验收标准

跑完 3 个脚本后，如果满足：

```text id="j1bsvf"
m8_query_ops_kpi：WARN 或 PASS
m8_export_human_review_pack：PASS
m8_export_ops_summary_pack：PASS
human review 文件全部生成

则可判定：

M8.6 Ops Dashboard / Human Review Pack：PASS