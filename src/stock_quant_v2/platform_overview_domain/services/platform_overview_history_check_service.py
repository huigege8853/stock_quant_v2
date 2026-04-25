from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_OVERVIEW_PREFIX_PATTERN = re.compile(
    r"^m9_platform_overview_p(?P<phase>\d+)_(?P<date>20\d{2}-\d{2}-\d{2})(?P<tail>.*)$"
)

_EXPECTED_SUFFIXES = {
    ".md": "markdown",
    ".json": "json",
    "_sections.csv": "sections_csv",
    "_action_items.csv": "action_items_csv",
    "_sources.csv": "sources_csv",
}


@dataclass(slots=True)
class ReportDateInventory:
    report_date: str
    files: dict[str, str] = field(default_factory=dict)

    @property
    def present_keys(self) -> list[str]:
        return sorted(self.files.keys())

    @property
    def missing_keys(self) -> list[str]:
        return sorted(set(_EXPECTED_SUFFIXES.values()) - set(self.files.keys()))

    @property
    def is_complete(self) -> bool:
        return not self.missing_keys


@dataclass(slots=True)
class PlatformOverviewHistoryCheckResult:
    generated_at: str
    requested_report_date: str
    status: str
    latest_available_date: str | None
    previous_complete_date: str | None
    minimum_required_complete_days: int
    available_dates: list[str] = field(default_factory=list)
    complete_dates: list[str] = field(default_factory=list)
    inventories: list[ReportDateInventory] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["inventories"] = [asdict(inv) for inv in self.inventories]
        return payload


class PlatformOverviewHistoryCheckService:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.platform_overview_dir = repo_root / "artifacts" / "m9" / "platform_overview"
        self.output_dir = repo_root / "artifacts" / "m9" / "platform_overview_check"

    def run(
        self,
        report_date: str,
        minimum_required_complete_days: int = 2,
    ) -> PlatformOverviewHistoryCheckResult:
        inventories = self._scan_inventories()
        available_dates = sorted(inv.report_date for inv in inventories)
        complete_dates = sorted(inv.report_date for inv in inventories if inv.is_complete)

        latest_available_date = available_dates[-1] if available_dates else None
        previous_complete_date = self._previous_complete_date(
            complete_dates=complete_dates,
            report_date=report_date,
        )

        status, risks, next_steps = self._evaluate(
            requested_report_date=report_date,
            inventories=inventories,
            complete_dates=complete_dates,
            minimum_required_complete_days=minimum_required_complete_days,
            previous_complete_date=previous_complete_date,
        )

        summary = self._build_summary(
            requested_report_date=report_date,
            status=status,
            latest_available_date=latest_available_date,
            previous_complete_date=previous_complete_date,
            complete_dates=complete_dates,
            minimum_required_complete_days=minimum_required_complete_days,
        )

        return PlatformOverviewHistoryCheckResult(
            generated_at=datetime.now(timezone.utc).isoformat(),
            requested_report_date=report_date,
            status=status,
            latest_available_date=latest_available_date,
            previous_complete_date=previous_complete_date,
            minimum_required_complete_days=minimum_required_complete_days,
            available_dates=available_dates,
            complete_dates=complete_dates,
            inventories=inventories,
            risks=risks,
            next_steps=next_steps,
            summary=summary,
        )

    def export(self, result: PlatformOverviewHistoryCheckResult) -> dict[str, Path]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        prefix = f"m9_platform_overview_history_check_p1_{result.requested_report_date}"

        md_path = self.output_dir / f"{prefix}.md"
        json_path = self.output_dir / f"{prefix}.json"
        csv_path = self.output_dir / f"{prefix}_inventory.csv"

        md_path.write_text(self._render_markdown(result), encoding="utf-8")
        json_path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._write_inventory_csv(csv_path, result)

        return {
            "markdown": md_path,
            "json": json_path,
            "inventory_csv": csv_path,
        }

    def _scan_inventories(self) -> list[ReportDateInventory]:
        if not self.platform_overview_dir.exists():
            return []

        grouped: dict[str, ReportDateInventory] = {}

        for path in self.platform_overview_dir.iterdir():
            if not path.is_file():
                continue

            matched = _OVERVIEW_PREFIX_PATTERN.match(path.name)
            if not matched:
                continue

            report_date = matched.group("date")
            tail = matched.group("tail")

            artifact_key = self._resolve_artifact_key(path.name, tail)
            if artifact_key is None:
                continue

            inventory = grouped.setdefault(report_date, ReportDateInventory(report_date=report_date))
            inventory.files[artifact_key] = path.name

        return sorted(grouped.values(), key=lambda x: x.report_date)

    @staticmethod
    def _resolve_artifact_key(filename: str, tail: str) -> str | None:
        if tail == ".md":
            return "markdown"
        if tail == ".json":
            return "json"
        if tail == "_sections.csv":
            return "sections_csv"
        if tail == "_action_items.csv":
            return "action_items_csv"
        if tail == "_sources.csv":
            return "sources_csv"
        return None

    @staticmethod
    def _previous_complete_date(
        complete_dates: list[str],
        report_date: str,
    ) -> str | None:
        previous_dates = [d for d in complete_dates if d < report_date]
        return previous_dates[-1] if previous_dates else None

    def _evaluate(
        self,
        requested_report_date: str,
        inventories: list[ReportDateInventory],
        complete_dates: list[str],
        minimum_required_complete_days: int,
        previous_complete_date: str | None,
    ) -> tuple[str, list[str], list[str]]:
        risks: list[str] = []
        next_steps: list[str] = []

        inventory_map = {inv.report_date: inv for inv in inventories}
        requested_inventory = inventory_map.get(requested_report_date)

        if requested_inventory is None:
            risks.append(f"未发现请求报告日 {requested_report_date} 的 platform overview 产物。")
            next_steps.append("先生成当前报告日的 platform overview 全套产物。")
            return "FAIL", risks, next_steps

        if not requested_inventory.is_complete:
            risks.append(
                f"报告日 {requested_report_date} 的 platform overview 产物不完整，缺少："
                + ", ".join(requested_inventory.missing_keys)
                + "。"
            )
            next_steps.append("补齐当前报告日缺失的 md/json/sections/action_items/sources 产物。")
            return "FAIL", risks, next_steps

        if len(complete_dates) < minimum_required_complete_days:
            risks.append(
                f"完整 platform overview 报告日数量仅有 {len(complete_dates)} 个，低于要求的 {minimum_required_complete_days} 个。"
            )
            next_steps.append("至少保留最近两个完整报告日的 platform overview 产物。")
            return "WARN", risks, next_steps

        if previous_complete_date is None:
            risks.append(
                f"当前报告日 {requested_report_date} 已完整，但未识别到更早的完整报告日，13_与上一报告日对比 仍不能稳定形成 comparison window。"
            )
            next_steps.append("补齐上一报告日的完整 platform overview 产物。")
            return "WARN", risks, next_steps

        next_steps.append(
            f"当前已识别 previous_complete_date={previous_complete_date}，后续可验证 13_与上一报告日对比 是否从 WARN 收敛为 OK。"
        )
        return "PASS", risks, next_steps

    @staticmethod
    def _build_summary(
        requested_report_date: str,
        status: str,
        latest_available_date: str | None,
        previous_complete_date: str | None,
        complete_dates: list[str],
        minimum_required_complete_days: int,
    ) -> str:
        parts: list[str] = [f"requested_report_date={requested_report_date}。"]
        if latest_available_date:
            parts.append(f"latest_available_date={latest_available_date}。")
        else:
            parts.append("当前未识别到任何 platform overview 历史产物。")

        parts.append(f"complete_dates_count={len(complete_dates)}。")

        if previous_complete_date:
            parts.append(f"previous_complete_date={previous_complete_date}。")
        else:
            parts.append("尚未识别到可用于 day-over-day comparison 的 previous_complete_date。")

        if status == "PASS":
            parts.append("当前历史产物保留要求已满足。")
        elif status == "WARN":
            parts.append(
                f"当前历史产物保留仍不足以稳定支持 day-over-day comparison，至少需要 {minimum_required_complete_days} 个完整报告日。"
            )
        else:
            parts.append("当前历史产物状态不足以支撑有效检查，需先补齐当前报告日产物。")

        return " ".join(parts)

    @staticmethod
    def _render_markdown(result: PlatformOverviewHistoryCheckResult) -> str:
        lines: list[str] = [
            "# M9.1.1 Platform Overview History Check",
            "",
            f"- Requested Report Date: {result.requested_report_date}",
            f"- Generated At: {result.generated_at}",
            f"- Status: {result.status}",
            f"- Latest Available Date: {result.latest_available_date or '-'}",
            f"- Previous Complete Date: {result.previous_complete_date or '-'}",
            f"- Minimum Required Complete Days: {result.minimum_required_complete_days}",
            "",
            "## Summary",
            "",
            result.summary,
            "",
            "## Risks",
            "",
        ]

        if result.risks:
            for risk in result.risks:
                lines.append(f"- {risk}")
        else:
            lines.append("- 无阻塞性风险。")

        lines.extend(["", "## Next Steps", ""])
        for step in result.next_steps:
            lines.append(f"- {step}")

        lines.extend(["", "## Inventory", ""])
        for inv in result.inventories:
            lines.append(f"### {inv.report_date}")
            lines.append("")
            lines.append(f"- Complete: {'YES' if inv.is_complete else 'NO'}")
            lines.append(f"- Present Keys: {', '.join(inv.present_keys) if inv.present_keys else '-'}")
            lines.append(f"- Missing Keys: {', '.join(inv.missing_keys) if inv.missing_keys else '-'}")
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _write_inventory_csv(path: Path, result: PlatformOverviewHistoryCheckResult) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "report_date",
                    "is_complete",
                    "present_keys",
                    "missing_keys",
                    "markdown",
                    "json",
                    "sections_csv",
                    "action_items_csv",
                    "sources_csv",
                ],
            )
            writer.writeheader()
            for inv in result.inventories:
                writer.writerow(
                    {
                        "report_date": inv.report_date,
                        "is_complete": "YES" if inv.is_complete else "NO",
                        "present_keys": "|".join(inv.present_keys),
                        "missing_keys": "|".join(inv.missing_keys),
                        "markdown": inv.files.get("markdown", ""),
                        "json": inv.files.get("json", ""),
                        "sections_csv": inv.files.get("sections_csv", ""),
                        "action_items_csv": inv.files.get("action_items_csv", ""),
                        "sources_csv": inv.files.get("sources_csv", ""),
                    }
                )