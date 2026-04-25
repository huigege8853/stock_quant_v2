# M8.12 Scheduler Registration Pack

- portfolio_id: `1`
- profile_code: `None`
- exported_at: `2026-04-23T15:46:34.592974`

## 1. Status

- registration_status: `FAIL`
- enhanced_final_status: `FAIL`
- scheduler_exit_code: `0`
- highest_alert_level: `WARN`

## 2. Manual Commands

10. 手动测试 PS1

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "artifacts\m8\scheduler\stock_quant_v2_m8_daily_ops.ps1"
```

20. 注册 Windows Task Scheduler 任务

```powershell
schtasks /Create /TN "stock_quant_v2_m8_daily_ops" /XML "artifacts\m8\scheduler\stock_quant_v2_m8_daily_ops.xml"
```

30. 人工检查后启用任务

```powershell
schtasks /Change /TN "stock_quant_v2_m8_daily_ops" /ENABLE
```

40. 人工禁用任务

```powershell
schtasks /Change /TN "stock_quant_v2_m8_daily_ops" /DISABLE
```

50. 人工删除任务

```powershell
schtasks /Delete /TN "stock_quant_v2_m8_daily_ops" /F
```

## 3. Registration Checklist

- [ ] scheduler_files_pass: `True`
- [ ] template_checks_pass: `True`
- [ ] scheduler_health_pass: `True`
- [ ] scheduler_exit_code_zero: `True`
- [ ] startup_not_fail: `False`
- [ ] alert_no_critical: `True`

## 4. Enhanced Final Checklist

- [ ] ops_kpi_not_fail: `True`
- [ ] startup_not_fail: `False`
- [ ] registration_not_fail: `False`
- [ ] alert_no_critical: `True`
- [ ] scheduler_exit_code_zero: `True`
- [ ] running_zero: `True`
- [ ] api_app_pass: `False`
- [ ] route_count_positive: `False`
- [ ] risk_decision_count_ok: `False`
- [ ] risk_reject_expected: `False`

## 5. Boundary

当前文档只提供注册命令和检查清单，不自动注册或启用 Windows Task Scheduler。
