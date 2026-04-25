# M8.11 Environment Config / Startup Check

项目名称：stock_quant_v2  
模块：M8.11 Environment Config / Startup Check  
状态：待验收

## 1. 目标

补齐 M8 原始职责中的：

```text
环境配置管理
启动检查
启动手册
2. 已新增 CLI
m8_env_check
m8_startup_check
m8_export_env_report
3. 当前边界
不自动修复环境
不改数据库
不改交易数据
不注册调度任务
4. 验收命令
$env:M8_PORTFOLIO_ID="1"
$env:M8_RISK_PROFILE_CODE="paper_cn_a_risk3_strict_v1"
$env:M8_PROJECT_ROOT="D:\01_a_Project\10_python\01_Projects\Projet_stock_quant_v2\stock_quant_v2"

python -m stock_quant_v2.scripts.m8_env_check
python -m stock_quant_v2.scripts.m8_startup_check

$env:M8_ENV_OUTPUT_DIR="artifacts/m8/env"
python -m stock_quant_v2.scripts.m8_export_env_report
5. 通过标准
m8_env_check = PASS 或 WARN
m8_startup_check = PASS 或 WARN
m8_export_env_report = PASS
failures = []
scheduler_exit_code = 0
highest_alert_level != CRITICAL
artifact check = PASS

---

跑完这三个脚本和 artifact check，把输出贴我。  
如果通过，我继续收口：

```text
sql/m8_11_acceptance.sql
docs/modules/m8/31_m8_11_acceptance.md
docs/modules/m8/32_next_step_after_m8_11.md