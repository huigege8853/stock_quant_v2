# M9｜07_next_chat_brief

你现在继续协助我推进量化平台 V2。当前模块是：**M9.1.1 Platform Overview Narrator**。

## 一、平台总方向（已锁定，不得推翻）

1. 平台定位：**Research + Trading 双域平台**
2. 当前市场主线：**A 股日线**
3. 当前交易能力：**只做 paper trading，不做真实下单**
4. V1 保留，V2 全新独立数据库
5. V2 采用独立 PostgreSQL / 独立 ORM / 独立 Alembic
6. 当前阶段 M9 的长期核心仍是**量化模型 AI**
7. 但当前 M9 阶段先做：**自然语言解释、平台总览、运维辅助、研究辅助**
8. 当前不得擅自扩展为：
   - 外部 LLM 接入
   - 自动交易
   - 自动调仓
   - 绕过 M4 Signal
   - 绕过 M7 Risk

## 二、当前模块定位

当前子模块：**M9.1.1 Platform Overview Narrator**

目标：
- 读取现有 M5 / M8 artifacts
- 生成平台总览自然语言报告
- 输出 Markdown / JSON / CSV
- 给出人工复核建议
- 形成来源文件与 run_id 索引
- 作为后续 M9.2 / M9.3 的解释层基础，但当前不扩展过去

## 三、当前输入边界

当前允许输入：
- `artifacts/m5/backtest/*`
- `artifacts/m8/daily_ops/*`
- `artifacts/m8/alert/*`
- `artifacts/m8/audit/*`
- `artifacts/m8/env/*`
- `artifacts/m8/human_review/*`
- `artifacts/m8/paper_chain/*`
- `artifacts/m8/portfolio_snapshot/*`
- `artifacts/m8/risk/*`
- `artifacts/m8/run_summary/*`
- `artifacts/m8/scheduler_registration/*`
- `docs/modules/m8/acceptance/*`
- `artifacts/m9/platform_overview/*`（用于 day-over-day comparison fallback）

当前默认**不接入**：
- DB 查询
- 外部 API
- 外部 LLM
- 新表结构改造
- 新调度链路改造

## 四、当前输出文件

当前标准输出目录：

`artifacts/m9/platform_overview/`

当前标准输出文件：

- `m9_platform_overview_p1_<report_date>.md`
- `m9_platform_overview_p1_<report_date>.json`
- `m9_platform_overview_p1_<report_date>_sections.csv`
- `m9_platform_overview_p1_<report_date>_action_items.csv`
- `m9_platform_overview_p1_<report_date>_sources.csv`

## 五、当前代码入口

当前脚本入口：

`python -m stock_quant_v2.scripts.bootstrap_m9_1_1_platform_overview_p0 --report-date <YYYY-MM-DD>`

当前核心实现文件：

- `src/stock_quant_v2/platform_overview_domain/readers/platform_overview_artifact_reader.py`
- `src/stock_quant_v2/platform_overview_domain/services/platform_overview_report_builder.py`
- `src/stock_quant_v2/platform_overview_domain/tasks/build_platform_overview_report.py`
- `src/stock_quant_v2/scripts/bootstrap_m9_1_1_platform_overview_p0.py`

## 六、当前已经完成的阶段

### P0｜首版骨架贯通
已完成：
- M9.1.1 基础代码骨架搭建
- 成功扫描 M5 / M8 artifacts
- 成功生成 md / json / csv 输出
- 15 个固定章节全部产出

### P0.1｜状态收紧
已完成：
- `05_数据质量与缺口` 从误判 OK 收紧为 WARN
- `06_指标/因子/特征/标签状态` 从误判 OK 收紧为 INFO
- `07_策略与信号状态` 从误判 OK 收紧为 INFO
- `13_与上一报告日对比` 从误判 OK 收紧为 WARN
- `latest_date` 格式统一为 `YYYY-MM-DD`

### P0.2｜08 / 13 语义收紧
已完成：
- `08_回测与研究结果` 已能区分：
  - latest backtest run
  - historical related runs
- `13_与上一报告日对比` 已能明确说明：
  - latest_report_date
  - previous_report_date 是否存在
  - 若不存在则保持 WARN

### P0.3｜previous report date fallback
已完成：
- `13_与上一报告日对比` 增加历史 platform overview 产物回看逻辑
- 若当前章节来源中没有 previous report date，则尝试从：
  - `artifacts/m9/platform_overview/*`
  中补出上一报告日
- 若历史产物中仍无上一报告日，则保持 WARN，并明确说明原因

## 七、当前结论

当前阶段结论：

**M9.1.1 P0.3 = PASS_WITH_WARN**

成立原因：
- 代码骨架已落地
- 平台总览产物已可稳定生成
- 章节状态判定已明显收紧
- 08 的 latest backtest run 解释已可用
- 13 的 previous report date fallback 已可用

当前仍保留 WARN 的主要原因：
- `06 / 07` 仍偏 docs-only 来源
- `13` 当前仍缺少真实上一报告日 platform overview 历史产物
- 当前 WARN 属于输入不足下的正确保守行为，不应视为实现失败

## 八、当前最重要的规则

### 1. 不要回退重做前序模块主功能
当前问题主要在 M9.1.1 的解释层和输入保留规则，不在 M3 / M4 / M5 / M8 主功能缺失。

### 2. 不要把未来路线提前当当前实现
当前仍然只做：
- 平台总览
- 自然语言解释
- 人工复核建议
- 来源索引

当前不做：
- 模型训练
- AI Signal 生成
- 自动交易
- 外部 LLM 接入

### 3. 13_与上一报告日对比 必须遵守输入保留规则
为支持 day-over-day comparison：

`artifacts/m9/platform_overview/`

必须至少保留最近 **2 个报告日** 的完整产物。

若当前仅存在单日报告产物，则：

`13_与上一报告日对比`

必须输出 `WARN`，不得误判为 `OK`。

## 九、下一轮最优先任务

### 优先级 P1
补齐 `13_与上一报告日对比` 的真实上一日报告输入：

目标：
- 让目录中至少存在最近两个报告日的 platform overview 产物
- 让 13 能自动补出：
  - `latest_report_date`
  - `previous_report_date`

完成后目标：
- 将 `13` 从 `WARN` 收敛为 `OK`

### 优先级 P2
评估是否给 `06 / 07` 增加更适合 M9.1.1 消费的轻量 summary artifact：

- M3 summary artifact
- M4 summary artifact

目标：
- 让 `06 / 07` 从 docs-only 提升为更接近“运行事实 + 配置事实”的状态解释

## 十、如果下一聊天继续本模块，默认要求

请在**不推翻既有锁定结论**的前提下，继续推进 **M9.1.1 Platform Overview Narrator**。

默认要求：
1. 不回退补前序模块主功能
2. 不擅自扩到 M9.2 / M9.3 / M9.4
3. 不引入外部 LLM
4. 不改数据库核心结构
5. 继续使用完整可替换代码交付，而不是零散 patch
6. 输出时优先给：
   - 结论
   - 已锁定边界
   - 当前阶段应该做什么
   - 当前不应该做什么
   - 推荐方案
   - 下一步执行清单

## 十一、当前建议的下一条任务指令

可直接用于下一聊天开场：

你现在继续协助我推进量化平台 V2。当前模块是 **M9.1.1 Platform Overview Narrator**。  
当前阶段已经完成 P0 ～ P0.3，当前结论是 **PASS_WITH_WARN**。  
请在不推翻既有锁定方向的前提下，继续推进以下目标：

**目标：补齐 13_与上一报告日对比 的真实上一日报告输入，使其后续可从 WARN 收敛为 OK。**

要求：
- 不回退补前序模块主功能
- 不引入外部 LLM
- 不改数据库核心结构
- 继续采用完整可替换代码交付
- 若需要新增规则，请直接给 copy-safe 完整文档块