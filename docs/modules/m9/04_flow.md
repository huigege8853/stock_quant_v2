# M9｜04_flow

当前模块：M9  
当前子阶段：M9.1.1 Platform Overview Narrator  
当前日期：2026-04-23

本文件用于说明 M9.1.1 当前阶段的运行流程、输入到输出的链路、章节生成逻辑，以及关键判断点。

---

## 一、总体流程概览

当前 M9.1.1 的总体运行流程如下：

1. 启动脚本入口
2. 扫描 artifacts / docs / acceptance 输入
3. 建立 `ArtifactSource` 列表
4. 按固定章节规则进行 source 匹配
5. 为每个章节生成：
   - latest_date
   - latest_run_ids
   - status
   - risks
   - next_checks
   - summary
6. 组装 `PlatformOverviewReport`
7. 导出：
   - markdown
   - json
   - sections.csv
   - action_items.csv
   - sources.csv

---

## 二、当前执行入口

当前脚本入口：

`python -m stock_quant_v2.scripts.bootstrap_m9_1_1_platform_overview_p0 --report-date <YYYY-MM-DD>`

入口脚本职责：
- 调用 task 层
- 传入 report_date
- 触发 builder
- 输出标准产物目录

---

## 三、目录级流程

### 3.1 reader 层
文件：

`platform_overview_artifact_reader.py`

职责：
- 扫描输入目录
- 建立 artifact 索引
- 从文件名提取：
  - report_date
  - run_id
- 对 md/json/csv 做轻量摘要

输出：
- `list[ArtifactSource]`

---

### 3.2 builder 层
文件：

`platform_overview_report_builder.py`

职责：
- 接收全部 `ArtifactSource`
- 按章节规则匹配来源
- 生成 15 个固定章节
- 生成 action items
- 组装 `PlatformOverviewReport`

输出：
- `PlatformOverviewReport`

---

### 3.3 exporter 层
文件：
- 仍位于 `platform_overview_report_builder.py` 中的 exporter

职责：
- 导出 md/json/csv
- 统一产物命名
- 写入 `artifacts/m9/platform_overview/`

输出：
- 5 个标准产物文件

---

### 3.4 task 层
文件：

`build_platform_overview_report.py`

职责：
- 连接 reader / builder / exporter
- 作为当前子阶段的任务入口

---

### 3.5 script 层
文件：

`bootstrap_m9_1_1_platform_overview_p0.py`

职责：
- 提供可直接运行的 CLI 入口
- 体现当前阶段辨识

---

## 四、输入到输出详细流程

### Step 1｜读取输入
输入包括：

- `artifacts/m5/backtest/*`
- `artifacts/m8/*`
- `docs/modules/m8/acceptance/*`
- `artifacts/m9/platform_overview/*`（用于 previous report date fallback）

说明：
- 当前优先读文件，不读 DB
- 当前不依赖外部 API
- 当前不依赖外部 LLM

---

### Step 2｜构建 ArtifactSource
reader 对每个文件做：

1. 分类：
   - module
   - topic
2. 提取：
   - report_date
   - run_ids
3. 读取轻量摘要：
   - text snippet
   - csv headers / row_count
   - json top-level keys

输出为统一的 `ArtifactSource` 列表。

---

### Step 3｜按固定章节进行 source 匹配
builder 使用 `_SECTION_SPECS` 进行映射，例如：

- `08_回测与研究结果` ← `backtest`, `m5_docs`
- `13_与上一报告日对比` ← `daily_ops`, `run_summary`, `portfolio_snapshot`

说明：
- 当前章节映射是固定规则
- 当前不使用动态学习映射
- 当前不允许任意新增 / 删除章节

---

### Step 4｜生成章节字段
对每个 section，当前生成：

- `latest_date`
- `latest_run_ids`
- `input_sources`
- `outputs`
- `status`
- `risks`
- `next_checks`
- `summary`

这是当前 M9.1.1 的核心计算层。

---

### Step 5｜章节级保守判定
当前判定原则：

1. 输入不足时保守
2. docs-only 不误判为 OK
3. 只有单日报告时，对比章节不误判为 OK
4. 有 alert / risk / missing comparison input 时优先 WARN
5. 不夸大当前能力

具体体现：
- `05` 收紧为 WARN
- `06 / 07` 收紧为 INFO
- `13` 缺少 previous report date 时保持 WARN

---

### Step 6｜08 回测章节特殊解释
`08_回测与研究结果` 需要：

- 识别 latest backtest run
- 同时保留 historical related runs
- 在 summary 中明确说明 latest 与 historical 的区别

原因：
- 不能只输出一个 run 列表
- 需要回答“最新运行是哪一次”

---

### Step 7｜13 对比章节特殊解释
`13_与上一报告日对比` 需要：

- 识别 latest_report_date
- 识别 previous_report_date
- 判断是否形成稳定 comparison window

若当前章节来源中没有 previous_report_date：
- 允许回看历史 `artifacts/m9/platform_overview/*`
- 若仍无 previous_report_date，则保持 WARN

这是当前 P0.3 的关键收口逻辑。

---

### Step 8｜生成 action items
当前 action items 主要来自：

- alert 来源
- risk 来源
- comparison window 缺失
- missing section source
- 当前章节状态为 WARN / MISSING 的情况

action items 用于：
- 人工复核
- 缺口补齐
- 下步执行建议

不用于：
- 自动执行
- 自动交易
- 自动调仓

---

### Step 9｜导出报告
当前标准产物包括：

- markdown
- json
- sections.csv
- action_items.csv
- sources.csv

命名统一为：

`m9_platform_overview_p1_<report_date>.*`

---

## 五、当前 day-over-day comparison 流程

### 输入层
先读取：
- `13` 当前章节匹配到的来源日期

### fallback 层
若当前章节只识别到一个日期：
- 再读取历史：

`artifacts/m9/platform_overview/*`

### 判定层
- 若可得到：
  - latest_report_date
  - previous_report_date
  则 comparison window 成立
- 若仍只有 latest_report_date
  则保持 WARN

### 输出层
summary / risks / next_checks 必须明确写出：
- 当前已识别到什么
- 缺什么
- 为什么不能比较
- 下一步需要补什么

---

## 六、当前运行模式的关键优点

### 优点 1｜不依赖 DB 即可先跑通
当前 file-artifact-first 模式让 M9.1.1 可以先落地，不必等待额外数据接入。

### 优点 2｜先收口解释层
当前先把“怎么看平台”做出来，再考虑“怎么补细节”，符合当前阶段优先级。

### 优点 3｜便于保守判定
当前容易做到：
- 输入不足时 WARN
- docs-only 时 INFO
- 单日报告时 comparison 不误判为 OK

### 优点 4｜便于逐步迭代
后续可逐步补：
- previous report date inputs
- M3/M4 summary artifacts
- DB facts merge

无需推翻当前骨架。

---

## 七、当前流程中的已知薄弱点

### 薄弱点 1｜06 / 07 仍偏 docs-only
当前流程更擅长处理：
- M5 / M8 artifacts
- run-driven topics

对 M3 / M4 的状态解释仍偏弱。

### 薄弱点 2｜13 依赖历史产物保留
如果没有历史 `platform_overview` 产物，13 将长期 WARN。

### 薄弱点 3｜latest_date 并非对所有章节都同样稳定
例如 08 仍更依赖 run_id，而不是稳定报告日。

---

## 八、当前不在流程中的内容

当前流程明确不包含：

- DB facts join
- API router
- pytest
- 外部 LLM
- 模型训练
- AI signal generation
- 自动交易 / 自动调仓

这些都不是当前 M9.1.1 流程的一部分。

---

## 九、后续可升级流程（不是当前必须实现）

### Upgrade 1
在当前流程稳定后，为 `06 / 07` 增加 summary artifact 输入。

### Upgrade 2
在当前流程稳定后，引入少量 DB facts merge。

### Upgrade 3
在当前流程稳定后，再考虑提供 stable-run script 或 API router。

---

## 十、一句话流程总结

当前 M9.1.1 的流程是：

**扫描 M5 / M8 / M9 artifacts → 建立 ArtifactSource → 按 15 个固定章节匹配输入 → 生成状态/风险/摘要 → 导出 md/json/csv 套装产物，并在 13 中通过历史 platform overview 产物补 previous report date。**