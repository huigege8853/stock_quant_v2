# M9｜03_schema

当前模块：M9  
当前子阶段：M9.1.1 Platform Overview Narrator  
当前日期：2026-04-23

本文件用于说明 M9.1.1 当前阶段涉及的**文件级 schema / 输出结构 / 关键对象结构**。  
当前阶段为 file-artifact-first，不引入新的数据库核心表，当前 schema 主要指：

- 输出文件 schema
- 内部 DTO schema
- section 结构
- action item 结构
- source index 结构

---

## 一、当前 schema 范围说明

当前阶段不新增数据库核心表。  
当前 schema 范围包括：

1. `PlatformOverviewReport`
2. `OverviewSection`
3. `ActionItem`
4. `ArtifactSource`
5. 标准输出文件结构：
   - markdown
   - json
   - sections.csv
   - action_items.csv
   - sources.csv

---

## 二、内部 DTO 结构

### 2.1 ArtifactSource

用途：
- 表示单个被扫描到的来源对象
- 可来自：
  - artifacts
  - docs
  - acceptance
  - historical platform overview outputs

字段说明：

| 字段 | 类型 | 说明 |
|---|---|---|
| module | string | 所属模块，如 m5 / m8 / docs_m8 |
| topic | string | 所属主题，如 backtest / daily_ops / risk |
| relative_path | string | 相对路径 |
| format | string | 文件格式，如 md / json / csv |
| title | string | 文件标题，通常为 stem |
| report_date | string \| null | 从文件名中识别的报告日 |
| run_ids | list[int] | 从文件名中识别的 run_id 集合 |
| summary | string | 该来源的简要摘要 |
| headers | list[string] | CSV 头字段 |
| row_count | int \| null | CSV 行数 |
| top_level_keys | list[string] | JSON 顶层 key |

说明：
- `report_date` 当前主要来自文件名
- `run_ids` 当前主要来自文件名
- 当前仍是轻量 schema，不做深度语义解析

---

### 2.2 OverviewSection

用途：
- 表示 platform overview 中的单个章节

字段说明：

| 字段 | 类型 | 说明 |
|---|---|---|
| section_id | string | 章节编号，如 01 / 08 / 13 |
| title | string | 章节标题 |
| summary | string | 当前章节自然语言摘要 |
| object_name | string | 当前对象名称 |
| latest_run_ids | list[int] | 关联到的最新 / 相关 run_id 集合 |
| latest_date | string \| null | 当前识别到的最新日期 |
| input_sources | list[string] | 本章节使用到的输入来源 |
| outputs | list[string] | 本章节关联到的产出路径 |
| status | string | OK / WARN / MISSING / INFO |
| risks | list[string] | 风险说明 |
| next_checks | list[string] | 人工下一步检查项 |

说明：
- 当前 DTO 尚未显式拆成 `latest_run_id` 与 `related_run_ids`
- 当前先通过 `summary` 解释 latest / related run 语义
- 后续如有需要，可升级 DTO

---

### 2.3 ActionItem

用途：
- 表示人工复核建议、缺口补齐动作、优先任务

字段说明：

| 字段 | 类型 | 说明 |
|---|---|---|
| priority | string | 优先级，如 P0 / P1 |
| area | string | 所属领域 |
| action | string | 建议动作 |
| reason | string | 触发原因 |
| related_run_ids | list[int] | 相关 run_id |
| related_sources | list[string] | 相关来源 |

说明：
- ActionItem 当前主要来自：
  - alert
  - risk
  - comparison gap
  - missing source
- 当前用于人工复核入口，而不是自动执行入口

---

### 2.4 PlatformOverviewReport

用途：
- 表示整份 platform overview 报告

字段说明：

| 字段 | 类型 | 说明 |
|---|---|---|
| generated_at | string | 生成时间 |
| report_date | string | 报告日 |
| scope | string | 当前范围描述 |
| sections | list[OverviewSection] | 所有章节 |
| action_items | list[ActionItem] | 人工复核建议 |
| sources | list[ArtifactSource] | 所有来源索引 |
| extra | dict | 额外元信息 |

说明：
- 当前 `scope` 已迭代到 `P0 / P0.1 / P0.2 / P0.3`
- 当前 `extra` 可承载 source_count / note 等轻量扩展信息

---

## 三、固定章节 schema

当前固定章节必须存在以下 15 个 section_id：

| section_id | title |
|---|---|
| 01 | 01_执行摘要 |
| 02 | 02_今日关键结论 |
| 03 | 03_数据更新水位 |
| 04 | 04_数据源与备用源使用情况 |
| 05 | 05_数据质量与缺口 |
| 06 | 06_指标/因子/特征/标签状态 |
| 07 | 07_策略与信号状态 |
| 08 | 08_回测与研究结果 |
| 09 | 09_Paper Trading 交易链路 |
| 10 | 10_风控与目标仓位调整 |
| 11 | 11_组合持仓与盈亏 |
| 12 | 12_调度、告警、审计与环境 |
| 13 | 13_与上一报告日对比 |
| 14 | 14_人工复核建议 |
| 15 | 15_来源文件与 run_id 索引 |

要求：
- 不得随意减少章节
- 不得变更 section_id
- 不得在当前阶段改成非固定结构

---

## 四、章节状态枚举

当前状态字段 `status` 允许取值：

| 枚举值 | 含义 |
|---|---|
| OK | 当前章节已形成相对稳定结论 |
| WARN | 当前章节有输入缺口、风险信号、或应优先人工复核 |
| INFO | 当前章节仅能形成信息性说明，尚不足以判定为稳定状态 |
| MISSING | 当前章节缺少关键来源，无法形成有效结论 |

状态判定原则：
1. 输入不足时优先保守
2. 不得因“存在文档”就误判为 OK
3. 不得因“有单日报告”就误判对比章节为 OK
4. WARN / INFO 不代表失败，可能只是输入不足下的正确表达

---

## 五、标准输出文件 schema

### 5.1 Markdown 文件

文件名模式：

`m9_platform_overview_p1_<report_date>.md`

用途：
- 给人阅读的自然语言总览报告
- 按 15 个固定章节输出
- 每章统一回答：
  - 当前对象是什么
  - 最新运行是哪一次
  - 最新日期到哪一天
  - 输入来自哪里
  - 输出产物是什么
  - 状态是否正常
  - 异常或风险是什么
  - 下一步人工应该看什么

---

### 5.2 JSON 文件

文件名模式：

`m9_platform_overview_p1_<report_date>.json`

结构来源：
- `PlatformOverviewReport.to_dict()`

要求：
- 包含 sections
- 包含 action_items
- 包含 sources
- 可作为后续 API / 二次处理输入

---

### 5.3 sections.csv

文件名模式：

`m9_platform_overview_p1_<report_date>_sections.csv`

字段定义：

| 字段 | 类型 | 说明 |
|---|---|---|
| section_id | string | 章节编号 |
| title | string | 章节标题 |
| status | string | OK / WARN / INFO / MISSING |
| latest_date | string | 当前最新日期 |
| latest_run_ids | string | 以 `|` 分隔的 run_id 集合 |
| summary | string | 章节摘要 |
| risks | string | 以 `|` 分隔的风险说明 |
| next_checks | string | 以 `|` 分隔的下一步检查项 |

要求：
- `latest_date` 格式统一为 `YYYY-MM-DD`
- `latest_run_ids` 允许为空
- `summary` 必须可读、可复核、不可夸大

---

### 5.4 action_items.csv

文件名模式：

`m9_platform_overview_p1_<report_date>_action_items.csv`

字段定义：

| 字段 | 类型 | 说明 |
|---|---|---|
| priority | string | 优先级 |
| area | string | 所属领域 |
| action | string | 建议动作 |
| reason | string | 触发原因 |
| related_run_ids | string | `|` 分隔的 run_id |
| related_sources | string | `|` 分隔的来源路径 |

---

### 5.5 sources.csv

文件名模式：

`m9_platform_overview_p1_<report_date>_sources.csv`

字段定义：

| 字段 | 类型 | 说明 |
|---|---|---|
| module | string | 所属模块 |
| topic | string | 所属主题 |
| relative_path | string | 相对路径 |
| format | string | 文件格式 |
| report_date | string | 报告日 |
| run_ids | string | `|` 分隔的 run_id |
| summary | string | 来源摘要 |
| row_count | string | CSV 行数 |
| headers | string | `|` 分隔的表头 |
| top_level_keys | string | `|` 分隔的 JSON 顶层 key |

---

## 六、当前章节解释规则的 schema 约束

### 6.1 08_回测与研究结果
当前要求：
- 不能只输出 run_id 列表
- 必须在 summary 中体现：
  - latest backtest run
  - historical related runs

当前限制：
- DTO 仍未显式拆字段
- 当前通过 summary 解决 latest / related 语义

---

### 6.2 13_与上一报告日对比
当前要求：
- 必须明确：
  - latest_report_date
  - previous_report_date 是否存在
- 若 previous_report_date 缺失：
  - 必须保持 WARN
  - 不得误判为 OK

当前 fallback：
- 若当前章节来源里缺少 previous_report_date
- 允许从：

`artifacts/m9/platform_overview/*`

中回看历史 platform overview 产物

---

## 七、当前不新增的 schema

当前阶段明确不新增：

- DB 新表
- comparison 专用表
- overview registry 表
- overview snapshot metadata 表
- action item persistence 表

原因：
- 当前处于 file-artifact-first 阶段
- 当前优先做解释层收口
- 数据库设计不是当前阻塞点

---

## 八、后续可选 schema 升级（不是当前阶段必须实现）

### Option 1｜OverviewSection 增加 `latest_run_id`
用途：
- 明确区分 latest run 与 related runs

### Option 2｜OverviewSection 增加 `comparison_latest_date / comparison_previous_date`
用途：
- 减少仅靠 summary 承载 comparison 语义

### Option 3｜增加 `summary_type`
用途：
- 区分 docs-only / run-based / comparison-based / alert-based 等摘要来源类型

当前状态：
- 仅为后续建议
- 不属于当前必须实现范围

---

## 九、一句话 schema 总结

当前 M9.1.1 的 schema 是：

**以 file-artifact-first 为核心、以 OverviewSection / ActionItem / ArtifactSource 为基础、以 md/json/csv 套装输出为承载的轻量解释层 schema，而不是数据库主链 schema。**