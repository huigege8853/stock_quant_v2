from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from stock_quant_v2.platform_overview_domain.dto.overview_models import ArtifactSource

_ALLOWED_SUFFIXES = {".md", ".json", ".csv", ".txt"}
_DATE_PATTERN = re.compile(r"(20\d{2}-\d{2}-\d{2})")
_RUN_ID_PATTERN = re.compile(
    r"(?:^|[_-])(run_|r|src|adj|t|o|f|p|s)(\d{2,})\b",
    re.IGNORECASE,
)


@dataclass(slots=True)
class ArtifactDiscoveryConfig:
    repo_root: Path

    @property
    def preferred_acceptance_files(self) -> list[Path]:
        base = self.repo_root / "docs" / "modules" / "m8" / "acceptance"
        return [
            base / "00_m8_acceptance_index.md",
            base / "01_m8_acceptance_master.md",
            base / "02_m8_acceptance_registry.json",
            base / "03_m8_acceptance_evidence_manifest.csv",
            base / "04_m8_acceptance_compact_copy.md",
            base / "05_m8_acceptance_history_map.md",
        ]

    @property
    def scan_roots(self) -> list[Path]:
        return [
            self.repo_root / "artifacts" / "m2",
            self.repo_root / "artifacts" / "m3",
            self.repo_root / "artifacts" / "m4",
            self.repo_root / "artifacts" / "m5",
            self.repo_root / "artifacts" / "m6",
            self.repo_root / "artifacts" / "m7",
            self.repo_root / "artifacts" / "m8",
            self.repo_root / "artifacts" / "m9",
            self.repo_root / "docs" / "modules" / "m2",
            self.repo_root / "docs" / "modules" / "m3",
            self.repo_root / "docs" / "modules" / "m4",
            self.repo_root / "docs" / "modules" / "m5",
            self.repo_root / "docs" / "modules" / "m6",
            self.repo_root / "docs" / "modules" / "m7",
            self.repo_root / "docs" / "modules" / "m8",
            self.repo_root / "docs" / "modules" / "m9",
        ]


class PlatformOverviewArtifactReader:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.config = ArtifactDiscoveryConfig(repo_root=repo_root)

    def scan(self) -> list[ArtifactSource]:
        candidates: dict[str, Path] = {}

        for path in self.config.preferred_acceptance_files:
            if path.exists() and path.is_file():
                candidates[str(path.resolve())] = path

        for root in self.config.scan_roots:
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                if path.suffix.lower() not in _ALLOWED_SUFFIXES:
                    continue
                candidates[str(path.resolve())] = path

        sources: list[ArtifactSource] = []
        for path in sorted(candidates.values()):
            built = self._build_source(path)
            if built is not None:
                sources.append(built)
        return sources

    def _build_source(self, path: Path) -> ArtifactSource | None:
        module, topic = self._classify_path(path)
        relative_path = path.relative_to(self.repo_root).as_posix()
        report_date = self._extract_report_date(path.name)
        run_ids = self._extract_run_ids(path.name)

        summary = ""
        headers: list[str] = []
        row_count: int | None = None
        top_level_keys: list[str] = []

        try:
            suffix = path.suffix.lower()
            if suffix == ".json":
                summary, top_level_keys = self._read_json_summary(path)
            elif suffix == ".csv":
                summary, headers, row_count = self._read_csv_summary(path)
            else:
                summary = self._read_text_summary(path)
        except Exception as exc:  # pragma: no cover
            summary = f"failed_to_read: {exc}"

        return ArtifactSource(
            module=module,
            topic=topic,
            relative_path=relative_path,
            format=path.suffix.lower().lstrip("."),
            title=path.stem,
            report_date=report_date,
            run_ids=run_ids,
            summary=summary,
            headers=headers,
            row_count=row_count,
            top_level_keys=top_level_keys,
        )

    def _classify_path(self, path: Path) -> tuple[str, str]:
        relative = path.relative_to(self.repo_root)
        parts = relative.parts
        if not parts:
            return "misc", "misc"

        if parts[0] == "artifacts":
            module = parts[1] if len(parts) > 1 else "artifacts"
            topic = parts[2] if len(parts) > 2 else "root"
            return module, topic

        if parts[0] == "docs" and len(parts) > 2 and parts[1] == "modules":
            module_name = parts[2]
            if len(parts) > 3 and parts[3] == "acceptance":
                return f"docs_{module_name}", "acceptance"
            return f"docs_{module_name}", f"{module_name}_docs"

        return "misc", "misc"

    @staticmethod
    def _extract_report_date(filename: str) -> str | None:
        match = _DATE_PATTERN.search(filename)
        return match.group(1) if match else None

    @staticmethod
    def _extract_run_ids(filename: str) -> list[int]:
        run_ids = {int(match.group(2)) for match in _RUN_ID_PATTERN.finditer(filename)}
        return sorted(run_ids)

    def _read_json_summary(self, path: Path) -> tuple[str, list[str]]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            keys = list(payload.keys())[:12]
            if payload.get("summary_type") in {"m3_readiness", "m4_strategy_signal", "m5_backtest_execution"}:
                return self._bridge_json_summary(payload), keys
            if self._looks_like_historical_backfill(payload):
                return self._historical_backfill_json_summary(payload), keys
            if "summary" in payload and isinstance(payload["summary"], str):
                return payload["summary"], keys
            return f"json keys: {', '.join(keys)}", keys
        if isinstance(payload, list):
            return f"json list items: {len(payload)}", []
        return f"json type: {type(payload).__name__}", []

    @staticmethod
    def _bridge_json_summary(payload: dict[str, Any]) -> str:
        status = str(payload.get("status", "INFO"))
        human_summary = str(payload.get("human_summary", payload.get("summary", ""))).replace("|", "/")
        latest_run_id = payload.get("latest_run_id")
        report_date = payload.get("report_date")
        summary_type = payload.get("summary_type", "bridge")

        parts = [f"summary_type={summary_type}", f"bridge_status={status}"]
        if latest_run_id is not None:
            parts.append(f"latest_run_id={latest_run_id}")
        if report_date:
            parts.append(f"report_date={report_date}")
        if human_summary:
            parts.append(f"human_summary={human_summary}")
        return " | ".join(parts)

    @staticmethod
    def _looks_like_historical_backfill(payload: dict[str, Any]) -> bool:
        stage = str(payload.get("stage", "")).lower()
        keys = set(payload.keys())
        return "historical" in stage or "backfill" in stage or {"overall_status", "start_date", "end_date", "frequency"}.issubset(keys)

    @staticmethod
    def _historical_backfill_json_summary(payload: dict[str, Any]) -> str:
        fields = [
            ("stage", payload.get("stage")),
            ("overall_status", payload.get("overall_status")),
            ("start_date", payload.get("start_date")),
            ("end_date", payload.get("end_date")),
            ("frequency", payload.get("frequency")),
            ("strategy_code", payload.get("strategy_code")),
            ("version_code", payload.get("version_code")),
            ("target_type", payload.get("target_type")),
            ("generated_at", payload.get("generated_at")),
        ]
        parts = [f"{k}={v}" for k, v in fields if v not in (None, "")]
        return "historical_backfill | " + " | ".join(parts) if parts else "historical_backfill json"

    @staticmethod
    def _read_csv_summary(path: Path) -> tuple[str, list[str], int]:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
        if not rows:
            return "csv empty", [], 0
        headers = rows[0]
        row_count = max(len(rows) - 1, 0)
        status_counts = PlatformOverviewArtifactReader._counts_from_csv_rows(headers, rows[1:], {"status", "result_status"})
        severity_counts = PlatformOverviewArtifactReader._counts_from_csv_rows(headers, rows[1:], {"severity", "level", "alert_level", "priority"})
        status_text = ""
        if status_counts:
            status_text += "; statuses: " + ", ".join(f"{k}={v}" for k, v in sorted(status_counts.items()))
        if severity_counts:
            status_text += "; severities: " + ", ".join(f"{k}={v}" for k, v in sorted(severity_counts.items()))
        return (
            f"csv rows: {row_count}; headers: {', '.join(headers[:8])}{status_text}",
            headers,
            row_count,
        )

    @staticmethod
    def _counts_from_csv_rows(headers: list[str], rows: list[list[str]], candidate_columns: set[str]) -> dict[str, int]:
        lowered = [h.strip().lower() for h in headers]
        index = next((i for i, name in enumerate(lowered) if name in candidate_columns), None)
        if index is None:
            return {}
        counts: dict[str, int] = {}
        for row in rows:
            if index >= len(row):
                continue
            value = row[index].strip()
            if not value:
                continue
            counts[value] = counts.get(value, 0) + 1
        return counts

    @staticmethod
    def _read_text_summary(path: Path) -> str:
        text = path.read_text(encoding="utf-8", errors="ignore")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        snippet = " | ".join(lines[:4])
        return snippet[:420] if snippet else "text file with no non-empty lines"
