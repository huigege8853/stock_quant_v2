# M9｜08_open_items

当前模块：M9  
当前子阶段：M9.1.1 Platform Overview Narrator  
当前阶段状态：PASS_WITH_WARN  
当前日期：2026-04-23

本文件用于收敛 M9.1.1 当前阶段尚未关闭的问题、风险点、输入缺口与后续建议。  
注意：本文件中的内容分为：

- 已确认问题
- 当前未关闭事项
- 后续建议 / Backlog
- 需要用户确认的事项

不得将本文件中的开放项自动视为已锁定决策。

---

## 一、已确认问题（当前阶段真实存在）

### 1. `13_与上一报告日对比` 仍缺少 previous report date
当前状态：
- 已识别 `latest_report_date = 2026-04-23`
- 当前章节来源中未补出 `previous_report_date`
- 历史 `artifacts/m9/platform_overview/` 产物中也未识别到可用上一报告日

影响：
- `13_与上一报告日对比` 目前必须保持 `WARN`
- 当前无法形成稳定 day-over-day comparison

结论：
- 这是输入不足导致的正确保守行为
- 不应误判为实现失败

### 2. `06_指标/因子/特征/标签状态` 仍偏 docs-only
当前状态：
- 当前主要依赖 `m3_docs`
- 尚未形成稳定的“运行事实 + 配置事实”级状态解释

影响：
- 当前更接近模块存在性说明
- 尚不能稳定回答“最新运行是哪一次 / 当前状态是否正常”

结论：
- 当前判为 `INFO` 是合理的
- 不应因为存在 M3 文档就误判为 `OK`

### 3. `07_策略与信号状态` 仍偏 docs-only
当前状态：
- 当前主要依赖 `m4_docs`
- 尚未形成稳定的“策略状态 / signal 状态 / 最新运行事实”解释层

影响：
- 当前更接近策略模块文档摘要
- 尚不能稳定回答“当前最新策略运行状态”

结论：
- 当前判为 `INFO` 是合理的
- 不应因为存在 M4 文档就误判为 `OK`

### 4. `08_回测与研究结果` 已可识别 latest run，但 latest_date 仍不稳定
当前状态：
- 已能区分 latest backtest run 与历史相关 run
- 已可识别 latest backtest run
- 但回测来源未必稳定带有报告日

影响：
- 当前 `08` 更依赖 run_id 表达“最新”
- latest_date 语义仍不如 run_id 稳定

结论：
- 当前 `08 = OK` 可以接受
- 但后续仍可优化“最新研究日/最新回测日”的解释维度

---

## 二、当前未关闭事项（必须持续跟踪）

### Open Item 1｜保留至少两个报告日的 platform overview 产物
目标：
- 让 `13_与上一报告日对比` 能自动识别：
  - latest_report_date
  - previous_report_date

当前状态：
- 未关闭

关闭条件：
- `artifacts/m9/platform_overview/` 中至少存在最近 2 个报告日的完整产物
- `13` 能稳定形成 latest / previous 比较窗口
- `13` 可从 `WARN` 收敛为 `OK`

优先级：
- P1

### Open Item 2｜为 `06` 增加更适合 M9.1.1 消费的轻量 summary artifact
目标：
- 让 M3 不只是 docs-level 输入
- 让 `06` 能更接近运行事实解释

可选做法：
- 增加指标/因子/特征/标签状态 summary artifact
- 或增加 M3 summary markdown/json 产物

当前状态：
- 未关闭

关闭条件：
- `06` 可不再仅依赖 `m3_docs`
- `06` 能输出更稳定的 latest state / risk / next check

优先级：
- P2

### Open Item 3｜为 `07` 增加更适合 M9.1.1 消费的轻量 summary artifact
目标：
- 让 M4 不只是 docs-level 输入
- 让 `07` 能更接近策略状态 / signal 状态解释

可选做法：
- 增加策略与 signal 状态 summary artifact
- 或增加 M4 summary markdown/json 产物

当前状态：
- 未关闭

关闭条件：
- `07` 可不再仅依赖 `m4_docs`
- `07` 能稳定说明当前策略与信号状态

优先级：
- P2

### Open Item 4｜明确 latest run 与 related runs 的长期展示规范
目标：
- 保证 `08 / 09 / 10 / 11 / 15` 等章节对 run 的说明口径统一

当前状态：
- 未关闭

建议规范：
- `latest_run_id`：当前最新、最主要运行
- `related_run_ids`：用于追溯的关联运行集合
- 若 DTO 暂不扩展，可先在 summary 中说明
- 后续若需要，可再升级 DTO 结构

关闭条件：
- 报告中对 latest / related run 的解释口径稳定且一致

优先级：
- P2

---

## 三、后续建议 / Backlog（不是当前必须实现）

### Backlog 1｜为 M9.1.1 增加 DB facts merge
建议内容：
- 在当前 file-artifact-first 模式稳定后，再考虑接入少量 DB facts
- 仅用于补强：
  - latest watermark
  - latest strategy runtime facts
  - latest comparison facts

当前状态：
- Backlog
- 不是当前阶段必须实现

### Backlog 2｜将 M9.1.1 入口拆分为 bootstrap 与 stable run 两类脚本
建议内容：
- 当前入口：
  - `bootstrap_m9_1_1_platform_overview_p0.py`
- 后续稳定后可增加：
  - `m9_build_platform_overview.py`

目的：
- 区分首版落地入口与长期稳定日常入口

当前状态：
- Backlog
- 不是当前阶段必须实现

### Backlog 3｜为 M9.1.1 增加 API router
建议内容：
- 在 CLI 与 artifact 输出稳定后，再考虑增加 API router
- 当前阶段不优先

当前状态：
- Backlog

### Backlog 4｜为 M9.1.1 增加 pytest
建议内容：
- 在核心输入规则和章节判定稳定后，再补 pytest
- 当前阶段不应优先于逻辑收敛

当前状态：
- Backlog

### Backlog 5｜扩展到 M9.2 / M9.3 / M9.4
建议内容：
- M9.2：Research Insight Reader
- M9.3：AI Model Foundation
- M9.4：AI Selection Model v1

注意：
- 这些都不是当前 M9.1.1 的实现范围
- 不得在当前阶段提前展开实现

当前状态：
- Backlog

---

## 四、需要用户确认的事项

### 1. 是否要求平台强制保留最近 2 个报告日的 platform overview 产物
当前建议：
- 是，至少保留 2 个报告日
- 最好保留 7 个报告日

原因：
- 这是 `13_与上一报告日对比` 收敛为 `OK` 的前提之一

当前状态：
- 建议确认

### 2. 是否需要为 `06 / 07` 专门新增轻量 summary artifact
当前建议：
- 可以，但不应立即做成复杂新模块
- 优先做轻量 markdown/json summary

原因：
- 当前 `06 / 07` 最大问题不是缺模块，而是缺“适合 M9 消费的摘要输入”

当前状态：
- 建议确认

### 3. 是否需要后续把 latest_run_id / related_run_ids 正式升级到 DTO 层
当前建议：
- 当前可先不改 DTO
- 若后续报告消费方需要更强结构化，再统一升级

当前状态：
- 建议确认

---

## 五、当前阶段不应做的事

以下事项当前明确不做：

- 不回退重做 M3 / M4 / M5 / M8 主功能
- 不引入外部 LLM
- 不引入自动交易
- 不引入自动调仓
- 不绕过 M4 Signal
- 不绕过 M7 Risk
- 不因为 `13` 缺少 previous report date 而强行伪造对比结论
- 不把 Backlog 提前说成当前已锁定任务

---

## 六、当前开放项优先级排序

### P1（当前最优先）
1. 保留至少两个报告日的 platform overview 产物
2. 让 `13_与上一报告日对比` 从 `WARN` 收敛到 `OK`

### P2（下一阶段可做）
3. 为 `06` 增加轻量 summary artifact
4. 为 `07` 增加轻量 summary artifact
5. 统一 latest run / related runs 展示规范

### P3（后续建议）
6. DB facts merge
7. stable run 脚本入口
8. API router
9. pytest
10. 扩展到 M9.2 / M9.3 / M9.4

---

## 七、当前一句话总结

当前 M9.1.1 已完成 P0 ～ P0.3，核心能力已可运行、可产生产物、可解释主要章节；当前尚未关闭的重点不是前序模块功能缺失，而是：

**补齐 `13_与上一报告日对比` 的上一日报告输入，并逐步为 `06 / 07` 增加更适合 M9.1.1 消费的轻量摘要输入。**