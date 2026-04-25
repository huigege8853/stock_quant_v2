# MarketIndex / MarketIndexBar 第一条运行链路手册

## 1. 文档目的

本文档用于说明 `MarketIndex / MarketIndexBar` 第二条链路的运行方式、成功判定标准、校验入口、repair 使用方式以及当前已知限制。

当前链路目标：

`market_index -> raw_market_index -> stg_market_index -> market_index_bar -> meta_data_version`

并配套沉淀：

- ops_run
- data_sync_run
- data_batch
- data_quality_issue
- data_lineage

---

## 2. 当前阶段结论

当前第二条链路已经完成首轮端到端真实打通，并进入初步稳定化阶段。

已验证结果：

### 2.1 bootstrap 结果
- input_rows = 16
- raw_rows = 16
- staging_rows = 16
- core_upsert_rows = 16
- error_rows = 0
- skipped_batches = 0

### 2.2 provider 统计
- baostock: empty rows
- sina: success
- akshare: 0
- tushare: 0

### 2.3 repair 结果
- missing_pairs = 1
- input_rows = 1
- raw_rows = 1
- staging_rows = 1
- core_upsert_rows = 1
- error_rows = 0

说明当前链路已经具备：
- 可运行
- 可观测
- 可追溯
- 可修复

---

## 3. 相关表职责

### 3.1 主数据与事实表
- `market_index`：指数主数据表
- `market_index_bar`：指数日线核心事实表

### 3.2 原始与标准化分层
- `raw_market_index`：原始抓取数据
- `stg_market_index`：标准化中间层

### 3.3 运行治理
- `ops_run`：顶层运行记录
- `data_sync_run`：单次同步任务记录
- `data_batch`：批次记录
- `data_quality_issue`：质量问题记录
- `data_lineage`：数据血缘记录

### 3.4 版本管理
- `meta_data_version`：版本记录

---

## 4. 当前 provider 策略

### 4.1 当前编排顺序
当前已按以下顺序编排 provider fallback：

`baostock -> sina -> akshare -> tushare -> skip`

### 4.2 当前真实状态
- `sina`：已真实可用
- `baostock`：当前为空实现，占位
- `akshare`：当前为空实现，占位
- `tushare`：当前为空实现，占位

### 4.3 当前实际命中
从当前 `stats_json / checkpoint_json` 看，实际命中 provider 为 `sina`，`baostock` 当前表现为 `empty rows`。

---

## 5. 运行前置条件

执行前需确保：

1. 数据库 migration 已升级完成
2. `market_index` 主数据已初始化
3. `raw_market_index` / `stg_market_index` / `market_index_bar` 已存在
4. `SinaClient.fetch_market_index_bar_by_symbol()` 已是可用实现
5. `sync_market_index_bar.py` 已接入：
   - provider fallback
   - quality issue 写入
   - lineage 写入
   - batch checkpoint 统计

---

## 6. 推荐执行顺序

### 6.1 首次初始化
```powershell
python -m stock_quant_v2.scripts.db_upgrade
python -m stock_quant_v2.scripts.seed_market_index_core_universe
python -m stock_quant_v2.scripts.bootstrap_market_index_first_chain