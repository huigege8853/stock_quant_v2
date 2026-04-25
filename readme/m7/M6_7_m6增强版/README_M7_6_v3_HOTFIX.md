# M7.6 v3 Hotfix

修复 v2 中 `OpsRunEnsureService` 对 `ops_run.run_uid` 写入 `UNKNOWN` 的问题。

原因：当前数据库中的 `ops_run.run_uid` 是 UUID 类型，必须写入合法 UUID。

替换文件：

```text
src/stock_quant_v2/trading_domain/services/ops_run_ensure_service.py
```
