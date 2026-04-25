## 增补决策｜M9.1.1 Daily Flow 已成为默认入口

### Decision 18｜M9.1.1 默认执行链改为 Daily Flow
状态：LOCKED

说明：
- 当前 `bootstrap_m9_1_1_platform_overview_p0.py` 不再只执行 platform overview 构建
- 当前默认执行链改为：
  1. build platform overview
  2. check platform overview history

当前影响：
- 运行 M9.1.1 默认入口时，必须同时生成：
  - platform_overview 标准产物
  - platform_overview_check 标准产物
- 不再将 history check 视为可有可无的手动附加步骤
- `13_与上一报告日对比` 的输入保留规则，已经从文档要求推进为默认执行链的一部分

---

### Decision 19｜History Check 是 13_与上一报告日对比 的默认配套检查
状态：LOCKED

说明：
- 为支持 `13_与上一报告日对比`，当前必须在每次运行 platform overview 后，自动检查：
  - 当前报告日产物是否完整
  - 历史完整报告日数量是否达到最少要求
  - 是否存在 `previous_complete_date`

当前影响：
- 当前 M9.1.1 默认执行链中，history check 不得被省略
- 若 history check 结果为 WARN，且原因是完整报告日不足 2 个，则该 WARN 视为输入保留不足下的正确保守行为
- 不得将该 WARN 误判为实现失败

---

### Decision 20｜当前 M9.1.1 的默认脚本语义已升级为“生成 + 检查”
状态：LOCKED

说明：
- 当前脚本入口：

`python -m stock_quant_v2.scripts.bootstrap_m9_1_1_platform_overview_p0 --report-date <YYYY-MM-DD>`

- 其语义已不再只是“生成 platform overview”
- 而是“运行 M9.1.1 的默认日常链路”

当前影响：
- 后续若新增 stable-run 入口，应明确与当前 bootstrap 语义区分
- 当前 bootstrap 入口可视为：
  - 当前阶段默认入口
  - 当前阶段标准执行链入口
- 当前不得再把 platform overview 生成与 history check 拆成两个彼此无关的默认动作

---

### Decision 21｜History Check 标准产物目录已锁定
状态：LOCKED

说明：
- 当前 history check 的标准输出目录为：

`artifacts/m9/platform_overview_check/`

- 当前标准输出文件为：
  - `m9_platform_overview_history_check_p1_<report_date>.md`
  - `m9_platform_overview_history_check_p1_<report_date>.json`
  - `m9_platform_overview_history_check_p1_<report_date>_inventory.csv`

当前影响：
- 后续不得随意更改 history check 的输出目录与命名口径
- History check 产物应纳入 M9.1.1 的标准 evidence artifacts
- 后续验收与运维检查可直接引用该目录中的产物

---

### Decision 22｜当前完整 platform overview 报告日少于 2 个时，Daily Flow 可 PASS_WITH_WARN
状态：LOCKED

说明：
- 当满足以下条件时：
  - 当前报告日的 platform overview 产物完整
  - history check 正常执行
  - 但完整报告日数量仍少于 2 个
- 则当前 M9.1.1 Daily Flow 可判定为：

`PASS_WITH_WARN`

原因：
- 实现已正确
- 自动检查已正确
- WARN 来源于历史输入不足，而非流程失败

当前影响：
- 不得因为 `previous_complete_date` 为空，就误判 daily flow 为 FAIL
- 只有在当前报告日产物不完整、或检查流程本身失败时，才应考虑 FAIL

---

### 一句话补充结论

当前 M9.1.1 已锁定为：

**默认入口即 Daily Flow：先生成 platform overview，再自动执行 history check，并将 `13_与上一报告日对比` 的输入保留规则落实为可执行检查。**