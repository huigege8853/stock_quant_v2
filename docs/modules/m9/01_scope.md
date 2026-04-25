# M9｜01_scope

当前模块：M9  
当前子阶段：M9.1.1 Platform Overview Narrator  
当前日期：2026-04-23

## 一、模块定位

M9 是量化平台 V2 的 **AI-Assisted Research & Ops Intelligence** 模块。  
其长期核心方向是：**量化模型 AI**。  
但当前阶段并不直接进入模型训练或 AI Signal 生成，而是先完成解释层、总览层和辅助分析层的基础建设。

在 M9 当前阶段中，**M9.1.1 Platform Overview Narrator** 是最优先落地的能力。  
它的职责是：

- 读取现有平台 artifacts
- 汇总平台当前状态
- 用自然语言输出平台总览报告
- 形成结构化 section / action item / source index
- 为人工复核提供清晰入口
- 为后续 M9.2 / M9.3 / M9.4 提供可观察、可复盘、可审计的解释基础

## 二、当前子阶段定位

当前推进子阶段为：

**M9.1.1｜Platform Overview Narrator**

中文可表述为：

**平台总览自然语言报告器**

它不是：
- dashboard
- 模型训练器
- AI Signal 生成器
- 自动调仓器
- 自动交易器

它是：
- 平台当前状态的解释层
- artifacts 的汇总器
- 运维 / 风控 / 研究 / 交易链路的总览报告生成器

## 三、当前子阶段目标

当前阶段目标如下：

1. 读取已有 M5 / M8 artifacts
2. 汇总平台在数据、研究、交易、风控、运维上的当前状态
3. 生成统一平台总览输出
4. 输出标准文件：
   - Markdown
   - JSON
   - CSV
5. 为人工复核提供 action items
6. 为后续 day-over-day comparison 保留输入基础
7. 为后续 M9 扩展阶段提供稳定解释口径

## 四、当前范围（In Scope）

### 4.1 输入范围
当前允许读取以下输入：

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
- `artifacts/m9/platform_overview/*`（用于上一报告日 fallback）

### 4.2 输出范围
当前必须生成以下标准产物：

输出目录：

`artifacts/m9/platform_overview/`

输出文件：

- `m9_platform_overview_p1_<report_date>.md`
- `m9_platform_overview_p1_<report_date>.json`
- `m9_platform_overview_p1_<report_date>_sections.csv`
- `m9_platform_overview_p1_<report_date>_action_items.csv`
- `m9_platform_overview_p1_<report_date>_sources.csv`

### 4.3 内容范围
当前必须覆盖以下固定章节：

1. `01_执行摘要`
2. `02_今日关键结论`
3. `03_数据更新水位`
4. `04_数据源与备用源使用情况`
5. `05_数据质量与缺口`
6. `06_指标/因子/特征/标签状态`
7. `07_策略与信号状态`
8. `08_回测与研究结果`
9. `09_Paper Trading 交易链路`
10. `10_风控与目标仓位调整`
11. `11_组合持仓与盈亏`
12. `12_调度、告警、审计与环境`
13. `13_与上一报告日对比`
14. `14_人工复核建议`
15. `15_来源文件与 run_id 索引`

### 4.4 当前实现模式
当前采用：

**file-artifact-first**

即：
- 优先读取 artifacts
- 优先读取已有收敛文档
- 优先利用文件级来源形成解释
- 必要时未来再考虑补 DB facts

## 五、当前不在范围内（Not In Scope）

当前阶段明确不做以下事项：

### 5.1 不做模型训练
当前不做：
- model training
- model evaluation pipeline
- model registry
- model prediction runtime

这些属于后续 M9.3 / M9.4 范围，而不是当前 M9.1.1 范围。

### 5.2 不生成 AI Signal
当前不做：
- AI score 生成
- AI rank 生成
- AI expected_return 生成
- AI strategy_signal 输出

这些属于 M9.4 / M9.5 的后续范围。

### 5.3 不接入外部 LLM
当前不做：
- 外部大模型 API 接入
- 在线问答增强
- LLM-based reasoning pipeline

当前解释逻辑基于：
- artifacts
- 固定规则
- 平台内部可追溯来源

### 5.4 不自动交易
当前不做：
- 自动下单
- 自动调仓
- 绕过 Signal
- 绕过 Risk

当前仅做：
- 状态解释
- 人工复核建议
- 平台总览

### 5.5 不回退重做前序模块主功能
当前不回退重做：
- M3 指标 / 特征主功能
- M4 策略主功能
- M5 回测主功能
- M8 运维 / 调度 / 审计主功能

当前 M9.1.1 的重点是：
**解释层收口**
而不是回退补前序业务主链。

## 六、当前已实现范围

截至当前阶段，已完成以下内容：

### 6.1 P0｜首版骨架贯通
- 完成 M9.1.1 基础代码骨架
- 成功扫描 M5 / M8 artifacts
- 成功生成 md / json / csv
- 成功产出 15 个固定章节

### 6.2 P0.1｜状态收紧
- `05_数据质量与缺口` 收紧为 WARN
- `06_指标/因子/特征/标签状态` 收紧为 INFO
- `07_策略与信号状态` 收紧为 INFO
- `13_与上一报告日对比` 收紧为 WARN
- `latest_date` 格式统一为 `YYYY-MM-DD`

### 6.3 P0.2｜08 / 13 语义收紧
- `08_回测与研究结果` 已可区分 latest backtest run 与 historical related runs
- `13_与上一报告日对比` 已可区分 latest / previous report date 是否齐备

### 6.4 P0.3｜previous report date fallback
- 当当前章节来源中缺少 previous report date 时
- 允许回看 `artifacts/m9/platform_overview/*`
- 若历史 platform overview 产物中也没有 previous report date，则 `13` 保持 WARN
- 该 WARN 属于输入不足下的正确保守行为

## 七、当前边界结论

当前 M9.1.1 的阶段结论为：

**PASS_WITH_WARN**

通过点：
- 代码骨架已落地
- 输出产物已稳定生成
- 核心章节已具备解释能力
- 章节状态判定已明显收紧
- 08 与 13 已具备更合理的解释逻辑

保留 WARN 的主要原因：
- `06 / 07` 仍偏 docs-only
- `13` 仍缺少真实 previous report date 历史输入
- 当前仍需通过输入保留规则来支持 day-over-day comparison

## 八、当前最关键的边界规则

### 8.1 当前是解释层，不是决策层
M9.1.1 负责：
- 解释
- 汇总
- 提醒
- 索引
- 建议

M9.1.1 不负责：
- 决策替代
- 风控替代
- 策略替代
- 交易执行替代

### 8.2 当前是 artifacts 消费者，不是前序模块替代者
M9.1.1 应：
- 消费 M5 / M8 已有产物
- 解释这些产物

M9.1.1 不应：
- 回退重写 M5 / M8 核心能力
- 直接替代前序模块主逻辑

### 8.3 当前应保守，不应误判
当输入不足时，M9.1.1 必须：
- 输出 WARN / INFO
- 明确说明缺失原因
- 给出人工下一步

不得在输入不足时：
- 误判 OK
- 伪造对比结论
- 夸大系统当前能力

## 九、当前已知输入保留规则

为支持 `13_与上一报告日对比`：

`artifacts/m9/platform_overview/`

必须至少保留最近 **2 个报告日** 的 platform overview 完整产物。

若当前仅保留单日报告，则：
- `13` 必须保持 `WARN`
- 不得误判为 `OK`

## 十、当前阶段下一步方向

当前最优先下一步：

### P1
补齐 `13` 的真实上一日报告输入，使其从 WARN 收敛为 OK。

### P2
评估是否为 `06 / 07` 增加更适合 M9.1.1 消费的轻量 summary artifact。

### P3
在当前解释层稳定后，再评估：
- stable run 脚本入口
- API router
- pytest
- DB facts merge

## 十一、一句话范围总结

当前 M9.1.1 的范围是：

**读取已有 M5 / M8 / M9 artifacts，生成平台总览自然语言报告，并在输入不足时以保守可追溯方式输出 WARN / INFO，而不是回退补前序模块主功能或提前展开后续 AI 路线。**