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
    ("01", "01_执行摘要", {"daily_ops", "human_review", "run_summary", "acceptance"}),
    ("02", "02_今日关键结论", {"alert", "human_review", "risk", "run_summary"}),
    ("03", "03_数据更新水位", {"daily_ops", "audit", "run_summary"}),
    ("04", "04_数据源与备用源使用情况", {"daily_ops", "env", "audit"}),
    ("05", "05_数据质量与缺口", {"alert", "audit", "daily_ops"}),
    ("06", "06_指标/因子/特征/标签状态", {"m3_docs", "m3:m9_bridge"}),
    ("07", "07_策略与信号状态", {"m4_docs", "m4:m9_bridge"}),
    ("08", "08_回测与研究结果", {"backtest", "m5_docs"}),
    ("09", "09_Paper Trading 交易链路", {"paper_chain", "daily_ops"}),
    ("10", "10_风控与目标仓位调整", {"risk", "human_review", "paper_chain"}),
    ("11", "11_组合持仓与盈亏", {"portfolio_snapshot", "paper_chain"}),
    ("12", "12_调度、告警、审计与环境", {"scheduler_registration", "alert", "audit", "env"}),
    ("13", "13_与上一报告日对比", {"daily_ops", "run_summary", "portfolio_snapshot"}),
    ("14", "14_人工复核建议", {"human_review", "alert", "risk"}),
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
            scope="M9.1.1 Platform Overview Narrator P1",
            sections=sections,
            action_items=action_items,
            sources=sources,
            extra={
                "source_count": len(sources),
                "note": (
                    "P1 keeps file-artifact-first mode, preserves P0.3 logic, "
                    "and adds M3/M4 bridge summaries for sections 06/07."
                ),
            },
        )

    @staticmethod
    def _normalize_date_str(value: str | None) -> str | None:
        if not value:
            return None

        raw = value.strip()
        raw = raw.replace(".", "-").replace("/", "-")

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

    def _bridge_sources(self, matched: list[ArtifactSource], module_code: str) -> list[ArtifactSource]:
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
        topics = {s.topic for s in matched}
        dates = self._collect_dates(matched)
        has_run = any(s.run_ids for s in matched)

        if title.startswith("02"):
            if "alert" in topics or "risk" in topics:
                return "WARN"
            return "OK"

        if title.startswith("05"):
            if "alert" in topics:
                return "WARN"
            return "OK"

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
            if not has_run:
                return "WARN"
            return "OK"

        if title.startswith("10"):
            if "risk" in topics:
                return "WARN"
            return "OK"

        if title.startswith("12"):
            if "alert" in topics:
                return "WARN"
            return "OK"

        if title.startswith("13"):
            latest_date, previous_date = self._comparison_window(matched, report_date)
            if latest_date and previous_date:
                return "OK"
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
        topics = {s.topic for s in matched}
        dates = self._collect_dates(matched)
        has_run = any(s.run_ids for s in matched)

        if status == "WARN":
            risks.append("本章节当前结论需人工复核，不应直接视为稳定最终结论。")

        if title.startswith("03") and "daily_ops" not in topics:
            risks.append("缺少 daily_ops 来源时，数据水位结论可能不完整。")

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
            if not has_run:
                risks.append("回测章节未识别到 run_id，无法说明最新研究运行是哪一次。")
            if "backtest" not in topics:
                risks.append("缺少 backtest artifact 来源时，回测章节容易退化为文档级总结。")

        if title.startswith("13"):
            latest_date, previous_date = self._comparison_window(matched, report_date)
            if latest_date and not previous_date:
                risks.append(
                    f"当前仅识别到最新报告日 {latest_date}，且历史 platform overview 产物中也未补出上一报告日，仍无法形成稳定日间对比。"
                )
            if not latest_date:
                risks.append("对比章节未识别到任何报告日来源，无法形成日间比较。")

        return risks

    @staticmethod
    def _next_checks_for_section(title: str, status: str) -> list[str]:
        if title.startswith("03"):
            return ["确认最近一个已收盘交易日的数据水位是否完整。"]
        if title.startswith("08"):
            return ["复核最新 backtest 的区间、策略版本、关键指标，并区分 latest run 与历史相关 run。"]
        if title.startswith("09"):
            return ["核对目标仓位、订单、成交、持仓快照是否闭环。"]
        if title.startswith("10"):
            return ["重点检查 reject / adjust / WARN 的原因和影响。"]
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

        parts: list[str] = []

        if latest_date:
            parts.append(f"当前已识别到的最新报告日为 {latest_date}。")
        else:
            parts.append("当前尚未识别到稳定的最新报告日。")

        if latest_run_id is not None:
            parts.append(f"最新运行可追踪到 run_id={latest_run_id}。")
        elif latest_run_ids:
            parts.append(
                "当前识别到关联 run_id：" + ", ".join(str(i) for i in latest_run_ids) + "。"
            )
        else:
            parts.append("当前未识别到可直接用于说明状态的 run_id。")

        parts.append(f"本章节已汇总 {len(matched)} 个来源，覆盖主题：{topic_names}。")

        if status == "WARN":
            parts.append("本章节当前结论需优先人工复核。")

        if any(s.topic == "alert" for s in matched):
            parts.append("由于关联告警来源，应重点关注异常、阻塞项或缺口信号。")

        if any(s.topic == "risk" for s in matched):
            parts.append("由于关联风控来源，应重点关注 reject / adjust / WARN 的影响。")

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

        if latest_run_id is not None:
            parts.append(f"当前最新可识别的回测运行为 run_id={latest_run_id}。")
        elif latest_run_ids:
            parts.append(
                "当前已识别到回测相关 run_id：" + ", ".join(str(i) for i in latest_run_ids) + "。"
            )
        else:
            parts.append("当前尚未识别到可用于说明回测状态的 run_id。")

        if latest_date:
            parts.append(f"当前来源中可识别的最新报告日为 {latest_date}。")
        else:
            parts.append("当前回测来源未稳定携带报告日，更多是依赖 run_id 来定位最新研究结果。")

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
        if backtest_section and backtest_section.status == "WARN":
            items.append(
                ActionItem(
                    priority="P0",
                    area="08_回测与研究结果",
                    action="补齐 latest backtest run 的稳定来源，避免回测章节退化为 docs-only 总结。",
                    reason="当前回测章节未稳定识别最新运行事实。",
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

        has_acceptance_master = any(
            "docs/modules/m8/acceptance/" in s.relative_path for s in sources
        )
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
        json_path.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
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
        lines: list[str] = [
            "# M9.1.1 Platform Overview Narrator",
            "",
            f"- Report Date: {report.report_date}",
            f"- Generated At: {report.generated_at}",
            f"- Scope: {report.scope}",
            f"- Source Count: {len(report.sources)}",
            "",
        ]

        for section in report.sections:
            lines.extend(
                [
                    f"## {section.title}",
                    "",
                    f"结论：{section.summary}",
                    f"当前对象是什么？{section.object_name}",
                    "最新运行是哪一次？"
                    + (", ".join(str(i) for i in section.latest_run_ids) if section.latest_run_ids else "未识别"),
                    f"最新日期到哪一天？{section.latest_date or '未识别'}",
                    "输入来自哪里？" + ("；".join(section.input_sources) if section.input_sources else "暂无"),
                    "输出产物是什么？" + ("；".join(section.outputs) if section.outputs else "暂无"),
                    f"状态是否正常？{section.status}",
                    "异常或风险是什么？" + ("；".join(section.risks) if section.risks else "暂无明显风险"),
                    "下一步人工应该看什么？" + ("；".join(section.next_checks) if section.next_checks else "人工抽样复核"),
                    "",
                ]
            )

        lines.append("## 14_人工复核建议｜Action Items")
        lines.append("")
        for item in report.action_items:
            lines.append(f"- [{item.priority}] {item.area}：{item.action}｜原因：{item.reason}")
        lines.append("")

        lines.append("## 15_来源文件与 run_id 索引")
        lines.append("")
        for source in report.sources:
            run_text = ", ".join(str(i) for i in source.run_ids) if source.run_ids else "-"
            lines.append(
                f"- {source.relative_path} | topic={source.topic} | date={source.report_date or '-'} | run_id={run_text}"
            )
        lines.append("")
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
                fieldnames=[
                    "priority",
                    "area",
                    "action",
                    "reason",
                    "related_run_ids",
                    "related_sources",
                ],
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