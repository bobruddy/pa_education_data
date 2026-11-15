"""Persist one table per sheet for each cached workbook.

The extract is the published columns, with codes kept as text. ``refine`` and
``personnel`` read it. A second run does not open Excel unless the file hash
or this module changes. ``check`` keeps opening the workbook.
"""

from __future__ import annotations

import contextvars
import hashlib
import json
import math
import os
import shutil
import urllib.parse
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests

from pa_edu.catalog import CatalogEntry, load_catalog
from pa_edu.common import DATA_DIR, ROOT, absolute_url, fetch_hrefs
from pa_edu.discover import PAGES
from pa_edu.storage import load_index, materialize, save_index

META_COLUMNS = ("document_id", "sheet", "source_row")
HEADER_SCAN_ROWS = 40
_ACTIVE: contextvars.ContextVar[dict[str, str] | None] = contextvars.ContextVar(
    "pde_extract",
    default=None,
)


def extract_code() -> str:
    """Identity of the header, typing, and sheet rules in this module."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def is_workbook(path: Path) -> bool:
    return path.suffix.lower() in {".xls", ".xlsx", ".xlsm"}


def ensure_extract(data_dir: Path, index: dict, record: dict) -> dict:
    """Write this workbook's sheets, or keep them when the hash and code match."""
    code = extract_code()
    directory = data_dir / "extract" / record["document_id"]
    updated = {
        **record,
        "kind": "workbook",
        "extract_id": f"{record['document_id']}-{code[:12]}",
        "extract_path": str(directory),
        "extract_code": code,
    }
    if _current(directory, updated):
        _remember(data_dir, index, updated)
        print(f"kept extract {record['catalog_id']}")
        return updated
    print(f"extract {record['catalog_id']}")
    _write(directory, updated)
    _remember(data_dir, index, updated)
    return updated


def ingest_discovered(data_dir: Path, index: dict) -> None:
    """Download watched-page workbooks that are not already in the inventory.

    An unrecognized layout is extracted and left unused. Refinement still
    fails until a catalog rule exists.
    """
    known = _known_urls(index)
    for page in PAGES:
        for href in fetch_hrefs(page):
            url = absolute_url(href).split("?", 1)[0]
            if not url.lower().endswith((".xls", ".xlsx", ".xlsm")):
                continue
            if _url_key(url) in known:
                continue
            entry = CatalogEntry(
                id=f"discovered-{hashlib.sha256(url.encode()).hexdigest()[:12]}",
                source_id="discovered",
                source_url=url,
                page_url=page,
                parser="",
                status="review",
            )
            try:
                record = materialize(entry, data_dir, index)
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status != 404:
                    raise
                print(f"missing {entry.id}: {Path(url).name}")
                continue
            print(f"review {entry.id}: {Path(record['path']).name}")
            ensure_extract(data_dir, index, record)
            known.add(_url_key(url))


@contextmanager
def use_extract(workbook: str | Path, extract_path: str | None):
    """Point sheet reads for this workbook at its extract. Unset, they open Excel."""
    if not extract_path:
        yield
        return
    current = dict(_ACTIVE.get() or {})
    current[str(Path(workbook).resolve())] = extract_path
    token = _ACTIVE.set(current)
    try:
        yield
    finally:
        _ACTIVE.reset(token)


def published_names(path: Path) -> list[str] | None:
    root = _lookup(path)
    if root is None:
        return None
    return [sheet["name"] for sheet in _meta(root)["sheets"]]


def published_sheet(path: Path, sheet: str) -> pd.DataFrame | None:
    """Published columns for one sheet, or None when this path is not activated."""
    root = _lookup(path)
    if root is None:
        return None
    meta = _meta(root)
    match = next((item for item in meta["sheets"] if item["name"] == sheet), None)
    if match is None:
        names = [item["name"] for item in meta["sheets"]]
        raise ValueError(f"{path.name} has no extracted sheet {sheet!r} in {names}")
    columns = match["columns"]
    if not columns:
        return pd.DataFrame()
    frame = pd.read_parquet(root / match["file"])
    return frame.drop(columns=list(META_COLUMNS))


def main() -> None:
    data_dir = DATA_DIR
    index = load_index(data_dir)
    for entry in load_catalog(ROOT / "sources" / "catalog.toml"):
        record = materialize(entry, data_dir, index)
        if is_workbook(Path(record["path"])):
            ensure_extract(data_dir, index, record)
    ingest_discovered(data_dir, index)


def _remember(data_dir: Path, index: dict, record: dict) -> None:
    index["documents"][record["document_id"]] = record
    save_index(data_dir, index)


def _current(directory: Path, record: dict) -> bool:
    meta_path = directory / "meta.json"
    if not meta_path.is_file():
        return False
    meta = json.loads(meta_path.read_text())
    if meta.get("extract_code") != record["extract_code"]:
        return False
    if meta.get("sha256") != record["sha256"] or meta.get("document_id") != record["document_id"]:
        return False
    sheets = meta.get("sheets")
    if not isinstance(sheets, list):
        return False
    for sheet in sheets:
        file_name = sheet.get("file")
        if not isinstance(file_name, str) or not (directory / file_name).is_file():
            return False
    return True


def _write(directory: Path, record: dict) -> None:
    sheets = read_workbook(Path(record["path"]))
    temporary = directory.parent / f".{directory.name}.{os.getpid()}.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    try:
        temporary.mkdir(parents=True)
        described = []
        for index, (name, rows) in enumerate(sheets):
            frame, columns = _sheet_frame(rows, record["document_id"], name)
            file_name = f"sheet-{index:03d}.parquet"
            frame.to_parquet(temporary / file_name, index=False)
            described.append({"name": name, "file": file_name, "columns": columns, "rows": len(frame)})
        meta = {
            "document_id": record["document_id"],
            "sha256": record["sha256"],
            "extract_code": record["extract_code"],
            "extract_id": record["extract_id"],
            "sheets": described,
        }
        (temporary / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
        if directory.exists():
            shutil.rmtree(directory)
        directory.parent.mkdir(parents=True, exist_ok=True)
        temporary.rename(directory)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
        raise


def read_workbook(path: Path) -> list[tuple[str, list[tuple]]]:
    """Open Excel. This is the only workbook read on the extract path."""
    if path.suffix.lower() == ".xls":
        return _read_xls(path)
    return _read_xlsx(path)


def _read_xlsx(path: Path) -> list[tuple[str, list[tuple]]]:
    import openpyxl

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheets = []
        for worksheet in workbook.worksheets:
            rows = [tuple(row) for row in worksheet.iter_rows(values_only=True)]
            sheets.append((worksheet.title, rows))
        return sheets
    finally:
        workbook.close()


def _read_xls(path: Path) -> list[tuple[str, list[tuple]]]:
    import xlrd

    book = xlrd.open_workbook(path)
    sheets = []
    for worksheet in book.sheets():
        rows = []
        for index in range(worksheet.nrows):
            values = []
            for cell in worksheet.row(index):
                if cell.ctype == xlrd.XL_CELL_DATE:
                    values.append(xlrd.xldate_as_datetime(cell.value, book.datemode))
                elif cell.ctype in {xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK}:
                    values.append(None)
                elif cell.ctype == xlrd.XL_CELL_ERROR:
                    values.append(None)
                else:
                    values.append(cell.value)
            rows.append(tuple(values))
        sheets.append((worksheet.name, rows))
    return sheets


def _sheet_frame(rows: list[tuple], document_id: str, sheet: str) -> tuple[pd.DataFrame, list[str]]:
    width = _width(rows)
    header_index = _header_row(rows, width)
    columns = _headers(rows[header_index] if rows else (), width) if width else []
    collision = [name for name in columns if name in META_COLUMNS]
    if collision:
        raise ValueError(f"sheet {sheet} uses reserved column names {collision}")
    records = []
    for index in range(header_index + 1, len(rows)):
        row = rows[index]
        values = [_cell_text(row[column]) if column < len(row) else None for column in range(width)]
        if all(value is None for value in values):
            continue
        record = dict(zip(columns, values, strict=True))
        record["document_id"] = document_id
        record["sheet"] = sheet
        record["source_row"] = index + 1
        records.append(record)
    frame = pd.DataFrame(records, columns=[*columns, *META_COLUMNS])
    for column in (*columns, "document_id", "sheet"):
        frame[column] = frame[column].astype("string")
    if frame.empty:
        frame["source_row"] = pd.Series(dtype="int64")
    else:
        frame["source_row"] = frame["source_row"].astype("int64")
    return frame, columns


def _width(rows: list[tuple]) -> int:
    last = 0
    for row in rows:
        for index, value in enumerate(row):
            if _cell_text(value) is not None:
                last = max(last, index + 1)
    return last


def _header_row(rows: list[tuple], width: int) -> int:
    for index, row in enumerate(rows[:HEADER_SCAN_ROWS]):
        for column in range(width):
            if column >= len(row):
                break
            text = _cell_text(row[column])
            if text and text.casefold() in {"aun", "submitting aun"}:
                return index
    return 0


def _headers(row: tuple, width: int) -> list[str]:
    seen: dict[str, int] = {}
    headers = []
    for column in range(width):
        text = _cell_text(row[column]) if column < len(row) else None
        name = text or f"Unnamed: {column}"
        count = seen.get(name, 0)
        seen[name] = count + 1
        if count:
            name = f"{name}.{count}"
        headers.append(name)
    return headers


def _cell_text(value: object) -> str | None:
    """Blank is null. An integer-valued Excel float is its digits, including 0."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, datetime):
        if value.hour == value.minute == value.second == value.microsecond == 0:
            return value.date().isoformat()
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        if value.is_integer():
            return str(int(value))
        return format(value, ".17g")
    text = str(value).replace("\r\n", "\n").replace("\r", "\n").strip()
    if text == "":
        return None
    return text


def _lookup(path: Path) -> Path | None:
    active = _ACTIVE.get()
    if not active:
        return None
    found = active.get(str(Path(path).resolve()))
    if found is None:
        return None
    return Path(found)


def _meta(root: Path) -> dict:
    return json.loads((root / "meta.json").read_text())


def _known_urls(index: dict) -> set[str]:
    return {_url_key(record.get("source_url", "")) for record in index["documents"].values()}


def _url_key(url: str) -> str:
    return urllib.parse.unquote(url.split("?", 1)[0]).rstrip("/")


if __name__ == "__main__":
    main()
