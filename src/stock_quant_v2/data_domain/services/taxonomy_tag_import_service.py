"""Import strategy taxonomy tags into existing tag / instrument_tag tables.

This service is intentionally schema-preserving: it does not create tables,
modify Alembic migrations, generate strategy_signal, run M5 backtests, or touch
paper trading / risk decisions.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import time
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from stock_quant_v2.data_domain.repositories.tag_repository import TagRepository
from stock_quant_v2.db.models.core.tag import Tag
from stock_quant_v2.db.models.meta.instrument import MetaInstrument

SW_INDUSTRY_TAG_TYPES = ("SW_INDUSTRY_L1", "SW_INDUSTRY_L2", "SW_INDUSTRY_L3")
CONCEPT_EM_TAG_TYPE = "CONCEPT_EM"
SW_TAXONOMY_SOURCE = "SW_2021"
CONCEPT_EM_TAXONOMY_SOURCE = "EASTMONEY"
SW_SOURCE_PROVIDER = "sw_industry_2021_csv"
SW_AKSHARE_SOURCE_PROVIDER = "sw_industry_akshare"
CONCEPT_EM_SOURCE_PROVIDER = "eastmoney_concept_akshare"
DEFAULT_EFFECTIVE_FROM = date(1990, 1, 1)
MAX_TAG_CODE_LEN = 64
MAX_TAG_NAME_LEN = 128
CSV_READ_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "gbk", "cp936", "big5", "utf-16", "utf-16-le", "utf-16-be")
CSV_TEXT_BOMS = (b"\xff\xfe", b"\xfe\xff")
LEGULEGU_SW_OVERVIEW_URL = "https://legulegu.com/stockdata/sw-industry-overview"
LEGULEGU_SW_CONS_URL_TEMPLATE = "https://legulegu.com/stockdata/index-composition?industryCode={industry_code}"
LEGULEGU_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


@dataclass(slots=True)
class TaxonomyImportStats:
    import_name: str
    source: str
    tag_type: str | None = None
    input_rows: int = 0
    tag_upsert_rows: int = 0
    instrument_tag_upsert_rows: int = 0
    skipped_rows: int = 0
    missing_instruments: int = 0
    error_rows: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)
    sample_rows: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "import_name": self.import_name,
            "source": self.source,
            "tag_type": self.tag_type,
            "input_rows": self.input_rows,
            "tag_upsert_rows": self.tag_upsert_rows,
            "instrument_tag_upsert_rows": self.instrument_tag_upsert_rows,
            "skipped_rows": self.skipped_rows,
            "missing_instruments": self.missing_instruments,
            "error_rows": self.error_rows,
            "errors": self.errors[:50],
            "sample_rows": self.sample_rows[:20],
        }


@dataclass(slots=True)
class TaxonomyImportResult:
    run_id: int | None
    started_at: str
    finished_at: str | None = None
    status: str = "RUNNING"
    stats: list[TaxonomyImportStats] = field(default_factory=list)
    artifact_paths: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "stats": [item.to_dict() for item in self.stats],
            "artifact_paths": self.artifact_paths,
        }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip()
    if not text_value or text_value.lower() in {"nan", "none", "null"}:
        return None
    return text_value


def normalize_symbol(value: Any) -> str | None:
    text_value = normalize_text(value)
    if not text_value:
        return None
    text_value = text_value.upper().replace(" ", "")
    if "." in text_value:
        text_value = text_value.split(".", 1)[0]
    if text_value.startswith(("SH", "SZ", "BJ")) and len(text_value) >= 8:
        text_value = text_value[2:]
    return text_value.zfill(6) if text_value.isdigit() and len(text_value) < 6 else text_value


def infer_exchange_code(symbol: str | None) -> str | None:
    if not symbol:
        return None
    if symbol.startswith(("600", "601", "603", "605", "688", "689", "900")):
        return "SSE"
    if symbol.startswith(("000", "001", "002", "003", "300", "301", "200")):
        return "SZSE"
    if symbol.startswith(("430", "830", "831", "832", "833", "834", "835", "836", "837", "838", "839", "870", "871", "872", "873", "920")):
        return "BSE"
    return None


def normalize_tag_code(value: Any, *, prefix: str | None = None) -> str | None:
    text_value = normalize_text(value)
    if not text_value:
        return None
    text_value = text_value.replace(" ", "_").replace("/", "_")
    if prefix and not text_value.startswith(prefix):
        text_value = f"{prefix}{text_value}"
    if len(text_value) > MAX_TAG_CODE_LEN:
        digest = hashlib.sha1(text_value.encode("utf-8")).hexdigest()[:12]
        text_value = f"{text_value[: MAX_TAG_CODE_LEN - 13]}_{digest}"
    return text_value


def normalize_tag_name(value: Any, *, fallback: str) -> str:
    text_value = normalize_text(value) or fallback
    return text_value[:MAX_TAG_NAME_LEN]


def first_value(row: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in row:
            value = row.get(key)
            if normalize_text(value) is not None:
                return value
    return None


def parse_date_value(value: Any, default: date | None = None) -> date | None:
    text_value = normalize_text(value)
    if not text_value:
        return default
    text_value = text_value[:10].replace("/", "-")
    try:
        return date.fromisoformat(text_value)
    except ValueError:
        return default


def _excel_column_index(cell_ref: str | None) -> int | None:
    if not cell_ref:
        return None
    match = re.match(r"([A-Z]+)", cell_ref.upper())
    if not match:
        return None
    index = 0
    for char in match.group(1):
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def _read_xlsx_rows(path: Path) -> list[dict[str, Any]]:
    """Read the first worksheet from an XLSX file without extra dependencies.

    Some Excel exports are accidentally saved with a .csv suffix while the
    content is still an XLSX zip package. Detecting and reading those files here
    prevents taxonomy import from failing on a misleading extension.
    """

    ns = {
        "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "pkg_rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    }

    def child_text(element: ET.Element | None, path_expr: str) -> str:
        if element is None:
            return ""
        found = element.find(path_expr, ns)
        if found is None or found.text is None:
            return ""
        return found.text

    with zipfile.ZipFile(path) as workbook_zip:
        names = set(workbook_zip.namelist())
        if "xl/workbook.xml" not in names:
            raise ValueError(f"Excel workbook.xml not found: {path}")

        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in names:
            shared_root = ET.fromstring(workbook_zip.read("xl/sharedStrings.xml"))
            for item in shared_root.findall("main:si", ns):
                texts = [node.text or "" for node in item.findall(".//main:t", ns)]
                shared_strings.append("".join(texts))

        sheet_path = "xl/worksheets/sheet1.xml"
        try:
            workbook_root = ET.fromstring(workbook_zip.read("xl/workbook.xml"))
            rel_id = None
            first_sheet = workbook_root.find("main:sheets/main:sheet", ns)
            if first_sheet is not None:
                rel_id = first_sheet.attrib.get(f"{{{ns['rel']}}}id")
            if rel_id and "xl/_rels/workbook.xml.rels" in names:
                rels_root = ET.fromstring(workbook_zip.read("xl/_rels/workbook.xml.rels"))
                for rel in rels_root.findall("pkg_rel:Relationship", ns):
                    if rel.attrib.get("Id") == rel_id:
                        target = rel.attrib.get("Target", "worksheets/sheet1.xml")
                        sheet_path = "xl/" + target.lstrip("/") if not target.startswith("xl/") else target
                        break
        except Exception:
            sheet_path = "xl/worksheets/sheet1.xml"

        if sheet_path not in names:
            worksheet_names = sorted(name for name in names if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"))
            if not worksheet_names:
                raise ValueError(f"No worksheet found in XLSX file: {path}")
            sheet_path = worksheet_names[0]

        sheet_root = ET.fromstring(workbook_zip.read(sheet_path))
        matrix: list[list[str]] = []
        for row_element in sheet_root.findall(".//main:sheetData/main:row", ns):
            values: list[str] = []
            for cell in row_element.findall("main:c", ns):
                col_index = _excel_column_index(cell.attrib.get("r"))
                if col_index is None:
                    col_index = len(values)
                while len(values) <= col_index:
                    values.append("")

                cell_type = cell.attrib.get("t")
                if cell_type == "s":
                    raw_value = child_text(cell, "main:v")
                    value = shared_strings[int(raw_value)] if raw_value.isdigit() and int(raw_value) < len(shared_strings) else raw_value
                elif cell_type == "inlineStr":
                    value = child_text(cell, "main:is/main:t")
                else:
                    value = child_text(cell, "main:v")
                values[col_index] = value
            if any(normalize_text(value) is not None for value in values):
                matrix.append(values)

    if not matrix:
        return []

    headers = [normalize_text(value) or "" for value in matrix[0]]
    rows: list[dict[str, Any]] = []
    for raw_row in matrix[1:]:
        row: dict[str, Any] = {}
        for index, header in enumerate(headers):
            if not header:
                continue
            row[header] = raw_row[index] if index < len(raw_row) else ""
        if any(normalize_text(value) is not None for value in row.values()):
            rows.append(row)
    return rows


def _parse_csv_text(text_value: str) -> tuple[list[dict[str, Any]], list[str] | None]:
    reader = csv.DictReader(io.StringIO(text_value, newline=""))
    rows = [dict(row) for row in reader]
    return rows, reader.fieldnames


def _csv_parse_looks_valid(rows: list[dict[str, Any]], fieldnames: list[str] | None) -> bool:
    if fieldnames is None:
        return False
    cleaned_fieldnames = [normalize_text(name) for name in fieldnames if normalize_text(name) is not None]
    if not cleaned_fieldnames:
        return False
    known_headers = {
        "symbol",
        "stock_name",
        "stock_code",
        "sw_l1_code",
        "sw_l1_name",
        "sw_l2_code",
        "sw_l2_name",
        "sw_l3_code",
        "sw_l3_name",
        "effective_from",
        "股票代码",
        "股票简称",
        "申万1级",
        "申万2级",
        "申万3级",
        "纳入时间",
    }
    if any(name in known_headers for name in cleaned_fieldnames):
        return True
    if len(cleaned_fieldnames) >= 2 and rows:
        return True
    return False


def read_csv_rows(path: str | Path, *, encodings: Sequence[str] = CSV_READ_ENCODINGS) -> list[dict[str, Any]]:
    """Read a taxonomy input table with deterministic fallback.

    Strategy taxonomy inputs often come from Excel / Windows exports. Accept
    common text encodings and also XLSX workbooks that were accidentally named
    with a .csv suffix. Legacy .xls binaries are detected with a clear error so
    operators can re-save them as CSV UTF-8 or XLSX.
    """

    csv_path = Path(path)
    raw = csv_path.read_bytes()

    if not raw:
        return []

    if zipfile.is_zipfile(csv_path):
        return _read_xlsx_rows(csv_path)

    if raw.startswith(b"\xd0\xcf\x11\xe0"):
        raise ValueError(
            f"Unsupported legacy Excel .xls binary file: {csv_path}. "
            "Please re-save it as CSV UTF-8 or XLSX, then rerun the import."
        )

    # UTF-16 without a BOM can decode many GBK/ANSI byte streams into garbage
    # without raising UnicodeDecodeError. Prefer UTF-16 only when a BOM is
    # present, otherwise try ordinary CSV encodings first.
    ordered_encodings = list(encodings)
    if not raw.startswith(CSV_TEXT_BOMS):
        ordered_encodings = [encoding for encoding in ordered_encodings if not encoding.startswith("utf-16")] + [
            encoding for encoding in ordered_encodings if encoding.startswith("utf-16")
        ]

    errors: list[str] = []
    for encoding in ordered_encodings:
        try:
            text_value = raw.decode(encoding)
            if "\x00" in text_value and not encoding.startswith("utf-16"):
                errors.append(f"{encoding}: decoded text contains NUL bytes; likely not a plain CSV")
                continue

            rows, fieldnames = _parse_csv_text(text_value)
            if _csv_parse_looks_valid(rows, fieldnames):
                return rows
            errors.append(f"{encoding}: decoded but CSV headers/rows did not look valid")
        except UnicodeDecodeError as exc:
            errors.append(f"{encoding}: {exc}")

    first_bytes = raw[:16].hex(" ")
    raise UnicodeDecodeError(
        "csv_encoding_fallback",
        raw,
        0,
        min(len(raw), 1),
        "Unable to decode taxonomy input as CSV or XLSX. "
        f"first_16_bytes={first_bytes}. Supported text encodings: {', '.join(encodings)}. "
        "If this is exported from Excel, save it as CSV UTF-8 or XLSX. "
        "Details: " + "; ".join(errors),
    )


class TaxonomyTagImportService:
    """Import SW industry and Eastmoney concept classifications."""

    def __init__(self) -> None:
        self.tag_repo = TagRepository()
        self._instrument_lookup_cache: dict[str, Any] | None = None
        self._tag_id_cache: dict[tuple[str, str], int] = {}

    def import_sw_industry_csv(
        self,
        *,
        session: Session,
        csv_path: str | Path,
        effective_from: date = DEFAULT_EFFECTIVE_FROM,
        effective_to: date | None = None,
        confidence: Decimal = Decimal("1.0000"),
    ) -> TaxonomyImportStats:
        return self.import_sw_industry_rows(
            session=session,
            rows=read_csv_rows(csv_path),
            source=str(csv_path),
            source_provider=SW_SOURCE_PROVIDER,
            effective_from=effective_from,
            effective_to=effective_to,
            confidence=confidence,
            import_name="sw_industry_csv",
        )

    def import_sw_industry_rows(
        self,
        *,
        session: Session,
        rows: Iterable[Mapping[str, Any]],
        source: str,
        source_provider: str,
        effective_from: date = DEFAULT_EFFECTIVE_FROM,
        effective_to: date | None = None,
        confidence: Decimal = Decimal("1.0000"),
        import_name: str = "sw_industry_mapping",
    ) -> TaxonomyImportStats:
        rows_list = list(rows)
        stats = TaxonomyImportStats(
            import_name=import_name,
            source=source,
            tag_type="SW_INDUSTRY_L1/L2/L3",
            input_rows=len(rows_list),
        )

        for index, row in enumerate(rows_list, start=1):
            symbol = normalize_symbol(
                first_value(row, ["symbol", "ticker", "stock_code", "证券代码", "股票代码", "代码", "instrument_symbol"])
            )
            instrument_code = normalize_text(first_value(row, ["instrument_code", "instrument", "ts_code"]))
            row_effective_from = parse_date_value(
                first_value(row, ["effective_from", "start_date", "in_date", "纳入时间", "生效日期"]),
                effective_from,
            ) or effective_from
            row_effective_to = parse_date_value(first_value(row, ["effective_to", "end_date", "out_date", "失效日期"]), effective_to)

            instrument_id = self._find_instrument_id(session, symbol=symbol, instrument_code=instrument_code)
            if instrument_id is None:
                stats.missing_instruments += 1
                self._append_error(stats, index, row, "INSTRUMENT_NOT_FOUND", f"instrument not found for symbol={symbol} instrument_code={instrument_code}")
                continue

            levels = [
                (
                    "SW_INDUSTRY_L1",
                    first_value(row, ["sw_l1_code", "industry_l1_code", "level1_code", "申万一级代码", "一级行业代码"]),
                    first_value(row, ["sw_l1_name", "industry_l1_name", "level1_name", "申万1级", "申万一级行业", "一级行业", "一级行业名称"]),
                ),
                (
                    "SW_INDUSTRY_L2",
                    first_value(row, ["sw_l2_code", "industry_l2_code", "level2_code", "申万二级代码", "二级行业代码"]),
                    first_value(row, ["sw_l2_name", "industry_l2_name", "level2_name", "申万2级", "申万二级行业", "二级行业", "二级行业名称"]),
                ),
                (
                    "SW_INDUSTRY_L3",
                    first_value(row, ["sw_l3_code", "industry_l3_code", "level3_code", "申万三级代码", "三级行业代码", "行业代码"]),
                    first_value(row, ["sw_l3_name", "industry_l3_name", "level3_name", "申万3级", "申万三级行业", "三级行业", "三级行业名称", "行业名称"]),
                ),
            ]

            imported_for_row = 0
            for tag_type, raw_code, raw_name in levels:
                tag_name = normalize_text(raw_name)
                tag_code = normalize_tag_code(raw_code or tag_name, prefix="SW")
                if not tag_code or not tag_name:
                    continue
                tag_id = self._upsert_tag(
                    session,
                    tag_type=tag_type,
                    tag_code=tag_code,
                    tag_name=tag_name,
                    taxonomy_source=SW_TAXONOMY_SOURCE,
                )
                stats.tag_upsert_rows += 1
                self._upsert_instrument_tag(
                    session,
                    instrument_id=instrument_id,
                    tag_id=tag_id,
                    effective_from=row_effective_from,
                    effective_to=row_effective_to,
                    source_provider=source_provider,
                    confidence=confidence,
                )
                stats.instrument_tag_upsert_rows += 1
                imported_for_row += 1

            if imported_for_row == 0:
                stats.skipped_rows += 1
                self._append_error(stats, index, row, "NO_SW_INDUSTRY_LEVEL", "no SW industry level columns found")
            elif len(stats.sample_rows) < 20:
                stats.sample_rows.append({"symbol": symbol, "instrument_id": instrument_id, "imported_tags": imported_for_row})

        return stats

    def import_concept_em_rows(
        self,
        *,
        session: Session,
        rows: Iterable[Mapping[str, Any]],
        source: str,
        effective_from: date = DEFAULT_EFFECTIVE_FROM,
        effective_to: date | None = None,
        confidence: Decimal = Decimal("0.9000"),
        progress_callback: Callable[[str], None] | None = None,
        import_progress_every: int = 2000,
        commit_every: int = 5000,
    ) -> TaxonomyImportStats:
        rows_list = list(rows)
        stats = TaxonomyImportStats(
            import_name="concept_em_mapping",
            source=source,
            tag_type=CONCEPT_EM_TAG_TYPE,
            input_rows=len(rows_list),
        )

        total = len(rows_list)
        if progress_callback:
            progress_callback(
                "CONCEPT_IMPORT_START "
                f"input_rows={total} import_progress_every={import_progress_every} commit_every={commit_every} "
                "lookup_cache=enabled tag_cache=enabled"
            )

        self._warm_instrument_lookup_cache(session=session, progress_callback=progress_callback)
        last_commit_row = 0

        for index, row in enumerate(rows_list, start=1):
            symbol = normalize_symbol(
                first_value(row, ["symbol", "ticker", "stock_code", "证券代码", "代码", "成分股代码"])
            )
            instrument_code = normalize_text(first_value(row, ["instrument_code", "instrument", "ts_code"]))
            concept_name = normalize_text(first_value(row, ["concept_name", "板块名称", "概念名称", "名称", "concept"]))
            raw_concept_code = first_value(row, ["concept_code", "板块代码", "概念代码", "code"])
            concept_code = normalize_tag_code(raw_concept_code or concept_name, prefix="EMC")
            row_effective_from = parse_date_value(first_value(row, ["effective_from", "start_date", "生效日期"]), effective_from) or effective_from
            row_effective_to = parse_date_value(first_value(row, ["effective_to", "end_date", "失效日期"]), effective_to)

            if not concept_code or not concept_name:
                stats.skipped_rows += 1
                self._append_error(stats, index, row, "CONCEPT_MISSING", "concept_code or concept_name is missing")
                continue

            instrument_id = self._find_instrument_id(session, symbol=symbol, instrument_code=instrument_code)
            if instrument_id is None:
                stats.missing_instruments += 1
                self._append_error(stats, index, row, "INSTRUMENT_NOT_FOUND", f"instrument not found for symbol={symbol} instrument_code={instrument_code}")
                continue

            tag_id = self._upsert_tag(
                session,
                tag_type=CONCEPT_EM_TAG_TYPE,
                tag_code=concept_code,
                tag_name=concept_name,
                taxonomy_source=CONCEPT_EM_TAXONOMY_SOURCE,
            )
            stats.tag_upsert_rows += 1
            self._upsert_instrument_tag(
                session,
                instrument_id=instrument_id,
                tag_id=tag_id,
                effective_from=row_effective_from,
                effective_to=row_effective_to,
                source_provider=CONCEPT_EM_SOURCE_PROVIDER,
                confidence=confidence,
            )
            stats.instrument_tag_upsert_rows += 1
            if len(stats.sample_rows) < 20:
                stats.sample_rows.append({"symbol": symbol, "instrument_id": instrument_id, "concept_code": concept_code, "concept_name": concept_name})

            if progress_callback and import_progress_every and import_progress_every > 0 and index % import_progress_every == 0:
                progress_callback(
                    "CONCEPT_IMPORT_PROGRESS "
                    f"row={index}/{total} instrument_tag_upsert_rows={stats.instrument_tag_upsert_rows} "
                    f"missing_instruments={stats.missing_instruments} skipped_rows={stats.skipped_rows}"
                )

            if commit_every and commit_every > 0 and index % commit_every == 0:
                session.commit()
                last_commit_row = index
                if progress_callback:
                    progress_callback(
                        "CONCEPT_IMPORT_COMMIT "
                        f"row={index}/{total} instrument_tag_upsert_rows={stats.instrument_tag_upsert_rows}"
                    )

        if commit_every and commit_every > 0 and total > 0 and last_commit_row != total:
            session.commit()
            if progress_callback:
                progress_callback(
                    "CONCEPT_IMPORT_COMMIT "
                    f"row={total}/{total} instrument_tag_upsert_rows={stats.instrument_tag_upsert_rows}"
                )

        if progress_callback:
            progress_callback(
                "CONCEPT_IMPORT_DONE "
                f"input_rows={stats.input_rows} instrument_tag_upsert_rows={stats.instrument_tag_upsert_rows} "
                f"missing_instruments={stats.missing_instruments} error_rows={stats.error_rows} skipped_rows={stats.skipped_rows}"
            )

        return stats

    def import_concept_em_csv(
        self,
        *,
        session: Session,
        csv_path: str | Path,
        effective_from: date = DEFAULT_EFFECTIVE_FROM,
        effective_to: date | None = None,
        confidence: Decimal = Decimal("0.9500"),
    ) -> TaxonomyImportStats:
        return self.import_concept_em_rows(
            session=session,
            rows=read_csv_rows(csv_path),
            source=str(csv_path),
            effective_from=effective_from,
            effective_to=effective_to,
            confidence=confidence,
        )

    def import_concept_em_from_akshare(
        self,
        *,
        session: Session,
        ak_module: Any,
        concept_names: Sequence[str] | None = None,
        max_concepts: int | None = None,
        progress_callback: Callable[[str], None] | None = None,
        progress_every: int = 1,
        concept_import_progress_every: int = 2000,
        concept_import_commit_every: int = 5000,
        effective_from: date = DEFAULT_EFFECTIVE_FROM,
        effective_to: date | None = None,
        confidence: Decimal = Decimal("0.9000"),
    ) -> TaxonomyImportStats:
        concept_rows = fetch_eastmoney_concept_rows_from_akshare(
            ak_module=ak_module,
            concept_names=concept_names,
            max_concepts=max_concepts,
            progress_callback=progress_callback,
            progress_every=progress_every,
        )
        return self.import_concept_em_rows(
            session=session,
            rows=concept_rows,
            source="akshare.stock_board_concept_name_em + stock_board_concept_cons_em",
            effective_from=effective_from,
            effective_to=effective_to,
            confidence=confidence,
            progress_callback=progress_callback,
            import_progress_every=concept_import_progress_every,
            commit_every=concept_import_commit_every,
        )

    def _warm_instrument_lookup_cache(self, session: Session, *, progress_callback: Callable[[str], None] | None = None) -> None:
        if self._instrument_lookup_cache is not None:
            return
        if progress_callback:
            progress_callback("INSTRUMENT_LOOKUP_CACHE_START")
        rows = session.execute(
            select(
                MetaInstrument.id,
                MetaInstrument.instrument_code,
                MetaInstrument.symbol,
                MetaInstrument.instrument_type,
                MetaInstrument.is_active,
            ).order_by(MetaInstrument.symbol.asc(), MetaInstrument.is_active.desc(), MetaInstrument.id.asc())
        ).mappings().all()
        by_code: dict[str, int] = {}
        by_symbol: dict[str, int] = {}
        for row in rows:
            instrument_id = int(row["id"])
            instrument_code = normalize_text(row.get("instrument_code"))
            symbol = normalize_symbol(row.get("symbol"))
            instrument_type = normalize_text(row.get("instrument_type"))
            if instrument_code:
                by_code.setdefault(instrument_code, instrument_id)
            if symbol and instrument_type == "EQUITY":
                by_symbol.setdefault(symbol, instrument_id)
        self._instrument_lookup_cache = {"by_code": by_code, "by_symbol": by_symbol}
        if progress_callback:
            progress_callback(
                "INSTRUMENT_LOOKUP_CACHE_DONE "
                f"instrument_code_count={len(by_code)} symbol_count={len(by_symbol)}"
            )

    def _find_instrument_id(self, session: Session, *, symbol: str | None, instrument_code: str | None) -> int | None:
        cache = self._instrument_lookup_cache
        if cache is not None:
            by_code: dict[str, int] = cache.get("by_code", {})
            by_symbol: dict[str, int] = cache.get("by_symbol", {})
            if instrument_code and instrument_code in by_code:
                return by_code[instrument_code]
            if symbol:
                exchange_code = infer_exchange_code(symbol)
                if exchange_code:
                    code = f"{symbol}.{exchange_code}"
                    if code in by_code:
                        return by_code[code]
                found = by_symbol.get(symbol)
                if found is not None:
                    return found
            return None

        if instrument_code:
            stmt = select(MetaInstrument.id).where(MetaInstrument.instrument_code == instrument_code)
            found = session.execute(stmt).scalar_one_or_none()
            if found is not None:
                return int(found)

        if not symbol:
            return None

        exchange_code = infer_exchange_code(symbol)
        if exchange_code:
            code = f"{symbol}.{exchange_code}"
            stmt = select(MetaInstrument.id).where(MetaInstrument.instrument_code == code)
            found = session.execute(stmt).scalar_one_or_none()
            if found is not None:
                return int(found)

        stmt = (
            select(MetaInstrument.id)
            .where(MetaInstrument.symbol == symbol)
            .where(MetaInstrument.instrument_type == "EQUITY")
            .order_by(MetaInstrument.is_active.desc(), MetaInstrument.id.asc())
            .limit(1)
        )
        found = session.execute(stmt).scalar_one_or_none()
        return int(found) if found is not None else None

    def _upsert_tag(
        self,
        session: Session,
        *,
        tag_type: str,
        tag_code: str,
        tag_name: str,
        taxonomy_source: str,
    ) -> int:
        normalized_code = tag_code[:MAX_TAG_CODE_LEN]
        cache_key = (tag_type, normalized_code)
        cached = self._tag_id_cache.get(cache_key)
        if cached is not None:
            return cached
        tag = self.tag_repo.upsert_tag(
            session,
            {
                "tag_type": tag_type,
                "tag_code": normalized_code,
                "tag_name": normalize_tag_name(tag_name, fallback=tag_code),
                "taxonomy_source": taxonomy_source[:32],
                "is_active": True,
            },
        )
        tag_id = int(tag.id)
        self._tag_id_cache[cache_key] = tag_id
        return tag_id

    def _upsert_instrument_tag(
        self,
        session: Session,
        *,
        instrument_id: int,
        tag_id: int,
        effective_from: date,
        effective_to: date | None,
        source_provider: str,
        confidence: Decimal,
    ) -> None:
        self.tag_repo.upsert_instrument_tag(
            session,
            {
                "instrument_id": instrument_id,
                "tag_id": tag_id,
                "effective_from": effective_from,
                "effective_to": effective_to,
                "source_provider": source_provider[:32],
                "confidence": confidence,
            },
        )

    @staticmethod
    def _append_error(stats: TaxonomyImportStats, row_no: int, row: Mapping[str, Any], code: str, message: str) -> None:
        stats.error_rows += 1 if code not in {"INSTRUMENT_NOT_FOUND"} else 0
        if len(stats.errors) < 50:
            stats.errors.append({"row_no": row_no, "issue_code": code, "message": message, "row_sample": {k: row.get(k) for k in list(row.keys())[:12]}})



def _safe_import_requests() -> Any:
    try:
        import requests  # type: ignore

        return requests
    except Exception:  # noqa: BLE001
        return None


def _safe_import_pandas() -> Any:
    try:
        import pandas as pd  # type: ignore

        return pd
    except Exception:  # noqa: BLE001
        return None




def _sleep_for(seconds: float | int | None, *, progress_callback: Callable[[str], None] | None = None, reason: str = "sleep") -> None:
    try:
        delay = float(seconds or 0)
    except (TypeError, ValueError):
        delay = 0.0
    if delay <= 0:
        return
    if progress_callback:
        progress_callback(f"THROTTLE_SLEEP reason={reason} seconds={delay:.2f}")
    time.sleep(delay)


def _is_retryable_http_error(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code is None:
        text_value = str(exc)
        return any(marker in text_value for marker in ("429", "500", "502", "503", "504", "Read timed out", "Connection"))
    return int(status_code) in {429, 500, 502, 503, 504}

def _normalize_sw_industry_code(value: Any) -> str | None:
    text_value = normalize_text(value)
    if not text_value:
        return None
    text_value = text_value.upper().strip()
    match = re.search(r"(\d{6})(?:\.SI)?", text_value)
    if not match:
        return text_value
    return f"{match.group(1)}.SI"


def _extract_sw_third_industries_from_legulegu_text(text: str) -> list[dict[str, Any]]:
    """Extract SW level-3 industry codes from Legulegu overview text."""

    if not text:
        return []
    compact = re.sub(r"\s+", " ", text)
    pattern = re.compile(
        r"(?P<code>85\d{4}\.SI)\s+"
        r"(?P<name>[^\(\[]+?)\s*"
        r"\((?P<count>\d+)\)\s*"
        r"\[(?P<parent>[^\]]+)\]",
        re.UNICODE,
    )
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in pattern.finditer(compact):
        code = _normalize_sw_industry_code(match.group("code"))
        if not code or code in seen:
            continue
        seen.add(code)
        rows.append(
            {
                "行业代码": code,
                "行业名称": normalize_text(match.group("name")),
                "上级行业": normalize_text(match.group("parent")),
                "成份个数": match.group("count"),
            }
        )
    return rows


def _fetch_legulegu_sw_third_info_records(*, progress_callback: Callable[[str], None] | None = None) -> list[dict[str, Any]]:
    requests = _safe_import_requests()
    if requests is None:
        if progress_callback:
            progress_callback("SW_FETCH_LIST_FALLBACK_SKIP requests_not_available")
        return []
    if progress_callback:
        progress_callback(f"SW_FETCH_LIST_FALLBACK start source={LEGULEGU_SW_OVERVIEW_URL}")
    response = requests.get(LEGULEGU_SW_OVERVIEW_URL, headers=LEGULEGU_HEADERS, timeout=30)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    records = _extract_sw_third_industries_from_legulegu_text(response.text)
    if progress_callback:
        progress_callback(f"SW_FETCH_LIST_FALLBACK done third_industry_count={len(records)}")
    return records


def _fetch_legulegu_sw_third_cons_records(
    industry_code: str,
    *,
    progress_callback: Callable[[str], None] | None = None,
    retry_attempts: int = 3,
    retry_backoff_seconds: float = 5.0,
    timeout_seconds: float = 20.0,
) -> list[dict[str, Any]]:
    pd = _safe_import_pandas()
    requests = _safe_import_requests()
    if pd is None or requests is None:
        if progress_callback:
            progress_callback("SW_FETCH_CONS_FALLBACK_SKIP pandas_or_requests_not_available")
        return []
    industry_code = _normalize_sw_industry_code(industry_code) or industry_code
    url = LEGULEGU_SW_CONS_URL_TEMPLATE.format(industry_code=industry_code)
    attempts = max(int(retry_attempts or 1), 1)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            if progress_callback and attempts > 1:
                progress_callback(f"SW_FETCH_CONS_FALLBACK_ATTEMPT code={industry_code} attempt={attempt}/{attempts}")
            response = requests.get(url, headers=LEGULEGU_HEADERS, timeout=float(timeout_seconds or 20.0))
            response.raise_for_status()
            response.encoding = response.apparent_encoding or response.encoding
            frames = pd.read_html(io.StringIO(response.text))
            if not frames:
                return []
            frame = frames[0]
            expected_columns = [
                "序号",
                "股票代码",
                "股票简称",
                "纳入时间",
                "申万1级",
                "申万2级",
                "申万3级",
                "价格",
                "市盈率",
                "市盈率ttm",
                "市净率",
                "股息率",
                "市值",
                "归母净利润同比增长(09-30)",
                "归母净利润同比增长(06-30)",
                "营业收入同比增长(09-30)",
                "营业收入同比增长(06-30)",
            ]
            if len(frame.columns) == len(expected_columns):
                frame.columns = expected_columns
            return _to_records(frame)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt >= attempts or not _is_retryable_http_error(exc):
                break
            _sleep_for(float(retry_backoff_seconds or 0) * attempt, progress_callback=progress_callback, reason=f"legulegu_retry_{industry_code}_{attempt}")
    if last_error is not None:
        raise last_error
    return []

def fetch_sw_industry_rows_from_akshare(
    *,
    ak_module: Any,
    industry_codes: Sequence[str] | None = None,
    max_industries: int | None = None,
    progress_callback: Callable[[str], None] | None = None,
    progress_every: int = 1,
    sw_fetch_delay_seconds: float = 0.0,
    sw_fallback_delay_seconds: float = 2.0,
    sw_fetch_retry_attempts: int = 3,
    sw_fetch_retry_backoff_seconds: float = 5.0,
    sw_fetch_timeout_seconds: float = 20.0,
) -> list[dict[str, Any]]:
    """Fetch SW industry L1/L2/L3 constituent rows through AKShare/Legulegu.

    Primary path:
        akshare.sw_index_third_info() -> akshare.sw_index_third_cons(symbol=...)

    Fallback path:
        If AKShare's overview parser breaks because Legulegu changed page DOM,
        directly parse visible Legulegu text for 850xxx.SI level-3 codes and
        then fetch composition tables from Legulegu.
    """

    if progress_callback:
        progress_callback("SW_FETCH_LIST start source=akshare.sw_index_third_info")

    third_records: list[dict[str, Any]] = []
    primary_error: Exception | None = None
    try:
        third_info_df = ak_module.sw_index_third_info()
        third_records = _to_records(third_info_df)
        if progress_callback:
            progress_callback(f"SW_FETCH_LIST done third_industry_count={len(third_records)} source=akshare")
    except Exception as exc:  # noqa: BLE001
        primary_error = exc
        if progress_callback:
            progress_callback(f"SW_FETCH_LIST_ERROR source=akshare error={type(exc).__name__}: {exc}")

    if not third_records:
        try:
            third_records = _fetch_legulegu_sw_third_info_records(progress_callback=progress_callback)
        except Exception as exc:  # noqa: BLE001
            if progress_callback:
                progress_callback(f"SW_FETCH_LIST_FALLBACK_ERROR source=legulegu error={type(exc).__name__}: {exc}")
            if primary_error is not None:
                raise RuntimeError(
                    "Unable to fetch SW third-level industry list from AKShare or Legulegu fallback. "
                    f"AKShare error: {type(primary_error).__name__}: {primary_error}; "
                    f"Legulegu fallback error: {type(exc).__name__}: {exc}"
                ) from exc
            raise

    if not third_records:
        raise RuntimeError("No SW third-level industry codes were fetched from AKShare or Legulegu fallback.")

    wanted_codes = {
        _normalize_sw_industry_code(code) or normalize_text(code)
        for code in industry_codes or []
        if normalize_text(code)
    }
    selected: list[dict[str, Any]] = []

    for row in third_records:
        industry_code = _normalize_sw_industry_code(first_value(row, ["行业代码", "industry_code", "code", "symbol"]))
        industry_name = normalize_text(first_value(row, ["行业名称", "industry_name", "name"]))
        parent_name = normalize_text(first_value(row, ["上级行业", "parent_name", "parent", "industry_parent"]))
        if not industry_code:
            continue
        if wanted_codes and industry_code not in wanted_codes:
            continue
        selected.append({"industry_code": industry_code, "industry_name": industry_name, "parent_name": parent_name})
        if max_industries is not None and max_industries > 0 and len(selected) >= max_industries:
            break

    if progress_callback:
        progress_callback(f"SW_FETCH_SELECTED total={len(selected)} max_industries={max_industries or 'ALL'}")

    rows: list[dict[str, Any]] = []
    failed_count = 0
    total_selected = len(selected)
    progress_every = max(int(progress_every or 1), 1)
    for index, industry in enumerate(selected, start=1):
        industry_code = industry["industry_code"]
        industry_name = industry.get("industry_name")
        parent_name = industry.get("parent_name")
        should_report = bool(progress_callback) and (index == 1 or index == total_selected or index % progress_every == 0)
        if progress_callback:
            progress_callback(f"SW_FETCH_START {index}/{total_selected} code={industry_code} name={industry_name or ''}")
        if index > 1:
            _sleep_for(sw_fetch_delay_seconds, progress_callback=progress_callback, reason="sw_fetch_between_industries")
        cons_records: list[dict[str, Any]] = []
        last_error: Exception | None = None
        try:
            cons_df = ak_module.sw_index_third_cons(symbol=industry_code)
            cons_records = _to_records(cons_df)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if progress_callback:
                progress_callback(f"SW_FETCH_CONS_ERROR source=akshare {index}/{total_selected} code={industry_code} error={type(exc).__name__}: {exc}")

        if not cons_records:
            try:
                _sleep_for(sw_fallback_delay_seconds, progress_callback=progress_callback, reason="sw_cons_fallback_before_legulegu")
                cons_records = _fetch_legulegu_sw_third_cons_records(
                    industry_code,
                    progress_callback=progress_callback,
                    retry_attempts=sw_fetch_retry_attempts,
                    retry_backoff_seconds=sw_fetch_retry_backoff_seconds,
                    timeout_seconds=sw_fetch_timeout_seconds,
                )
                if progress_callback:
                    progress_callback(f"SW_FETCH_CONS_FALLBACK_DONE {index}/{total_selected} code={industry_code} rows={len(cons_records)}")
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if progress_callback:
                    progress_callback(f"SW_FETCH_CONS_FALLBACK_ERROR {index}/{total_selected} code={industry_code} error={type(exc).__name__}: {exc}")

        if not cons_records:
            failed_count += 1
            if progress_callback:
                if last_error is not None:
                    progress_callback(f"SW_FETCH_ERROR {index}/{total_selected} code={industry_code} error={type(last_error).__name__}: {last_error}")
                else:
                    progress_callback(f"SW_FETCH_ERROR {index}/{total_selected} code={industry_code} error=empty_constituents")
            continue

        if should_report or progress_callback:
            progress_callback(f"SW_FETCH_DONE {index}/{total_selected} code={industry_code} rows={len(cons_records)} accumulated_rows={len(rows)} failed={failed_count}")
        for item in cons_records:
            stock_code = normalize_symbol(first_value(item, ["股票代码", "证券代码", "代码", "stock_code", "symbol", "ticker"]))
            if not stock_code:
                continue
            stock_name = normalize_text(first_value(item, ["股票简称", "证券简称", "名称", "stock_name", "name"]))
            rows.append(
                {
                    "symbol": stock_code,
                    "stock_name": stock_name,
                    "sw_l1_name": normalize_text(first_value(item, ["申万1级", "申万一级", "一级行业", "sw_l1_name"])) or "UNKNOWN_SW_L1",
                    "sw_l2_name": normalize_text(first_value(item, ["申万2级", "申万二级", "二级行业", "sw_l2_name"])) or parent_name or "UNKNOWN_SW_L2",
                    "sw_l3_code": industry_code,
                    "sw_l3_name": normalize_text(first_value(item, ["申万3级", "申万三级", "三级行业", "sw_l3_name"])) or industry_name,
                    "effective_from": normalize_text(first_value(item, ["纳入时间", "计入日期", "start_date", "in_date", "effective_from"])),
                }
            )
    if progress_callback:
        progress_callback(f"SW_FETCH_ALL_DONE selected={len(selected)} rows={len(rows)} failed={failed_count}")
    return rows


def write_source_rows_csv(path: str | Path, rows: Sequence[Mapping[str, Any]]) -> None:
    _write_csv(Path(path), rows)


def fetch_eastmoney_concept_rows_from_akshare(
    *,
    ak_module: Any,
    concept_names: Sequence[str] | None = None,
    max_concepts: int | None = None,
    progress_callback: Callable[[str], None] | None = None,
    progress_every: int = 1,
) -> list[dict[str, Any]]:
    """Fetch Eastmoney concept constituents through AKShare.

    This function keeps AKShare isolated so tests can pass a fake module and so
    production failures do not leak into import-time side effects.
    """

    if progress_callback:
        progress_callback("CONCEPT_FETCH_LIST start source=akshare.stock_board_concept_name_em")
    concept_df = ak_module.stock_board_concept_name_em()
    concept_records = _to_records(concept_df)
    if progress_callback:
        progress_callback(f"CONCEPT_FETCH_LIST done concept_count={len(concept_records)}")
    wanted_names = {name.strip() for name in concept_names or [] if name.strip()}
    selected: list[dict[str, Any]] = []

    for row in concept_records:
        concept_name = normalize_text(first_value(row, ["板块名称", "名称", "concept_name", "name"]))
        concept_code = normalize_text(first_value(row, ["板块代码", "代码", "concept_code", "code"]))
        if not concept_name:
            continue
        if wanted_names and concept_name not in wanted_names:
            continue
        selected.append({"concept_name": concept_name, "concept_code": concept_code})
        if max_concepts is not None and max_concepts > 0 and len(selected) >= max_concepts:
            break

    if progress_callback:
        progress_callback(f"CONCEPT_FETCH_SELECTED total={len(selected)} max_concepts={max_concepts or 'ALL'}")

    rows: list[dict[str, Any]] = []
    failed_count = 0
    total_selected = len(selected)
    progress_every = max(int(progress_every or 1), 1)
    for index, concept in enumerate(selected, start=1):
        concept_name = concept["concept_name"]
        concept_code = concept.get("concept_code")
        if progress_callback:
            progress_callback(f"CONCEPT_FETCH_START {index}/{total_selected} name={concept_name} code={concept_code or ''}")
        cons_records = []
        last_error: Exception | None = None
        for symbol_arg in [concept_name, concept_code]:
            if not symbol_arg:
                continue
            try:
                cons_df = ak_module.stock_board_concept_cons_em(symbol=symbol_arg)
                cons_records = _to_records(cons_df)
                if cons_records:
                    break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue
        if not cons_records and last_error is not None:
            failed_count += 1
            if progress_callback:
                progress_callback(f"CONCEPT_FETCH_ERROR {index}/{total_selected} name={concept_name} error={type(last_error).__name__}: {last_error}")
            continue
        should_report = bool(progress_callback) and (index == 1 or index == total_selected or index % progress_every == 0)
        if should_report or progress_callback:
            progress_callback(f"CONCEPT_FETCH_DONE {index}/{total_selected} name={concept_name} rows={len(cons_records)} accumulated_rows={len(rows)} failed={failed_count}")
        for item in cons_records:
            stock_code = normalize_symbol(first_value(item, ["代码", "证券代码", "stock_code", "symbol", "ticker"]))
            stock_name = normalize_text(first_value(item, ["名称", "证券简称", "stock_name", "name"]))
            if not stock_code:
                continue
            rows.append(
                {
                    "concept_code": concept_code,
                    "concept_name": concept_name,
                    "stock_code": stock_code,
                    "stock_name": stock_name,
                }
            )
    if progress_callback:
        progress_callback(f"CONCEPT_FETCH_ALL_DONE selected={len(selected)} rows={len(rows)} failed={failed_count}")
    return rows


def _to_records(frame_like: Any) -> list[dict[str, Any]]:
    if frame_like is None:
        return []
    if hasattr(frame_like, "to_dict"):
        records = frame_like.to_dict("records")
        return [dict(row) for row in records]
    return [dict(row) for row in frame_like]


def write_taxonomy_import_artifacts(
    *,
    output_dir: str | Path,
    report_date: str,
    result: TaxonomyImportResult,
) -> dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    prefix = f"m4_taxonomy_import_p0_{report_date}"
    json_path = out / f"{prefix}.json"
    stats_csv_path = out / f"{prefix}_stats.csv"
    errors_csv_path = out / f"{prefix}_errors.csv"
    md_path = out / f"{prefix}.md"

    payload = result.to_dict()
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    stats_rows = [item.to_dict() for item in result.stats]
    _write_csv(stats_csv_path, stats_rows)

    error_rows: list[dict[str, Any]] = []
    for item in result.stats:
        for err in item.errors:
            error_rows.append({"import_name": item.import_name, "source": item.source, **err})
    _write_csv(errors_csv_path, error_rows)

    lines = [
        "# M4 S1.1 Taxonomy Import Report",
        "",
        f"- report_date: {report_date}",
        f"- status: {result.status}",
        f"- run_id: {result.run_id}",
        "- scope: SW_INDUSTRY taxonomy + Eastmoney CONCEPT_EM mapping only.",
        "- guardrail: this import does not generate strategy_signal, backtest, paper orders, or risk decisions.",
        "",
        "## Import Stats",
        "",
        _format_markdown_table(
            stats_rows,
            ["import_name", "source", "tag_type", "input_rows", "tag_upsert_rows", "instrument_tag_upsert_rows", "missing_instruments", "skipped_rows", "error_rows"],
        ),
        "",
        "## Natural Language Interpretation",
        "",
        _build_import_interpretation(result),
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    paths = {
        "json": str(json_path),
        "stats_csv": str(stats_csv_path),
        "errors_csv": str(errors_csv_path),
        "markdown": str(md_path),
    }
    result.artifact_paths = paths
    json_path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return paths


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                fields.append(key)
    if not fields:
        fields = ["empty"]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fields})


def _format_markdown_table(rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> str:
    if not rows:
        return "_No rows._"
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = ["| " + " | ".join(str(row.get(col, "")) for col in columns) + " |" for row in rows]
    return "\n".join([header, sep, *body])


def _build_import_interpretation(result: TaxonomyImportResult) -> str:
    blockers = []
    for stat in result.stats:
        if stat.input_rows == 0:
            blockers.append(f"{stat.import_name} 没有输入行")
        if stat.instrument_tag_upsert_rows == 0:
            blockers.append(f"{stat.import_name} 没有成功写入 instrument_tag")
    if blockers:
        return "本次 taxonomy 导入未完全满足 S1.1 目标：" + "；".join(blockers) + "。请补齐输入或检查 provider 后重跑。"
    return "本次 taxonomy 导入已写入标签和股票归属映射。下一步应重跑 M4 readiness audit，确认 industry_classification_assignment 和 concept_em_assignment 覆盖率。"
