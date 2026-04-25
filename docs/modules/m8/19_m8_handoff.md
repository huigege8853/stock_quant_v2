M8 Handoff

项目名称：stock_quant_v2  
模块：M8 运维域  
状态：已完成

## 1. 交接结论

M8 已完成。当前系统已经具备：

```text
Run 查询
Paper Chain 查询
Risk 查询
Target Diff 查询
Portfolio Snapshot 查询
报告导出
Daily Ops 检查
Run 状态治理
Scheduler Adapter
Human Review Pack

M8 最终状态：

PASS
2. 当前生产参考链路
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
3. 当前 Run 状态
FAILED = 16
STALE = 20
SUCCESS = 115
RUNNING = 0
4. 当前关键判断
M8 运维健康：PASS
Scheduler Adapter：PASS
Human Review Pack：PASS
Daily Ops：WARN

Daily Ops = WARN 的原因是 strict profile 下风控拒绝 30 个目标，这是预期结果。

5. 日常运维推荐命令
5.1 查询 KPI
$env:M8_PORTFOLIO_ID="1"
$env:M8_RISK_PROFILE_CODE="paper_cn_a_risk3_strict_v1"
python -m stock_quant_v2.scripts.m8_query_ops_kpi
5.2 执行 daily ops entrypoint
$env:M8_PORTFOLIO_ID="1"
$env:M8_RISK_PROFILE_CODE="paper_cn_a_risk3_strict_v1"
$env:M8_REPORT_OUTPUT_DIR="artifacts/m8/daily_ops"
$env:M8_FAIL_ON_WARN="false"
python -m stock_quant_v2.scripts.m8_daily_ops_entrypoint
5.3 导出人工复核包
$env:M8_HUMAN_REVIEW_OUTPUT_DIR="artifacts/m8/human_review"
python -m stock_quant_v2.scripts.m8_export_human_review_pack
python -m stock_quant_v2.scripts.m8_export_ops_summary_pack
5.4 Run hygiene 检查
python -m stock_quant_v2.scripts.m8_ops_run_hygiene_check
6. 调度模板

已生成：

artifacts/m8/scheduler/stock_quant_v2_m8_daily_ops.ps1
artifacts/m8/scheduler/stock_quant_v2_m8_daily_ops.xml
artifacts/m8/scheduler/stock_quant_v2_m8_daily_ops_README.md

已手动验证：

powershell -NoProfile -ExecutionPolicy Bypass -File "artifacts/m8/scheduler/stock_quant_v2_m8_daily_ops.ps1"

结果：

scheduler_exit_code = 0
overall_status = PASS
M8.5 daily ops entrypoint completed.

当前不建议自动启用 Windows Task Scheduler。后续可在人工确认后注册。

7. M8 不包含的内容
真实自动交易
券商接口
自动下单
自动调仓
FastAPI Dashboard
自动注册定时任务
自动清理 stale run
8. 进入 M9 的建议

M9 建议进入：

M9 AI-Assisted Research & Ops Intelligence

优先方向：

1. 对 M8 human review pack 做 AI 解读
2. 对 risk decision / target diff 做自动摘要
3. 对 daily ops WARN / FAIL 做原因归纳
4. 对 M2-M8 数据水位生成自然语言日报
5. 对策略表现、风控结果、交易链路生成复核建议
9. M9 前置条件
M7 Paper Trading + Risk：PASS
M8 Ops：PASS
RUNNING = 0
daily ops entrypoint 可执行
human review pack 可导出

当前全部满足。