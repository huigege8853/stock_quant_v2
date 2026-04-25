# M8 Enhanced Handoff

项目名称：stock_quant_v2  
模块：M8 接口、调度与运维域增强版  
状态：已完成

## 1. 交接结论

M8 增强版已经完成，具备最小可长期维护、可查询、可导出、可调度、可审计的运维能力。

```text
M8 接口、调度与运维域增强版：PASS
2. 当前关键链路
portfolio_id = 1
target_run_id = 160
order_run_id = 146
fill_run_id = 147
position_run_id = 153
snapshot_run_id = 154
risk_run_id = 167
source_target_run_id = 160
adjusted_target_run_id = 166
risk_profile_code = paper_cn_a_risk3_strict_v1
snapshot_date = 2026-04-23
3. 当前运行状态
RUNNING = 0
STALE = 20
FAILED = 16
SUCCESS = 115

scheduler_exit_code = 0
highest_alert_level = WARN
api_route_count = 32
failures = []
4. 日常运维推荐命令
4.1 启动前检查
python -m stock_quant_v2.scripts.m8_env_check
python -m stock_quant_v2.scripts.m8_startup_check
4.2 Daily Ops
$env:M8_PORTFOLIO_ID="1"
$env:M8_RISK_PROFILE_CODE="paper_cn_a_risk3_strict_v1"
$env:M8_REPORT_OUTPUT_DIR="artifacts/m8/daily_ops"
$env:M8_FAIL_ON_WARN="false"

python -m stock_quant_v2.scripts.m8_daily_ops_entrypoint
4.3 人工复核包
python -m stock_quant_v2.scripts.m8_export_human_review_pack
python -m stock_quant_v2.scripts.m8_export_ops_summary_pack
4.4 Excel 导出
python -m stock_quant_v2.scripts.m8_export_excel_human_review_pack
python -m stock_quant_v2.scripts.m8_export_excel_daily_ops
python -m stock_quant_v2.scripts.m8_export_excel_ops_summary
4.5 Alert / Log / Audit
python -m stock_quant_v2.scripts.m8_ops_alert_check
python -m stock_quant_v2.scripts.m8_query_ops_logs
python -m stock_quant_v2.scripts.m8_export_alert_report
python -m stock_quant_v2.scripts.m8_export_audit_snapshot
4.6 Scheduler 注册前检查
python -m stock_quant_v2.scripts.m8_scheduler_registration_check
python -m stock_quant_v2.scripts.m8_enhanced_final_check
5. API 启动
uvicorn stock_quant_v2.api.app:app --host 127.0.0.1 --port 8008 --reload

API 文档：

http://127.0.0.1:8008/docs
http://127.0.0.1:8008/openapi.json
6. Scheduler 手动注册

当前不自动注册。人工确认后可执行：

schtasks /Create /TN "stock_quant_v2_m8_daily_ops" /XML "artifacts\m8\scheduler\stock_quant_v2_m8_daily_ops.xml"
schtasks /Change /TN "stock_quant_v2_m8_daily_ops" /ENABLE
7. 进入 M9 的建议

M9 建议进入：

M9 AI-Assisted Research & Ops Intelligence

优先目标：

读取 M8 human review pack
读取 M8 daily ops report
读取 M8 alert / audit / env / scheduler registration pack
生成自然语言摘要
生成风险解释
生成人工复核建议
生成研究与运维洞察
8. M9 前置条件
M7 Paper Trading + Risk：PASS
M8 Enhanced Ops：PASS
RUNNING = 0
scheduler_exit_code = 0
highest_alert_level != CRITICAL
human review pack 可导出
daily ops entrypoint 可执行
API 可启动
OpenAPI 可导出
Excel 可导出
alert / audit / startup report 可导出

当前全部满足。