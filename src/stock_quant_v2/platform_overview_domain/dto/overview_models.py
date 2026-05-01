from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

SectionStatus = Literal["OK", "WARN", "MISSING", "INFO", "PASS", "PASS_WITH_WARN", "FAIL"]


@dataclass(slots=True)
class ArtifactSource:
    module: str
    topic: str
    relative_path: str
    format: str
    title: str
    report_date: str | None = None
    run_ids: list[int] = field(default_factory=list)
    summary: str = ""
    headers: list[str] = field(default_factory=list)
    row_count: int | None = None
    top_level_keys: list[str] = field(default_factory=list)


@dataclass(slots=True)
class OverviewSection:
    section_id: str
    title: str
    summary: str
    object_name: str
    latest_run_ids: list[int] = field(default_factory=list)
    latest_date: str | None = None
    input_sources: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    status: SectionStatus = "INFO"
    risks: list[str] = field(default_factory=list)
    next_checks: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ActionItem:
    priority: str
    area: str
    action: str
    reason: str
    related_run_ids: list[int] = field(default_factory=list)
    related_sources: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PlatformOverviewReport:
    generated_at: str
    report_date: str
    scope: str
    sections: list[OverviewSection] = field(default_factory=list)
    action_items: list[ActionItem] = field(default_factory=list)
    sources: list[ArtifactSource] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)