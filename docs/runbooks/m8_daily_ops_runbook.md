# M8 Daily Ops Runbook

项目名称：stock_quant_v2  
模块：M8.3 Daily Ops Orchestration / Scheduler Preparation

## 1. 当前目标

M8.3 当前不是正式 Scheduler，而是每日运维编排检查入口。

原则：

```text
只做手动 CLI
不引入 APScheduler
不引入 cron
不自动触发交易链
不新增数据库表
不修改 Alembic

2. 推荐每日执行顺序
2.1 检查整体运维状态
$env:M8_PORTFOLIO_ID="1"
$env:M8_RISK_PROFILE_CODE="paper_cn_a_risk3_strict_v1"
$env:M8_EXPORT_DAILY_REPORT="false"
python -m stock_quant_v2.scripts.m8_daily_ops_check

结果含义：

PASS = 所有核心检查通过，且无显著 warning
WARN = 核心检查通过，但存在风控拒绝、调整或 target diff
FAIL = 核心检查失败，不应进入下一步

strict profile 下出现 WARN 是合理的，因为它会拒绝缺行业分类的目标。

2.2 查看每日执行计划
python -m stock_quant_v2.scripts.m8_daily_ops_plan

输出：

QUERY_LATEST_RUNS
QUERY_PAPER_CHAIN
QUERY_RISK_DECISION
QUERY_TARGET_DIFF
EXPORT_DAILY_OPS_REPORT
2.3 查看 Ops 状态汇总
python -m stock_quant_v2.scripts.m8_ops_status_summary
2.4 导出 Daily Ops Report
$env:M8_EXPORT_DAILY_REPORT="true"
$env:M8_REPORT_OUTPUT_DIR="artifacts/m8/daily_ops"
python -m stock_quant_v2.scripts.m8_daily_ops_check

或直接：

$env:M8_REPORT_OUTPUT_DIR="artifacts/m8/daily_ops"
python -m stock_quant_v2.scripts.m8_export_daily_ops_report
3. 关键链路
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
4. 状态解释
PASS
latest_runs 可识别
paper_chain 通过
risk_decision 通过
target_diff 通过
snapshot 存在
WARN

常见原因：

risk decision 有 REJECT
risk decision 有 WARN
risk decision 有 ADJUST
source target 与 adjusted target 有差异

WARN 不一定是错误。对于 strict profile，REJECT 是预期风控结果。

FAIL

常见原因：

latest runs 找不到完整链路
paper chain 缺 target/order/fill/position/snapshot
risk decision 查不到
target diff 查不到
snapshot 查不到

FAIL 需要先修复，不建议进入日报导出或后续调度准备。

5. 后续 Scheduler 准备

M8.3 通过后，才考虑进入：

M8.4 Scheduler Adapter

M8.4 再决定是否引入：

APScheduler
Windows Task Scheduler
cron
Airflow / Prefect

当前不做。


---

# 5. 当前 M8.3 验收标准

跑完 3 个命令后，如果结果符合：

```text
m8_daily_ops_check = WARN 或 PASS
m8_daily_ops_plan = PASS
m8_ops_status_summary = PASS

则 M8.3 第一版可以判定通过。

注意：当前 strict profile 下，m8_daily_ops_check 出现 WARN 是合理结果，不是失败，因为 M7-Risk.3 strict 本来就是 30 个 REJECT。