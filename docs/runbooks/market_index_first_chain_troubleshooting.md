
---

# `docs/runbooks/market_index_first_chain_troubleshooting.md`

```md
# MarketIndex / MarketIndexBar 第一条运行链路故障排查文档

## 1. 排查原则

排查顺序固定为：

1. 先看 `ops_run / data_sync_run / data_batch`
2. 再看 `raw_market_index`
3. 再看 `stg_market_index`
4. 最后看 `market_index_bar`

不要跳过前面的运行治理层，直接盯 core 结果。

---

## 2. 常见问题总览

| 现象 | 高概率原因 | 首要检查点 |
|---|---|---|
| 脚本执行成功但 `raw_rows=0` | provider 未返回数据 | `SinaClient.fetch_market_index_bar_by_symbol()`、`raw_market_index` |
| `raw_rows>0` 但 `staging_rows=0` | staging 表/仓储/质量校验拦截 | `stg_market_index`、`data_quality_issue` |
| `staging_rows>0` 但 `core_upsert_rows=0` | 主数据映射失败 | `market_index`、`MARKET_INDEX_NOT_FOUND` |
| 有落数但 provider 不清楚 | fallback 统计没看 | `data_batch.checkpoint_json` |
| repair 跑了但没补回 | 缺口扫描范围不对 | `REPAIR_*` 环境变量、缺口 SQL |
| PowerShell 设了变量但没生效 | 使用了 `set` 而不是 `$env:` | 当前 shell 写法 |

---

## 3. 问题：脚本执行成功但 `raw_rows=0`

### 3.1 典型症状
返回值类似：

```json
{
  "input_rows": 16,
  "raw_rows": 0,
  "staging_rows": 0,
  "core_upsert_rows": 0,
  "error_rows": 0
}