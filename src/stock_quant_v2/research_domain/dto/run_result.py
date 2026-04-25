from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class RunMetricSnapshotDTO:
    run_id: int
    metric_namespace: str
    metric_code: str

    metric_name: str | None = None
    metric_value_numeric: Decimal | None = None
    metric_value_text: str | None = None
    metric_value_json: dict[str, Any] | None = None

    unit: str | None = None

    period_start: date | None = None
    period_end: date | None = None

    dimension_type: str = "PORTFOLIO"
    dimension_key: str = "ALL"
    sequence_no: int = 0


@dataclass(frozen=True)
class RunSeriesSnapshotDTO:
    run_id: int
    series_namespace: str
    series_code: str
    trade_date: date

    instrument_id: int | None = None

    dimension_type: str = "PORTFOLIO"
    dimension_key: str = "ALL"

    value_numeric: Decimal | None = None
    value_text: str | None = None
    value_json: dict[str, Any] | None = None


@dataclass(frozen=True)
class RunArtifactDTO:
    run_id: int
    artifact_type: str
    artifact_code: str
    storage_backend: str
    uri: str

    artifact_name: str | None = None
    mime_type: str | None = None
    file_size_bytes: int | None = None
    checksum_sha256: str | None = None

    payload_schema: dict[str, Any] | None = None
    artifact_metadata: dict[str, Any] = field(default_factory=dict)