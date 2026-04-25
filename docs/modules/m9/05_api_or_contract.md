# M9｜05_api_or_contract

当前模块：M9  
当前子阶段：M9.1.1 Platform Overview Narrator  
当前日期：2026-04-23

本文件用于说明 M9.1.1 当前阶段的任务契约、输出契约、内部对象契约，以及后续 API 预留契约。

注意：
- 当前阶段以 CLI + artifact 输出为主
- 当前不强制引入 API router
- 当前 contract 重点在：
  - 输入 contract
  - 输出 contract
  - section contract
  - comparison contract
  - action item contract

---

## 一、当前入口契约

### 1.1 CLI 入口

当前入口命令：

```bash
python -m stock_quant_v2.scripts.bootstrap_m9_1_1_platform_overview_p0 --report-date <YYYY-MM-DD>
1.2 输入参数 contract
参数	类型	必填	说明
--report-date	string	否	报告日，格式建议为 YYYY-MM-DD

说明：

若传入 report-date，则优先使用该值
若未传入，则由系统基于来源自动识别 report_date
当前 report_date 主要作为输出文件命名基准
二、输入 contract
2.1 输入模式

当前模式：

file-artifact-first

即当前 contract 不是 DB query contract，而是：

artifact directory contract
docs contract
acceptance contract
historical output fallback contract
2.2 输入目录 contract

当前默认读取以下路径：

路径	说明
artifacts/m5/backtest/*	回测与研究结果
artifacts/m8/daily_ops/*	日常运行状态
artifacts/m8/alert/*	告警
artifacts/m8/audit/*	审计
artifacts/m8/env/*	环境与启动检查
artifacts/m8/human_review/*	人工复核包
artifacts/m8/paper_chain/*	交易链路
artifacts/m8/portfolio_snapshot/*	持仓与组合快照
artifacts/m8/risk/*	风控报告
artifacts/m8/run_summary/*	运行总结
artifacts/m8/scheduler_registration/*	调度注册
docs/modules/m8/acceptance/*	M8 权威验收收敛入口
artifacts/m9/platform_overview/*	历史 platform overview，用于 comparison fallback
2.3 输入文件格式 contract

当前允许读取：

.md
.json
.csv
.txt

当前 contract 不包含：

xlsx 直接解析
图片 OCR
二进制产物解析
外部接口数据流
三、内部对象 contract
3.1 ArtifactSource contract

最小契约：

{
  "module": "m8",
  "topic": "risk",
  "relative_path": "artifacts/m8/risk/m8_risk_report_p1_src160_adj166.md",
  "format": "md",
  "title": "m8_risk_report_p1_src160_adj166",
  "report_date": "2026-04-23",
  "run_ids": [160, 166],
  "summary": "text summary",
  "headers": [],
  "row_count": null,
  "top_level_keys": []
}

要求：

module / topic / relative_path 必须可追溯
report_date 与 run_ids 可为空，但若能识别则必须标准化
summary 必须可读，不得返回空字符串占位
3.2 OverviewSection contract

最小契约：

{
  "section_id": "13",
  "title": "13_与上一报告日对比",
  "summary": "当前仅识别到最新报告日 2026-04-23 ...",
  "object_name": "13_与上一报告日对比",
  "latest_run_ids": [167],
  "latest_date": "2026-04-23",
  "input_sources": [
    "daily_ops:artifacts/m8/daily_ops/...",
    "run_summary:artifacts/m8/run_summary/..."
  ],
  "outputs": [
    "artifacts/m8/daily_ops/...",
    "artifacts/m8/run_summary/..."
  ],
  "status": "WARN",
  "risks": [
    "当前仅识别到最新报告日 2026-04-23 ..."
  ],
  "next_checks": [
    "确认是否已保留上一日报告产物 ..."
  ]
}

要求：

section_id 必须为固定章节编号
status 只能取：
OK
WARN
INFO
MISSING
summary 必须说明当前状态，不得空泛
risks 与 next_checks 必须能支撑人工复核
3.3 ActionItem contract

最小契约：

{
  "priority": "P0",
  "area": "13_与上一报告日对比",
  "action": "保留上一日报告产物，并让 M9.1.1 在生成时持续读取最近两个报告日的 platform overview 快照。",
  "reason": "当前对比章节仍未形成稳定的 latest / previous 报告日窗口。",
  "related_run_ids": [],
  "related_sources": [
    "artifacts/m8/daily_ops/...",
    "artifacts/m8/run_summary/..."
  ]
}

要求：

action 必须是明确动作
reason 必须可解释
当前 action item 只作为人工复核入口，不作为自动执行任务
3.4 PlatformOverviewReport contract

最小契约：

{
  "generated_at": "2026-04-23T00:00:00Z",
  "report_date": "2026-04-23",
  "scope": "M9.1.1 Platform Overview Narrator P0.3",
  "sections": [],
  "action_items": [],
  "sources": [],
  "extra": {
    "source_count": 145
  }
}

要求：

report_date 必须与输出文件命名一致
sections 必须覆盖固定 15 章
action_items 可为空，但不建议长期为空
sources 必须可追溯
四、章节 contract
4.1 固定章节 contract

当前 sections 必须固定为 15 个，不允许动态删减：

01_执行摘要
02_今日关键结论
03_数据更新水位
04_数据源与备用源使用情况
05_数据质量与缺口
06_指标/因子/特征/标签状态
07_策略与信号状态
08_回测与研究结果
09_Paper Trading 交易链路
10_风控与目标仓位调整
11_组合持仓与盈亏
12_调度、告警、审计与环境
13_与上一报告日对比
14_人工复核建议
15_来源文件与 run_id 索引
4.2 每个章节的统一解释 contract

每个章节必须尽量回答以下问题：

当前对象是什么？
最新运行是哪一次？
最新日期到哪一天？
输入来自哪里？
输出产物是什么？
状态是否正常？
异常或风险是什么？
下一步人工应该看什么？

说明：

当前若输入不足，可保守回答
不要求每节都强行给出“完美事实”
但不得跳过状态 / 风险 / next check
五、08 contract
5.1 08_回测与研究结果 contract

当前要求：

必须区分：
latest backtest run
historical related runs
不得只输出 run_id 列表
若无 run_id，则应退化为 WARN，而不是误判 OK

当前 contract 体现方式：

latest_run_ids 承载相关 runs
summary 承载 latest / historical 的解释
后续如有需要，可升级 DTO
六、13 contract
6.1 13_与上一报告日对比 contract

当前必须输出：

latest_report_date 是否识别成功
previous_report_date 是否识别成功
当前是否形成 comparison window
若未形成 comparison window，缺少的是什么
下一步人工应补什么输入
6.2 previous report date fallback contract

当当前章节来源未补出 previous_report_date 时：

系统允许回看：

artifacts/m9/platform_overview/*

并尝试识别历史 platform overview 产物中的上一报告日。

若仍无法识别，则：

13.status = WARN
summary 必须明确说明失败原因
risks 必须明确说明输入不足
next_checks 必须明确指向补上一日报告输入
6.3 输入保留 contract

为支持 13，必须保留：

至少最近 2 个报告日 的 platform overview 完整产物
最好保留最近 7 个报告日

若仅存在单日报告产物：

13 必须保持 WARN
不得误判为 OK
七、输出 contract
7.1 输出目录 contract

输出目录固定为：

artifacts/m9/platform_overview/

7.2 输出文件命名 contract

固定命名为：

m9_platform_overview_p1_<report_date>.md
m9_platform_overview_p1_<report_date>.json
m9_platform_overview_p1_<report_date>_sections.csv
m9_platform_overview_p1_<report_date>_action_items.csv
m9_platform_overview_p1_<report_date>_sources.csv

要求：

report_date 使用 YYYY-MM-DD
不得随意更改产物命名
不得只输出其中一部分而缺少成套产物
八、当前不包含的 API contract

当前阶段不包含以下 contract：

HTTP API contract
REST router contract
DB read/write contract
external LLM contract
scheduler orchestration contract

说明：

这些不是当前 M9.1.1 阶段必需项
当前以 CLI + files 为主
九、后续预留 contract（不是当前必须实现）
Future Contract 1｜Stable CLI Contract

后续可增加：

python -m stock_quant_v2.scripts.m9_build_platform_overview --report-date <YYYY-MM-DD>

用于区分 bootstrap 与稳定入口。

Future Contract 2｜API Contract

后续可增加：

/m9/platform-overview/build
/m9/platform-overview/latest
/m9/platform-overview/sections

当前状态：

仅预留
不属于当前实现范围
Future Contract 3｜DB Facts Merge Contract

后续可增加：

latest watermark facts
latest strategy facts
latest comparison facts

当前状态：

仅预留
不属于当前实现范围