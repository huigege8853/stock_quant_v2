# M2.2 行情域稳定化阶段交接文档

## 1. 文档定位

本文档用于对 `stock_quant_v2` 项目当前 M2 阶段的推进成果进行阶段性交接，重点覆盖：

- 当前项目所处阶段
- 本轮完成的关键工作
- 已锁定的运行口径与 provider priority
- 当前已跑通的主题链路
- 本轮修复的问题与原因
- 当前遗留事项
- 下一阶段建议推进顺序
- 新聊天继续推进时可直接复用的上下文摘要

本文档目标不是 PRD 全量替代，而是作为 **M2.2 收口文档 + 后续推进桥接文档** 使用。

---

## 2. 当前项目阶段判断

### 2.1 全项目阶段

当前项目整体处于：

**M2 数据域建设阶段后半段**。

更细分地说：

- **M1 元数据与数据库框架**：已完成
- **M2_1 第一阶段主链收敛**：已完成
- **M2_2 行情域稳定化与 provider priority 收口**：核心部分已完成
- **M2 剩余主题与验收文档化**：待继续推进

### 2.2 当前最准确状态

当前不再处于“主链是否能跑”的阶段，而是进入：

**主链已跑通，稳定化已初步完成，接下来进入验收化、文档化、测试化，以及剩余主题扩展阶段。**

---

## 3. 本轮阶段目标与完成情况

### 3.1 本轮主要目标

本轮的核心目标是将 M2_1 已经收敛的链路，进一步推进成：

- 有明确 provider priority
- 有真实 fallback 机制
- tushare 可显式禁用
- 关键主题可实际跑通并落库
- 已知运行错误能被修复
- 脚本运行资源可正常释放

### 3.2 本轮已完成成果

本轮已经完成：

1. provider priority 平台规则收口
2. topic 级 priority 独立化
3. fallback 机制支持真实 skipped provider
4. tushare 支持 `TUSHARE_ENABLED=false` 显式禁用
5. instrument / trading_calendar / daily_bar / adjust_factor / market_breadth / market_index_bar 主链跑通
6. instrument 链上的 baostock 错误修复
7. instrument 链上的 `MetaInstrument(name=...)` 写入错误修复
8. baostock socket 未关闭问题修复
9. SQLAlchemy / psycopg 连接池未释放问题修复
10. stale RUNNING 记录识别与人工关闭流程明确

---

## 4. 当前已锁定的 provider 口径

### 4.1 平台默认优先级

统一默认优先级：

```text
baostock > sina > akshare > pytdx > tushare > paid > skip
```

说明：

- `skip` 为系统兜底占位，不是实际 provider
- `paid` 为未来收费源预留位
- `tushare` 当前保留在 priority 中，但运行时默认可禁用

### 4.2 主题级优先级

当前已锁定：

#### trading_calendar

```text
baostock > tushare > akshare > paid > skip
```

#### daily_bar

```text
baostock > sina > akshare > pytdx > tushare > paid > skip
```

#### adjust_factor

```text
baostock > akshare > tushare > paid > skip
```

#### market_index_bar

```text
baostock > sina > akshare > pytdx > tushare > paid > skip
```

#### instrument

```text
akshare > tushare > baostock > paid > skip
```

#### fundamental_snapshot

当前仅锁规则，尚未进入稳定主链：

```text
akshare > baostock > sina > pytdx > tushare > paid > skip
```

### 4.3 tushare 当前运行口径

当前明确口径：

- `tushare` 保留在 priority 配置中
- 是否启用由 `TUSHARE_ENABLED` 控制
- 当前阶段建议默认：

```env
TUSHARE_ENABLED=false
```

运行含义：

- priority 层仍可看到 tushare
- 实际运行中若被禁用，应进入 skipped provider 逻辑
- 当前平台不依赖 tushare 作为稳定主链

---

## 5. 当前已跑通主题链

### 5.1 股票主链

当前已跑通并落库的股票主链：

1. Instrument
2. TradingCalendar
3. DailyBar
4. AdjustFactor
5. MarketBreadth

### 5.2 指数链

当前已跑通：

1. MarketIndexBar

当前实际运行结果中，`market_index_bar` 的真实主 provider 为：

- `sina` 成功
- `baostock` 返回 empty rows

这说明当前指数行情链的实际运行主源是 `sina`，与 task 代码的 provider 尝试结果一致。

### 5.3 Instrument 最新状态

`instrument` 最新已从失败/部分成功修复为：

- `status = SUCCESS`
- `input_rows = 5502`
- `core_upsert_rows = 5502`
- `error_rows = 0`
- `selected_provider = akshare`

这标志着 instrument 主题已从“功能失败态”进入“稳定成功态”。

---

## 6. 本轮关键修复记录

### 6.1 ProviderFallbackService 真跳过修复

问题：

- 早期 fallback service 虽记录 skipped provider，但仍继续执行 fetch
- 导致 skipped 只是“记日志”，不是真正跳过

修复：

- 在 fallback service 中，对于 `skipped_providers` 先判断并直接 `continue`
- 不再执行被标记为 skipped 的 provider fetch 函数

结果：

- skipped provider 语义正确
- tushare 显式禁用逻辑可真正生效

### 6.2 sync_adjust_factor priority 修复

问题：

- `sync_adjust_factor.py` 早期错误复用了 `DAILY_BAR_PROVIDER_PRIORITY`

修复：

- 改为独立使用 `ADJUST_FACTOR_PROVIDER_PRIORITY`

结果：

- adjust_factor 主题已具备独立 priority
- 与 daily_bar 正式解耦

### 6.3 sync_trading_calendar 接统一 priority

问题：

- 早期 trading_calendar 仍是手写 provider 顺序

修复：

- 接入统一 priority 读取逻辑
- 接入 skipped_providers 入口

结果：

- trading_calendar 也进入统一 provider 管理口径

### 6.4 sync_instrument 中 baostock adapter 调用错误

问题：

- 早期 `sync_instrument.py` 直接对 `baostock_api_client` 调用 `fetch_instruments()`
- 但实际注入的是 `BaoStockApiClientAdapter`，并无此方法

修复：

- 改为走 `BaoStockClient(api_client=...)`
- instrument 链统一走 provider client 包装层，而非直接使用 adapter

结果：

- instrument 不再因 baostock 方法不存在而失败

### 6.5 MetaInstrument 不接受 `name` 字段

问题：

- instrument upsert 阶段有 308 条失败
- 根因是 `MetaInstrument(...)` 不接受 `name` 字段

修复：

- 从 `_normalize_instrument_row()` / `_upsert_instrument()` 写入路径中移除对 `name` 的构造写入
- 统一使用 `display_name`

结果：

- instrument 从 PARTIAL 修复为 SUCCESS
- `5502 -> 5502`

### 6.6 baostock socket 未关闭

问题：

- 运行结束后出现 `unclosed socket.socket`

修复：

- 在 `bootstrap_daily_bar_first_chain.py` 中增加 `_safe_logout_baostock()`
- 脚本 finally 中显式 `logout()`

结果：

- socket warning 消失

### 6.7 psycopg 连接未释放

问题：

- 运行结束后出现 `psycopg.Connection was deleted while still open`

修复：

- `bootstrap_daily_bar_first_chain.py` 改用 `with SessionLocal() as session`
- `bootstrap_meta_data_domain.py` 改用 `with SessionLocal() as session`
- `db/session.py` 新增 `dispose_engine()`
- 在主链脚本 finally 中显式 `dispose_engine()`

结果：

- 数据库连接释放问题已解决

---

## 7. 当前数据库与运行验收结论

### 7.1 已确认的运行结果

当前已验证：

- trading_calendar 成功写入
- daily_bar 成功写入
- adjust_factor 成功写入
- market_breadth 成功写入
- market_index_bar 成功写入
- instrument 成功写入

### 7.2 当前验收结论

当前可以下阶段性结论：

**M2_2 的“行情域稳定化主线”已经完成主要目标，可进入阶段收口。**

这意味着：

- provider priority 已落地
- fallback 行为正确
- 关键主链稳定
- 已知关键 bug 已修复
- 资源生命周期问题已处理

---

## 8. 当前遗留事项

虽然本轮核心目标已完成，但仍有一些事项尚未完成。

### 8.1 tushare skipped telemetry 未做强制显式验证

当前逻辑已支持：

- priority 中保留 tushare
- `TUSHARE_ENABLED=false` 时可被 skipped

但由于当前主 provider 命中较早，运行时未必真正走到 tushare，因此数据库中未必总能直接看到：

```json
{"provider_name": "tushare", "skipped": true, "skipped_reason": "disabled_by_config"}
```

这不影响当前稳定性，但若要做严谨验收，建议后续补测试或构造场景强制验证。

### 8.2 FundamentalSnapshot 尚未进入稳定主链

当前只完成了：

- provider priority 规则定义
- 在平台中的主题定位

尚未完成：

- 完整 raw/staging/core 链路
- 最小稳定 provider 主链
- 稳定运行验收

### 8.3 指数域仍需继续完善

`market_index_bar` 已跑通，但指数域整体仍建议继续补：

- `market_index` 主数据稳定化
- 指数 universe/runbook/acceptance
- 指数链路文档化

### 8.4 最小单测尚未补齐

建议后续补：

- `test_provider_priority.py`
- `test_provider_fallback_service.py`
- `test_sync_instrument_*`

---

## 9. 推荐下一阶段推进顺序

## 第一优先级：正式收口 M2.2

### 9.1 补阶段文档

建议本文件作为主交接文档保留，并在 docs 中补：

- `m2_2_provider_priority_acceptance.md`
- `m2_2_runbook.md`
- `m2_2_known_issues.md`

### 9.2 补 acceptance SQL

建议整理成正式 SQL 文档，覆盖：

- `data_sync_run` 验收
- `data_batch` 验收
- `data_quality_issue` 验收
- provider counter 验收
- core/raw/staging 行数核对

### 9.3 补最小测试

优先级建议：

1. provider priority
2. provider fallback
3. instrument upsert / normalization
4. trading_calendar priority 接线

---

## 第二优先级：推进 M2 剩余主题

### 9.4 FundamentalSnapshot 最小可用版

建议目标：

- 定义最小字段集
- 选定最小 provider 主链
- 串通 raw/staging/core
- 接入 run/batch/quality 体系

### 9.5 指数域补完

建议重点：

- `market_index` 主数据治理
- `market_index_bar` runbook 与 acceptance 完整化
- 指数主题文档收口

### 9.6 判断哪些主题留到后续小阶段

建议评估这些主题是否本轮收完，还是延后：

- `price_limit_daily`
- `instrument_status_daily`
- `tag`
- `instrument_tag`

---

## 第三优先级：为 M3 研究域做准备

当 M2 数据域底座稳定后，后续应进入更上层模块，例如：

- 特征/因子层
- 回测接入
- 研究结果管理
- 研究域到交易域的桥接

当前不建议过早进入这一层，建议等 M2 剩余主题与文档化基本完成后再切换。

---

## 10. 新聊天继续推进时的建议提示词

如果后续要开新聊天，建议直接带上下面这段上下文：

```text
项目名称：stock_quant_v2
当前阶段：M2 数据域建设后半段
当前状态：M2_1 已完成收敛；M2_2 的行情域稳定化主线已基本完成
已完成：Instrument / TradingCalendar / DailyBar / AdjustFactor / MarketBreadth / MarketIndexBar 主链跑通，provider priority 已正式落地，tushare 支持显式禁用，instrument 与资源释放问题已修复
当前重点：
1. 继续完成 M2_2 收口文档、acceptance SQL、最小测试
2. 推进 FundamentalSnapshot 最小可用版
3. 补完指数域剩余部分
4. 决定 price_limit_daily / instrument_status_daily / tag 等主题是否并入当前 M2 收尾
请基于此状态继续推进，不要回退到已完成的 provider priority 或主链稳定化问题。
```

---

## 11. 当前阶段一句话结论

**M2_2 的行情域稳定化主线已经完成主要目标，当前最合理的下一步是先完成收口文档与最小验收，再继续推进 FundamentalSnapshot 与指数域剩余建设。**

