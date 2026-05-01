from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from stock_quant_v2.platform_overview_domain.dto.overview_models import (
    ActionItem,
    ArtifactSource,
    OverviewSection,
    PlatformOverviewReport,
)
from stock_quant_v2.platform_overview_domain.readers.platform_overview_artifact_reader import (
    PlatformOverviewArtifactReader,
)

_SECTION_SPECS: list[tuple[str, str, set[str]]] = [
    ("00", "00_平台运行总览卡片", {"daily_ops", "alert", "risk", "audit", "env", "paper_chain", "portfolio_snapshot", "m3:m9_bridge", "m4:m9_bridge", "m5:m9_bridge", "m9:platform_overview_check"}),
    ("01", "01_一页式执行摘要", {"daily_ops", "human_review", "run_summary", "acceptance", "alert", "risk", "paper_chain", "portfolio_snapshot", "m3:m9_bridge", "m4:m9_bridge", "m5:m9_bridge", "docs_m8:m8_docs"}),
    ("02", "02_今日关键结论", {"alert", "human_review", "risk", "run_summary", "acceptance", "docs_m8:m8_docs", "m9:platform_overview_check"}),
    ("03", "03_数据更新水位", {"daily_ops", "audit", "run_summary", "acceptance", "docs_m8:m8_docs"}),
    ("04", "04_数据源与备用源使用情况", {"daily_ops", "env", "audit", "acceptance", "docs_m8:m8_docs"}),
    ("05", "05_数据质量与缺口", {"alert", "audit", "daily_ops", "acceptance", "docs_m8:m8_docs"}),
    ("06", "06_指标/因子/特征/标签状态", {"m3_docs", "m3:m9_bridge"}),
    ("07", "07_策略与信号状态", {"m4_docs", "m4:m9_bridge"}),
    ("08", "08_回测与研究结果", {"backtest", "historical_signal_backfill", "m5_docs", "m5:m9_bridge"}),
    ("09", "09_Paper Trading 交易链路", {"paper_chain", "daily_ops", "docs_m6:m6_docs", "docs_m7:m7_docs", "acceptance", "docs_m8:m8_docs"}),
    ("10", "10_风控与目标仓位调整", {"risk", "human_review", "paper_chain", "docs_m7:m7_docs", "acceptance", "docs_m8:m8_docs"}),
    ("11", "11_组合持仓与盈亏", {"portfolio_snapshot", "paper_chain", "docs_m6:m6_docs", "docs_m7:m7_docs", "acceptance", "docs_m8:m8_docs"}),
    ("12", "12_调度、告警、审计与环境", {"scheduler_registration", "scheduler", "alert", "audit", "env", "acceptance", "docs_m8:m8_docs"}),
    ("13", "13_与上一报告日对比", {"m9:platform_overview", "m9:platform_overview_check"}),
    ("14", "14_人工复核建议", {"human_review", "alert", "risk", "acceptance", "docs_m8:m8_docs", "m9:platform_overview_check"}),
    ("15", "15_来源文件与 run_id 索引", {"*"}),
]

_OVERVIEW_REPORT_DATE_PATTERN = re.compile(r"m9_platform_overview_p\d+_(20\d{2}-\d{2}-\d{2})")


class PlatformOverviewReportBuilder:
    def __init__(
        self,
        repo_root: Path,
        reader: PlatformOverviewArtifactReader | None = None,
    ) -> None:
        self.repo_root = repo_root
        self.reader = reader or PlatformOverviewArtifactReader(repo_root=repo_root)

    def build_report(self, report_date: str | None = None) -> PlatformOverviewReport:
        sources = self.reader.scan()
        resolved_report_date = report_date or self._resolve_report_date(sources)

        sections = [
            self._build_section(section_id, title, topics, sources, resolved_report_date)
            for section_id, title, topics in _SECTION_SPECS
        ]
        action_items = self._build_action_items(sections, sources, resolved_report_date)

        return PlatformOverviewReport(
            generated_at=datetime.now(timezone.utc).isoformat(),
            report_date=resolved_report_date,
            scope="M9.1.1 Professional Platform Operations Overview P1.3",
            sections=sections,
            action_items=action_items,
            sources=sources,
            extra={
                "source_count": len(sources),
                "note": (
                    "P1.3 professionalizes platform operations overview while keeping file-artifact-first mode, "
                    "uses docs/acceptance as WARN fallback when runtime artifacts are absent, "
                    "and explicitly indexes M5 historical_signal_backfill artifacts for M5.11 readiness checks."
                ),
            },
        )

    @staticmethod
    def _normalize_date_str(value: str | None) -> str | None:
        if not value:
            return None
        raw = value.strip().replace(".", "-").replace("/", "-")
        match = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", raw)
        if match:
            year, month, day = match.groups()
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        return raw

    @classmethod
    def _collect_dates(cls, sources: list[ArtifactSource]) -> list[str]:
        return sorted(
            {
                cls._normalize_date_str(s.report_date)
                for s in sources
                if cls._normalize_date_str(s.report_date)
            }
        )

    @classmethod
    def _resolve_report_date(cls, sources: list[ArtifactSource]) -> str:
        dates = cls._collect_dates(sources)
        return dates[-1] if dates else datetime.now().strftime("%Y-%m-%d")

    def _build_section(
        self,
        section_id: str,
        title: str,
        topics: set[str],
        sources: list[ArtifactSource],
        report_date: str,
    ) -> OverviewSection:
        matched = self._match_sources(topics, sources)

        if not matched:
            return OverviewSection(
                section_id=section_id,
                title=title,
                summary="当前未发现可直接用于该章节的来源，首版以占位输出并提示人工补源。",
                object_name=title,
                latest_run_ids=[],
                latest_date=None,
                input_sources=[],
                outputs=[],
                status="MISSING",
                risks=["来源不足，无法自动形成稳定结论。"],
                next_checks=["补齐对应 artifact 或 docs source，再重跑 M9.1.1。"],
            )

        latest_date = self._latest_date(title, matched, report_date)
        latest_run_ids = self._latest_run_ids(matched)
        input_sources = [f"{s.topic}:{s.relative_path}" for s in matched[:8]]
        outputs = [s.relative_path for s in matched[:8]]
        status = self._status_for_section(title, matched, report_date)
        risks = self._risks_for_section(title, matched, status, report_date)
        next_checks = self._next_checks_for_section(title, status)
        summary = self._summary_for_section(
            title=title,
            matched=matched,
            latest_date=latest_date,
            latest_run_ids=latest_run_ids,
            status=status,
            report_date=report_date,
        )

        return OverviewSection(
            section_id=section_id,
            title=title,
            summary=summary,
            object_name=title,
            latest_run_ids=latest_run_ids,
            latest_date=latest_date,
            input_sources=input_sources,
            outputs=outputs,
            status=status,
            risks=risks,
            next_checks=next_checks,
        )

    @staticmethod
    def _match_sources(topics: set[str], sources: list[ArtifactSource]) -> list[ArtifactSource]:
        if "*" in topics:
            return list(sources)
        return [
            s
            for s in sources
            if s.topic in topics or s.module in topics or f"{s.module}:{s.topic}" in topics
        ]

    @staticmethod
    def _topic_set(sources: list[ArtifactSource]) -> set[str]:
        return {s.topic for s in sources}

    @staticmethod
    def _has_any_topic(sources: list[ArtifactSource], topics: set[str]) -> bool:
        actual = {s.topic for s in sources}
        return bool(actual.intersection(topics))

    @staticmethod
    def _has_non_doc_runtime_source(sources: list[ArtifactSource]) -> bool:
        for src in sources:
            if not src.module.startswith("docs_") and src.module != "m9":
                return True
        return False

    def _historical_overview_report_dates(self, exclude_date: str | None = None) -> list[str]:
        output_dir = self.repo_root / "artifacts" / "m9" / "platform_overview"
        if not output_dir.exists():
            return []

        exclude_norm = self._normalize_date_str(exclude_date)
        dates: set[str] = set()
        for path in output_dir.iterdir():
            if not path.is_file():
                continue
            match = _OVERVIEW_REPORT_DATE_PATTERN.search(path.name)
            if not match:
                continue
            found = self._normalize_date_str(match.group(1))
            if not found:
                continue
            if exclude_norm and found == exclude_norm:
                continue
            dates.add(found)
        return sorted(dates)

    def _comparison_window(
        self,
        sources: list[ArtifactSource],
        current_report_date: str | None = None,
    ) -> tuple[str | None, str | None]:
        current_norm = self._normalize_date_str(current_report_date)
        source_dates = self._collect_dates(sources)

        latest_candidates = set(source_dates)
        if current_norm:
            latest_candidates.add(current_norm)
        if not latest_candidates:
            return None, None

        latest_date = sorted(latest_candidates)[-1]
        previous_from_current_sources = sorted(d for d in latest_candidates if d != latest_date)
        if previous_from_current_sources:
            return latest_date, previous_from_current_sources[-1]

        historical_dates = self._historical_overview_report_dates(exclude_date=latest_date)
        previous_date = historical_dates[-1] if historical_dates else None
        return latest_date, previous_date

    def _latest_date(
        self,
        title: str,
        sources: list[ArtifactSource],
        report_date: str,
    ) -> str | None:
        if title.startswith("13"):
            latest_date, _ = self._comparison_window(sources, report_date)
            return latest_date
        dates = self._collect_dates(sources)
        return dates[-1] if dates else None

    @staticmethod
    def _latest_run_ids(sources: list[ArtifactSource]) -> list[int]:
        run_ids = sorted({run_id for s in sources for run_id in s.run_ids})
        return run_ids[-8:]

    @staticmethod
    def _latest_run_id(sources: list[ArtifactSource]) -> int | None:
        run_ids = sorted({run_id for s in sources for run_id in s.run_ids})
        return run_ids[-1] if run_ids else None

    @staticmethod
    def _bridge_sources(matched: list[ArtifactSource], module_code: str) -> list[ArtifactSource]:
        return [s for s in matched if s.module == module_code and s.topic == "m9_bridge"]

    @staticmethod
    def _bridge_field(summary: str, field_name: str) -> str | None:
        pattern = rf"{re.escape(field_name)}=([^|]+)"
        match = re.search(pattern, summary)
        return match.group(1).strip() if match else None

    def _bridge_status(self, matched: list[ArtifactSource], module_code: str) -> str | None:
        for src in self._bridge_sources(matched, module_code):
            value = self._bridge_field(src.summary, "bridge_status")
            if value:
                return value
        return None

    def _bridge_human_summary(self, matched: list[ArtifactSource], module_code: str) -> str | None:
        for src in self._bridge_sources(matched, module_code):
            value = self._bridge_field(src.summary, "human_summary")
            if value:
                return value
        return None

    def _status_for_section(
        self,
        title: str,
        matched: list[ArtifactSource],
        report_date: str,
    ) -> str:
        topics = self._topic_set(matched)
        dates = self._collect_dates(matched)
        has_run = any(s.run_ids for s in matched)

        if title.startswith("02"):
            if self._has_any_topic(matched, {"alert", "risk"}):
                return "WARN"
            return "OK" if self._has_any_topic(matched, {"human_review", "run_summary"}) else "WARN"

        if title.startswith("03"):
            return "OK" if self._has_any_topic(matched, {"daily_ops", "audit", "run_summary"}) else "WARN"

        if title.startswith("04"):
            return "OK" if self._has_any_topic(matched, {"daily_ops", "env", "audit"}) else "WARN"

        if title.startswith("05"):
            if "alert" in topics:
                return "WARN"
            return "OK" if self._has_any_topic(matched, {"daily_ops", "audit"}) else "WARN"

        if title.startswith("06"):
            bridge_status = self._bridge_status(matched, "m3")
            if bridge_status:
                return bridge_status
            if not has_run and not dates:
                return "INFO"
            return "OK"

        if title.startswith("07"):
            bridge_status = self._bridge_status(matched, "m4")
            if bridge_status:
                return bridge_status
            if not has_run and not dates:
                return "INFO"
            return "OK"

        if title.startswith("08"):
            bridge_status = self._bridge_status(matched, "m5")
            if bridge_status:
                return bridge_status
            if not has_run and not self._has_any_topic(matched, {"historical_signal_backfill"}):
                return "WARN"
            return "OK"

        if title.startswith("09"):
            return "OK" if self._has_any_topic(matched, {"paper_chain", "daily_ops"}) else "WARN"

        if title.startswith("10"):
            if "risk" in topics:
                return "WARN"
            return "OK" if self._has_any_topic(matched, {"paper_chain", "human_review"}) else "WARN"

        if title.startswith("11"):
            return "OK" if self._has_any_topic(matched, {"portfolio_snapshot", "paper_chain"}) else "WARN"

        if title.startswith("12"):
            if "alert" in topics:
                return "WARN"
            return "OK" if self._has_any_topic(matched, {"scheduler_registration", "scheduler", "audit", "env"}) else "WARN"

        if title.startswith("13"):
            latest_date, previous_date = self._comparison_window(matched, report_date)
            return "OK" if latest_date and previous_date else "WARN"

        if title.startswith("14"):
            if self._has_any_topic(matched, {"alert", "risk", "human_review"}):
                return "WARN"
            return "WARN"

        return "OK"

    def _risks_for_section(
        self,
        title: str,
        matched: list[ArtifactSource],
        status: str,
        report_date: str,
    ) -> list[str]:
        risks: list[str] = []
        topics = self._topic_set(matched)
        dates = self._collect_dates(matched)
        has_run = any(s.run_ids for s in matched)

        if status in {"WARN", "PASS_WITH_WARN"}:
            risks.append("本章节当前结论需人工复核，不应直接视为稳定最终结论。")

        if title.startswith("02") and not self._has_any_topic(matched, {"alert", "risk", "human_review", "run_summary"}):
            risks.append("未发现今日告警/风控/运行摘要事实，当前关键结论只能依据 M8 验收或历史检查材料兜底。")

        if title.startswith("03") and "daily_ops" not in topics:
            risks.append("缺少 daily_ops 来源时，数据水位结论可能不完整。")

        if title.startswith("04") and not self._has_any_topic(matched, {"daily_ops", "env", "audit"}):
            risks.append("未发现数据源/备用源运行态 artifact，当前只能做文档级解释。")

        if title.startswith("05"):
            if "alert" in topics:
                risks.append("数据质量与缺口章节已关联 alert 来源，说明仍存在待人工确认的异常或缺口信号。")
            if "audit" not in topics:
                risks.append("缺少 audit 来源时，无法稳定判断问题是否已闭环。")

        if title.startswith("06"):
            bridge_summary = self._bridge_human_summary(matched, "m3")
            if bridge_summary:
                risks.append(bridge_summary)
            elif "m3_docs" not in topics:
                risks.append("缺少 M3 文档来源，指标/因子/特征/标签章节可能只能输出占位信息。")
            elif not has_run and not dates:
                risks.append("当前仅发现文档级来源，尚未识别到可用于说明“最新状态”的运行事实。")

        if title.startswith("07"):
            bridge_summary = self._bridge_human_summary(matched, "m4")
            if bridge_summary:
                risks.append(bridge_summary)
            elif "m4_docs" not in topics:
                risks.append("缺少 M4 文档来源，策略与信号章节可能只能输出占位信息。")
            elif not has_run and not dates:
                risks.append("当前仅发现文档级来源，尚未识别到可用于说明“最新状态”的运行事实。")

        if title.startswith("08"):
            bridge_summary = self._bridge_human_summary(matched, "m5")
            bridge_status = self._bridge_status(matched, "m5")
            historical_sources = [s for s in matched if s.topic == "historical_signal_backfill"]
            if bridge_status == "PASS_WITH_WARN":
                risks.append("M5.10 当前已完成真实 backtrader 执行，但仍使用 SNAPSHOT_STATIC_BASKET_P1；这是 P1 可接受告警，不是失败。")
            elif bridge_summary:
                risks.append(bridge_summary)
            if historical_sources:
                risks.append("已发现 historical_signal_backfill artifacts，M9 已把 M5.11 相关输入纳入来源索引；仍需确认它是否已进入正式回测执行主链。")
            if not has_run:
                risks.append("回测章节未识别到 run_id，无法说明最新研究运行是哪一次。")
            if "backtest" not in topics and "m9_bridge" not in topics:
                risks.append("缺少 backtest artifact 或 M5→M9 bridge 来源时，回测章节容易退化为文档级总结。")

        if title.startswith("09") and "paper_chain" not in topics:
            risks.append("未发现 paper_chain artifact；交易链路章节当前只能依据文档/验收材料兜底。")

        if title.startswith("10") and "risk" not in topics:
            risks.append("未发现 risk artifact；风控与目标仓位调整章节当前无法稳定解释 reject / adjust 明细。")

        if title.startswith("11") and "portfolio_snapshot" not in topics:
            risks.append("未发现 portfolio_snapshot artifact；组合持仓与盈亏章节当前不能确认最新持仓/权益快照。")

        if title.startswith("12") and not self._has_any_topic(matched, {"scheduler_registration", "scheduler", "alert", "audit", "env"}):
            risks.append("未发现 scheduler/alert/audit/env 运行态 artifact；调度与环境章节只能以 M8 验收材料兜底。")

        if title.startswith("13"):
            latest_date, previous_date = self._comparison_window(matched, report_date)
            if latest_date and not previous_date:
                risks.append(f"当前仅识别到最新报告日 {latest_date}，尚无法形成稳定日间对比。")
            if not latest_date:
                risks.append("对比章节未识别到任何报告日来源，无法形成日间比较。")

        if title.startswith("14") and not self._has_any_topic(matched, {"human_review", "alert", "risk"}):
            risks.append("未发现专用 human_review/alert/risk artifact；人工复核建议将根据各章节 WARN/PASS_WITH_WARN 自动生成。")

        return risks

    @staticmethod
    def _next_checks_for_section(title: str, status: str) -> list[str]:
        if title.startswith("02"):
            return ["检查 M8 alert/risk/run_summary 是否已生成；确认今日关键结论是否仍依赖文档兜底。"]
        if title.startswith("03"):
            return ["确认最近一个已收盘交易日的数据水位是否完整。"]
        if title.startswith("04"):
            return ["确认 provider 优先级、备用源切换和 env/audit artifact 是否已进入 M8 输出。"]
        if title.startswith("05"):
            return ["检查数据质量缺口是否已有 alert/audit 记录，并确认是否闭环。"]
        if title.startswith("08"):
            return ["复核最新 backtest 的区间、策略版本、关键指标；同时检查 historical_signal_backfill 是否已进入 M5.11 正式链路。"]
        if title.startswith("09"):
            return ["核对目标仓位、订单、成交、持仓快照是否闭环。"]
        if title.startswith("10"):
            return ["重点检查 reject / adjust / WARN 的原因和影响。"]
        if title.startswith("11"):
            return ["核对最新 portfolio_snapshot 是否覆盖持仓、现金、权益和 PnL。"]
        if title.startswith("12"):
            return ["检查 scheduler、audit、env、alert 是否存在阻塞项。"]
        if title.startswith("13"):
            return ["确认是否已保留上一日报告产物；若仍缺失，则补齐上一报告日 platform overview 输入或快照。"]
        if title.startswith("06"):
            return ["检查 M3 definition 是否完整、recent M3 runs 是否成功，以及 snapshot/readiness 事实是否仍为空。"]
        if title.startswith("07"):
            return ["检查 M4 strategy metadata 是否 ready，以及 strategy_signal 运行事实是否仍为 0。"]
        if title.startswith("14"):
            return ["优先处理 CRITICAL/WARN，再处理信息性提醒。"]
        if status == "MISSING":
            return ["补齐对应来源后重跑。"]
        return ["人工抽样复核本章节结论。"]

    def _summary_for_section(
        self,
        title: str,
        matched: list[ArtifactSource],
        latest_date: str | None,
        latest_run_ids: list[int],
        status: str,
        report_date: str,
    ) -> str:
        topic_names = ", ".join(sorted({s.topic for s in matched}))
        latest_run_id = self._latest_run_id(matched)

        if title.startswith("06"):
            bridge = self._bridge_human_summary(matched, "m3")
            if bridge:
                return bridge + f" 当前来源主题：{topic_names}。"

        if title.startswith("07"):
            bridge = self._bridge_human_summary(matched, "m4")
            if bridge:
                return bridge + f" 当前来源主题：{topic_names}。"

        if title.startswith("08"):
            return self._summary_for_backtest_section(
                matched=matched,
                latest_date=latest_date,
                latest_run_ids=latest_run_ids,
                latest_run_id=latest_run_id,
                status=status,
                topic_names=topic_names,
            )

        if title.startswith("13"):
            return self._summary_for_comparison_section(
                matched=matched,
                status=status,
                topic_names=topic_names,
                report_date=report_date,
            )

        if title.startswith("14"):
            warn_like = [s for s in matched if s.topic in {"alert", "risk", "human_review", "platform_overview_check"}]
            prefix = "当前人工复核建议章节已读取专用运维来源。" if warn_like else "当前未发现专用人工复核 artifact，将根据各章节状态生成建议。"
            return f"{prefix} 本章节已汇总 {len(matched)} 个来源，覆盖主题：{topic_names}。"

        parts: list[str] = []
        if latest_date:
            parts.append(f"当前已识别到的最新报告日为 {latest_date}。")
        else:
            parts.append("当前尚未识别到稳定的最新报告日。")

        if latest_run_id is not None:
            parts.append(f"最新运行可追踪到 run_id={latest_run_id}。")
        elif latest_run_ids:
            parts.append("当前识别到关联 run_id：" + ", ".join(str(i) for i in latest_run_ids) + "。")
        else:
            parts.append("当前未识别到可直接用于说明状态的 run_id。")

        parts.append(f"本章节已汇总 {len(matched)} 个来源，覆盖主题：{topic_names}。")

        if status == "WARN":
            parts.append("本章节当前结论需优先人工复核。")
        if any(s.topic == "alert" for s in matched):
            parts.append("由于关联告警来源，应重点关注异常、阻塞项或缺口信号。")
        if any(s.topic == "risk" for s in matched):
            parts.append("由于关联风控来源，应重点关注 reject / adjust / WARN 的影响。")
        if not self._has_non_doc_runtime_source(matched):
            parts.append("当前主要是文档/验收兜底来源，尚不是完整运行态事实。")

        return " ".join(parts)

    def _summary_for_backtest_section(
        self,
        matched: list[ArtifactSource],
        latest_date: str | None,
        latest_run_ids: list[int],
        latest_run_id: int | None,
        status: str,
        topic_names: str,
    ) -> str:
        parts: list[str] = []
        bridge = self._bridge_human_summary(matched, "m5")
        bridge_status = self._bridge_status(matched, "m5")
        historical_sources = [s for s in matched if s.topic == "historical_signal_backfill"]

        if bridge:
            parts.append(bridge)
            if bridge_status == "PASS_WITH_WARN":
                parts.append("该 WARN 为当前 M5.10 P1 已接受口径；M5.11 需要继续验证历史信号逐日重放是否进入正式回测执行主链。")
            if historical_sources:
                latest_hist_date = self._collect_dates(historical_sources)[-1] if self._collect_dates(historical_sources) else "未识别"
                pass_like = sum(1 for s in historical_sources if "PASS" in s.summary or "PASS_WITH_WARN" in s.summary)
                fail_like = sum(1 for s in historical_sources if "FAIL" in s.summary)
                parts.append(
                    f"M5.11 接入检查：已发现 historical_signal_backfill 来源 {len(historical_sources)} 个，"
                    f"最新来源日期={latest_hist_date}，PASS-like={pass_like}，FAIL-like={fail_like}。"
                    "M9 已将这些来源纳入第08章和第15章索引，但这不等同于 M5.11 已替代当前 M5.10 回测主链。"
                )
            parts.append(f"当前来源主题：{topic_names}。")
            if latest_run_ids:
                parts.append("可追踪 run_id：" + ", ".join(str(i) for i in latest_run_ids) + "。")
            return " ".join(parts)

        if latest_run_id is not None:
            parts.append(f"当前最新可识别的回测运行为 run_id={latest_run_id}。")
        elif latest_run_ids:
            parts.append("当前已识别到回测相关 run_id：" + ", ".join(str(i) for i in latest_run_ids) + "。")
        else:
            parts.append("当前尚未识别到可用于说明回测状态的 run_id。")

        if latest_date:
            parts.append(f"当前来源中可识别的最新报告日为 {latest_date}。")
        else:
            parts.append("当前回测来源未稳定携带报告日，更多是依赖 run_id 来定位最新研究结果。")

        if historical_sources:
            parts.append(f"已发现 M5 historical_signal_backfill 来源 {len(historical_sources)} 个，用于 M5.11 接入检查。")
        if latest_run_ids:
            parts.append("历史相关回测 run 集合为：" + ", ".join(str(i) for i in latest_run_ids) + "。")

        parts.append(f"本章节已汇总 {len(matched)} 个来源，覆盖主题：{topic_names}。")
        if status == "WARN":
            parts.append("由于缺少稳定的回测运行事实，本章节结论需优先人工复核。")
        else:
            parts.append("当前章节已能区分 latest backtest run 与历史相关 run。")
        return " ".join(parts)

    def _summary_for_comparison_section(
        self,
        matched: list[ArtifactSource],
        status: str,
        topic_names: str,
        report_date: str,
    ) -> str:
        latest_date, previous_date = self._comparison_window(matched, report_date)
        parts: list[str] = []
        if latest_date and previous_date:
            parts.append(f"当前已识别到对比窗口：latest={latest_date}，previous={previous_date}。")
            parts.append("上一报告日已可通过当前章节来源或历史 platform overview 产物补出。")
            parts.append("本章节可以在报告日维度上形成基础的日间比较。")
        elif latest_date and not previous_date:
            parts.append(f"当前仅识别到最新报告日 {latest_date}。")
            parts.append("当前章节来源中未补出上一报告日，历史 platform overview 产物中也未识别到可用 previous report date。")
            parts.append("因此本章节仍不能形成稳定日间对比结论。")
        else:
            parts.append("当前尚未识别到可用于形成日间比较的报告日来源。")
        parts.append(f"本章节已汇总 {len(matched)} 个来源，覆盖主题：{topic_names}。")
        if status == "WARN":
            parts.append("当前对比章节应视为待补源状态，而不是稳定完成状态。")
        return " ".join(parts)

    def _build_action_items(
        self,
        sections: list[OverviewSection],
        sources: list[ArtifactSource],
        report_date: str,
    ) -> list[ActionItem]:
        items: list[ActionItem] = []

        alert_sources = [s for s in sources if s.topic == "alert"]
        if alert_sources:
            items.append(
                ActionItem(
                    priority="P0",
                    area="alert",
                    action="复核告警来源中的 CRITICAL/WARN 项。",
                    reason="M8 alert artifacts 已存在，M9 首版应把高风险对象优先推给人工复核。",
                    related_sources=[s.relative_path for s in alert_sources[:5]],
                )
            )

        risk_sources = [s for s in sources if s.topic == "risk"]
        if risk_sources:
            related_runs = sorted({run_id for s in risk_sources for run_id in s.run_ids})
            items.append(
                ActionItem(
                    priority="P0",
                    area="risk",
                    action="核对 risk reject / adjust / WARN 对目标仓位和 paper 链路的影响。",
                    reason="风控章节属于当前必须解释的主线。",
                    related_run_ids=related_runs[:8],
                    related_sources=[s.relative_path for s in risk_sources[:5]],
                )
            )

        historical_sources = [s for s in sources if s.topic == "historical_signal_backfill"]
        if historical_sources:
            items.append(
                ActionItem(
                    priority="P1",
                    area="M5.11 接入检查",
                    action="复核 historical_signal_backfill 最新 PASS/WARN/FAIL 状态，并确认它是否已进入正式 M5.11 回测执行链。",
                    reason="M9 已能索引 M5 historical_signal_backfill artifacts，但仍需区分“来源已接入”和“5.11 主链已完成”。",
                    related_sources=[s.relative_path for s in historical_sources[:5]],
                )
            )

        section06 = next((s for s in sections if s.section_id == "06"), None)
        if section06 and section06.status == "WARN":
            items.append(
                ActionItem(
                    priority="P1",
                    area="06_指标/因子/特征/标签状态",
                    action="优先检查 M3 snapshot/readiness 阻塞点，尤其是 definition 已有但 snapshot 事实仍空的情况。",
                    reason="06 已从 docs-only 升级为 bridge-driven，但当前 readiness 事实仍未就绪。",
                    related_run_ids=section06.latest_run_ids[:5],
                    related_sources=section06.outputs[:5],
                )
            )

        section07 = next((s for s in sections if s.section_id == "07"), None)
        if section07 and section07.status == "WARN":
            items.append(
                ActionItem(
                    priority="P1",
                    area="07_策略与信号状态",
                    action="优先检查 strategy_signal 产出链路，确认 metadata 已 ready 但 signal runtime facts 为 0 的原因。",
                    reason="07 已从 docs-only 升级为 bridge-driven，但当前 signal facts absent。",
                    related_run_ids=section07.latest_run_ids[:5],
                    related_sources=section07.outputs[:5],
                )
            )

        comparison_section = next((s for s in sections if s.section_id == "13"), None)
        if comparison_section and comparison_section.status == "WARN":
            items.append(
                ActionItem(
                    priority="P0",
                    area="13_与上一报告日对比",
                    action="保留上一日报告产物，并让 M9.1.1 在生成时持续读取最近两个报告日的 platform overview 快照。",
                    reason="当前对比章节仍未形成稳定的 latest / previous 报告日窗口。",
                    related_sources=comparison_section.outputs[:5],
                )
            )

        backtest_section = next((s for s in sections if s.section_id == "08"), None)
        if backtest_section and backtest_section.status in {"WARN", "FAIL", "MISSING"}:
            items.append(
                ActionItem(
                    priority="P0",
                    area="08_回测与研究结果",
                    action="补齐 latest backtest run 的稳定来源，避免回测章节退化为 docs-only 总结。",
                    reason="当前回测章节未稳定识别最新运行事实。",
                    related_sources=backtest_section.outputs[:5],
                )
            )
        elif backtest_section and backtest_section.status == "PASS_WITH_WARN":
            items.append(
                ActionItem(
                    priority="P2",
                    area="08_回测与研究结果",
                    action="保留 M5.10 真实 backtrader 执行口径，并把 historical_signal_backfill 是否可进入 M5.11 正式链路作为下一项复核。",
                    reason="M5.10 已通过但使用 SNAPSHOT_STATIC_BASKET_P1，这是当前可接受 WARN；M5.11 需要独立确认。",
                    related_run_ids=backtest_section.latest_run_ids[:5],
                    related_sources=backtest_section.outputs[:5],
                )
            )

        for section in sections:
            if section.status == "MISSING":
                items.append(
                    ActionItem(
                        priority="P1",
                        area=section.title,
                        action=f"补齐 {section.title} 对应来源或 DB facts。",
                        reason="当前章节仍是占位或来源不足。",
                        related_sources=section.outputs[:5],
                    )
                )
            elif section.status in {"WARN", "PASS_WITH_WARN"} and section.section_id not in {"06", "07", "08", "13"}:
                items.append(
                    ActionItem(
                        priority="P2",
                        area=section.title,
                        action=f"复核 {section.title} 是否仍缺少运行态 artifact。",
                        reason="该章节已由文档/验收或告警类来源兜底，尚不等同于稳定 OK。",
                        related_sources=section.outputs[:5],
                    )
                )

        has_acceptance_master = any("docs/modules/m8/acceptance/" in s.relative_path for s in sources)
        if not has_acceptance_master:
            items.append(
                ActionItem(
                    priority="P0",
                    area="acceptance",
                    action="先把 M8 验收材料收敛到 acceptance master / registry / manifest。",
                    reason="M9.1.1 应优先读取 M8 权威收敛入口，避免从零散验收文档中拼接结论。",
                )
            )

        return items


class PlatformOverviewExporter:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def export(self, report: PlatformOverviewReport) -> dict[str, Path]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        prefix = f"m9_platform_overview_p1_{report.report_date}"

        md_path = self.output_dir / f"{prefix}.md"
        json_path = self.output_dir / f"{prefix}.json"
        sections_csv_path = self.output_dir / f"{prefix}_sections.csv"
        action_items_csv_path = self.output_dir / f"{prefix}_action_items.csv"
        sources_csv_path = self.output_dir / f"{prefix}_sources.csv"

        md_path.write_text(self._render_markdown(report), encoding="utf-8")
        json_path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        self._write_sections_csv(sections_csv_path, report)
        self._write_action_items_csv(action_items_csv_path, report)
        self._write_sources_csv(sources_csv_path, report)

        return {
            "markdown": md_path,
            "json": json_path,
            "sections_csv": sections_csv_path,
            "action_items_csv": action_items_csv_path,
            "sources_csv": sources_csv_path,
        }

    @staticmethod
    def _render_markdown(report: PlatformOverviewReport) -> str:
        """Render professional platform operations overview.

        Markdown focuses on status, key facts, risk, and action. Full source
        lineage remains in JSON/CSV exports, especially *_sources.csv.
        """

        def section_by_id(section_id: str) -> OverviewSection | None:
            return next((s for s in report.sections if s.section_id == section_id), None)

        def status_of(section_id: str) -> str:
            section = section_by_id(section_id)
            return section.status if section else "MISSING"

        def severity_rank(status: str) -> int:
            return {
                "OK": 0,
                "PASS": 0,
                "INFO": 1,
                "PASS_WITH_WARN": 2,
                "WARN": 3,
                "MISSING": 4,
                "FAIL": 5,
            }.get(status, 3)

        def merged_status(section_ids: list[str]) -> str:
            statuses = [status_of(i) for i in section_ids]
            worst = max(statuses, key=severity_rank) if statuses else "INFO"
            return "WARN" if worst == "PASS_WITH_WARN" else worst

        def sources_for_topic(topic: str) -> list[ArtifactSource]:
            return [s for s in report.sources if s.topic == topic or s.module == topic]

        def latest_date(sources: list[ArtifactSource]) -> str:
            dates = sorted({s.report_date for s in sources if s.report_date})
            return dates[-1] if dates else "未识别"

        def latest_run_ids(sources: list[ArtifactSource], limit: int = 8) -> list[int]:
            run_ids = sorted({rid for s in sources for rid in s.run_ids})
            return run_ids[-limit:]

        def latest_run_id_text(sources: list[ArtifactSource]) -> str:
            run_ids = latest_run_ids(sources, limit=1)
            return str(run_ids[-1]) if run_ids else "未识别"

        def topic_counts() -> dict[str, int]:
            counts: dict[str, int] = {}
            for src in report.sources:
                counts[src.topic] = counts.get(src.topic, 0) + 1
            return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))

        def has_text(pattern: str, sources: list[ArtifactSource] | None = None) -> bool:
            haystack = sources if sources is not None else report.sources
            needle = pattern.lower()
            return any(
                needle in (s.summary or "").lower()
                or needle in (s.relative_path or "").lower()
                or needle in (s.title or "").lower()
                for s in haystack
            )

        def source_summary_value(module_code: str, field_name: str) -> str | None:
            pattern = rf"{re.escape(field_name)}=([^|]+)"
            for src in report.sources:
                if src.module == module_code and src.topic == "m9_bridge":
                    match = re.search(pattern, src.summary or "")
                    if match:
                        return match.group(1).strip()
            return None

        def first_non_empty(values: list[str | None]) -> str:
            for value in values:
                if value and str(value).strip() and str(value).strip() != "未识别":
                    return str(value).strip()
            return "未识别"

        def fmt_run_ids(run_ids: list[int]) -> str:
            return ", ".join(str(i) for i in run_ids) if run_ids else "未识别"

        def source_hint(section: OverviewSection) -> str:
            topics: list[str] = []
            output_set = set(section.outputs)
            input_tail = {x.split(":", 1)[-1] for x in section.input_sources}
            for src in report.sources:
                if src.relative_path in output_set or src.relative_path in input_tail:
                    if src.topic not in topics:
                        topics.append(src.topic)
            return "、".join(topics[:8]) if topics else "详见 sources.csv"

        alert_sources = sources_for_topic("alert")
        risk_sources = sources_for_topic("risk")
        paper_sources = sources_for_topic("paper_chain")
        portfolio_sources = sources_for_topic("portfolio_snapshot")
        daily_ops_sources = sources_for_topic("daily_ops")
        m4_bridge_sources = [s for s in report.sources if s.module == "m4" and s.topic == "m9_bridge"]
        m5_bridge_sources = [s for s in report.sources if s.module == "m5" and s.topic == "m9_bridge"]
        backtest_sources = sources_for_topic("backtest") + m5_bridge_sources

        data_status = merged_status(["03", "05", "06"])
        research_status = merged_status(["07", "08"])
        paper_status = merged_status(["09", "11"])
        risk_status = merged_status(["10", "12", "14"])
        alert_status = "FAIL" if has_text("CRITICAL", alert_sources) else ("WARN" if alert_sources else "OK")

        platform_status_candidates = [data_status, research_status, paper_status, risk_status, alert_status]
        platform_status = max(platform_status_candidates, key=severity_rank)
        if platform_status == "OK":
            final_conclusion = "OK：平台运行总览未发现明显阻塞项，可作为日常复盘依据。"
        elif platform_status in {"WARN", "PASS_WITH_WARN"}:
            final_conclusion = "WARN：平台主链有可用产物，但存在需要人工复核的风险项，不建议无人值守放行。"
        else:
            final_conclusion = "FAIL/WARN：存在高优先级告警、缺失或阻塞项，必须人工复核后再使用。"

        latest_business_date = first_non_empty([
            latest_date(daily_ops_sources),
            latest_date(portfolio_sources),
            latest_date(report.sources),
        ])
        latest_signal_date = first_non_empty([
            source_summary_value("m4", "report_date"),
            latest_date(m4_bridge_sources),
        ])
        latest_backtest_run = first_non_empty([
            source_summary_value("m5", "latest_run_id"),
            latest_run_id_text(backtest_sources),
        ])
        latest_paper_run = latest_run_id_text(paper_sources)
        latest_risk_run = latest_run_id_text(risk_sources)
        highest_alert = "CRITICAL" if has_text("CRITICAL", alert_sources) else ("WARN/INFO" if alert_sources else "未识别")

        key_findings: list[str] = []
        if paper_sources:
            key_findings.append(f"Paper Trading 链路已识别，最新相关 run_id={latest_paper_run}，交易链路章节状态={status_of('09')}。")
        else:
            key_findings.append("未识别到 paper_chain 来源，交易链路闭环状态需要补源确认。")
        if risk_sources:
            key_findings.append(f"风控来源已识别，最新 risk run_id={latest_risk_run}；风控章节状态={status_of('10')}。")
        else:
            key_findings.append("未识别到 risk 来源，无法稳定解释 reject / adjust / WARN。")
        if alert_sources:
            key_findings.append(f"告警来源已识别，最高告警级别={highest_alert}；平台整体不能简单判为完全 OK。")
        if status_of("06") in {"WARN", "FAIL", "MISSING", "PASS_WITH_WARN"}:
            key_findings.append("M3 指标/因子/特征/标签章节仍需复核，尤其是 readiness / snapshot 阻塞点。")
        if status_of("08") == "PASS_WITH_WARN":
            key_findings.append("M5 回测已有可解释结果，但仍需区分 M5.10 当前口径与 M5.11 historical signal replay 是否进入正式主链。")
        elif status_of("08") in {"WARN", "MISSING", "FAIL"}:
            key_findings.append("M5 回测章节未达到稳定 OK，需要复核最新 backtest run 与研究证据。")
        if not key_findings:
            key_findings.append("当前未自动识别到核心异常，但仍建议抽样复核关键来源。")

        def professional_section(section: OverviewSection) -> list[str]:
            lines: list[str] = [f"## {section.title}", ""]
            risk_text = "；".join(section.risks) if section.risks else "暂无明显风险"
            action_text = "；".join(section.next_checks) if section.next_checks else "人工抽样复核本章节结论。"
            src_hint = source_hint(section)

            if section.section_id == "00":
                lines.extend([
                    f"- 状态：{platform_status}",
                    f"- 最终运维结论：{final_conclusion}",
                    "",
                    "### 关键水位",
                    "",
                    f"- 报告生成日：{report.report_date}",
                    f"- 最新业务数据日：{latest_business_date}",
                    f"- 最新信号来源日：{latest_signal_date}",
                    f"- 最新回测 run_id：{latest_backtest_run}",
                    f"- 最新 paper run_id：{latest_paper_run}",
                    f"- 最新 risk run_id：{latest_risk_run}",
                    f"- 最高告警级别：{highest_alert}",
                    "",
                    "### 状态分层",
                    "",
                    f"- 数据链路状态：{data_status}",
                    f"- 研究链路状态：{research_status}",
                    f"- Paper Trading 状态：{paper_status}",
                    f"- 风控/告警状态：{risk_status} / {alert_status}",
                    "",
                ])
                return lines

            if section.section_id == "01":
                lines.extend([
                    f"- 状态：{platform_status}",
                    f"- 结论：{final_conclusion}",
                    "",
                    "### 今日一页式摘要",
                    "",
                    f"- 数据链路：{data_status}",
                    f"- 策略/研究链路：{research_status}",
                    f"- Paper Trading 链路：{paper_status}",
                    f"- 风控与告警：{risk_status} / {alert_status}",
                    f"- 来源总数：{len(report.sources)}，完整来源见 `m9_platform_overview_p1_{report.report_date}_sources.csv`。",
                    "",
                    "### 重点复核",
                    "",
                ])
                for idx, finding in enumerate(key_findings[:6], start=1):
                    lines.append(f"{idx}. {finding}")
                lines.append("")
                return lines

            if section.section_id == "02":
                lines.extend([
                    f"- 状态：{section.status}",
                    "- 结论：今日关键结论以平台主链状态、风控、告警、M3/M5 readiness 为核心，不再以来源数量作为正文重点。",
                    "",
                    "### 今日关键结论",
                    "",
                ])
                for idx, finding in enumerate(key_findings[:8], start=1):
                    lines.append(f"{idx}. {finding}")
                lines.append("")
                return lines

            if section.section_id == "03":
                conclusion = "数据水位章节用于确认最新交易日数据是否完整；若缺少 M2/M3 专用水位 artifact，则只能做间接判断。"
                facts = [f"最新可识别业务日期：{section.latest_date or latest_business_date}", f"数据相关来源主题：{src_hint}"]
            elif section.section_id == "04":
                conclusion = "数据源与备用源章节用于确认 provider 是否可用、是否触发备用源、是否存在源级失败。"
                facts = [f"环境/审计/日常运行来源：{src_hint}", "当前报告不会假设 provider 级别状态；若无 provider usage artifact，则只做运行态兜底判断。"]
            elif section.section_id == "05":
                conclusion = "数据质量章节应重点关注缺口、告警和 audit 是否闭环。"
                facts = [f"数据质量相关状态：{section.status}", f"关联来源：{src_hint}"]
            elif section.section_id == "06":
                conclusion = "M3 当前应分开判断：definition 是否 ready，以及 runtime/readiness 是否 blocked。"
                facts = [f"M3 bridge 状态：{section.status}", section.summary]
            elif section.section_id == "07":
                conclusion = "策略与信号章节用于确认 strategy metadata、strategy version 和 signal facts 是否可作为 M5/M6 输入。"
                facts = [f"M4 bridge 状态：{section.status}", section.summary]
            elif section.section_id == "08":
                conclusion = "回测章节应区分当前可解释结果与下一阶段 M5.11 historical signal replay 是否已成为正式主链。"
                facts = [f"最新回测 run_id：{latest_backtest_run}", f"M5 bridge 状态：{section.status}", "正文只保留回测口径解释；完整 backtest 文件索引见 sources.csv。"]
            elif section.section_id == "09":
                conclusion = "Paper Trading 章节用于确认 target / order / fill / position / snapshot 是否闭环。"
                facts = [f"Paper 相关 run_id：{fmt_run_ids(latest_run_ids(paper_sources))}", f"交易链路状态：{section.status}"]
            elif section.section_id == "10":
                conclusion = "风控章节用于确认 reject / adjust / WARN 是否影响目标仓位和 paper 链路。"
                facts = [f"Risk 相关 run_id：{fmt_run_ids(latest_run_ids(risk_sources))}", f"风控章节状态：{section.status}"]
            elif section.section_id == "11":
                conclusion = "组合章节用于确认持仓、现金、权益和 PnL 快照是否存在；细粒度投资解释由 M9.1.1-B 负责。"
                facts = [f"Portfolio snapshot 日期：{latest_date(portfolio_sources)}", f"组合章节状态：{section.status}"]
            elif section.section_id == "12":
                conclusion = "调度、告警、审计与环境是运维报告核心；存在 CRITICAL 时平台整体不能判为完全 OK。"
                facts = [f"告警状态：{alert_status}，最高告警级别：{highest_alert}", f"调度/审计/环境章节状态：{section.status}"]
            elif section.section_id == "13":
                conclusion = "与上一报告日对比用于识别状态恶化、风险持续和缺失项是否闭环。"
                facts = [section.summary, "P0 先做报告日维度对比；指标级变化留到后续版本。"]
            elif section.section_id == "14":
                lines.extend([
                    f"- 状态：{section.status}",
                    "- 结论：本节聚合运维 P0/P1/P2 人工复核事项，优先处理 CRITICAL、risk WARN、M3 readiness、M5.11 主链确认。",
                    "",
                    "### Action Items",
                    "",
                ])
                if report.action_items:
                    for item in report.action_items:
                        run_text = f"｜run_id={fmt_run_ids(item.related_run_ids)}" if item.related_run_ids else ""
                        lines.append(f"- [{item.priority}] {item.area}：{item.action}｜原因：{item.reason}{run_text}")
                else:
                    lines.append("- 暂无自动生成的人工复核建议。")
                lines.append("")
                return lines
            elif section.section_id == "15":
                counts = topic_counts()
                lines.extend([
                    f"- 状态：{section.status}",
                    f"- 结论：当前共索引 {len(report.sources)} 个来源；Markdown 只展示汇总，完整血缘见 sources.csv。",
                    "",
                    "### 来源主题汇总",
                    "",
                ])
                for topic, count in list(counts.items())[:20]:
                    lines.append(f"- {topic}: {count}")
                lines.extend(["", "### 核心来源", ""])
                core_topics = {"m9_bridge", "daily_ops", "paper_chain", "portfolio_snapshot", "risk", "alert", "audit", "env", "platform_overview_check"}
                shown: set[str] = set()
                for src in report.sources:
                    if src.topic not in core_topics:
                        continue
                    key = f"{src.topic}:{src.relative_path}"
                    if key in shown:
                        continue
                    shown.add(key)
                    lines.append(f"- {src.topic}: {src.relative_path} | date={src.report_date or '-'} | run_id={fmt_run_ids(src.run_ids)}")
                    if len(shown) >= 24:
                        break
                lines.extend(["", f"完整来源文件：`m9_platform_overview_p1_{report.report_date}_sources.csv`。", ""])
                return lines
            else:
                conclusion = section.summary
                facts = [section.summary]

            lines.extend([
                f"- 状态：{section.status}",
                f"- 结论：{conclusion}",
                "",
                "### 关键事实",
                "",
            ])
            for fact in facts:
                if fact:
                    lines.append(f"- {fact}")
            lines.extend(["", "### 风险", "", f"- {risk_text}", "", "### 建议动作", "", f"- {action_text}", ""])
            return lines

        lines: list[str] = [
            "# M9.1.1 专业版平台运行总览日报",
            "",
            f"- Report Date: {report.report_date}",
            f"- Generated At: {report.generated_at}",
            f"- Scope: {report.scope}",
            f"- Source Count: {len(report.sources)}",
            f"- DATA_CHAIN_STATUS: {data_status}",
            f"- RESEARCH_CHAIN_STATUS: {research_status}",
            f"- PAPER_TRADING_STATUS: {paper_status}",
            f"- RISK_ALERT_STATUS: {risk_status} / {alert_status}",
            f"- FINAL_OPS_CONCLUSION: {final_conclusion}",
            "",
        ]

        for section in report.sections:
            lines.extend(professional_section(section))

        return "\n".join(lines)

    @staticmethod
    def _write_sections_csv(path: Path, report: PlatformOverviewReport) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "section_id",
                    "title",
                    "status",
                    "latest_date",
                    "latest_run_ids",
                    "summary",
                    "risks",
                    "next_checks",
                ],
            )
            writer.writeheader()
            for section in report.sections:
                writer.writerow(
                    {
                        "section_id": section.section_id,
                        "title": section.title,
                        "status": section.status,
                        "latest_date": section.latest_date or "",
                        "latest_run_ids": "|".join(str(i) for i in section.latest_run_ids),
                        "summary": section.summary,
                        "risks": "|".join(section.risks),
                        "next_checks": "|".join(section.next_checks),
                    }
                )

    @staticmethod
    def _write_action_items_csv(path: Path, report: PlatformOverviewReport) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["priority", "area", "action", "reason", "related_run_ids", "related_sources"],
            )
            writer.writeheader()
            for item in report.action_items:
                writer.writerow(
                    {
                        "priority": item.priority,
                        "area": item.area,
                        "action": item.action,
                        "reason": item.reason,
                        "related_run_ids": "|".join(str(i) for i in item.related_run_ids),
                        "related_sources": "|".join(item.related_sources),
                    }
                )

    @staticmethod
    def _write_sources_csv(path: Path, report: PlatformOverviewReport) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "module",
                    "topic",
                    "relative_path",
                    "format",
                    "report_date",
                    "run_ids",
                    "summary",
                    "row_count",
                    "headers",
                    "top_level_keys",
                ],
            )
            writer.writeheader()
            for source in report.sources:
                writer.writerow(
                    {
                        "module": source.module,
                        "topic": source.topic,
                        "relative_path": source.relative_path,
                        "format": source.format,
                        "report_date": source.report_date or "",
                        "run_ids": "|".join(str(i) for i in source.run_ids),
                        "summary": source.summary,
                        "row_count": source.row_count or "",
                        "headers": "|".join(source.headers),
                        "top_level_keys": "|".join(source.top_level_keys),
                    }
                )
