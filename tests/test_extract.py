"""Raw sheet extracts. Excel opens only when the bytes or the extract code change."""

import json
from pathlib import Path

import pandas as pd
import requests
from openpyxl import Workbook

from pa_edu.catalog import CatalogEntry
from pa_edu.codes import read_sheet
from pa_edu.extract import ensure_extract, read_workbook, use_extract
from pa_edu.storage import load_index, store_bytes


def _book(path: Path) -> None:
    book = Workbook()
    sheet = book.active
    sheet.title = "Exp"
    sheet.append(["AUN", "School Number", "Amount"])
    sheet.append([101260303.0, 9999.0, 0])
    sheet.append([None, 0, None])
    sheet.append([None, None, None])
    path.parent.mkdir(parents=True, exist_ok=True)
    book.save(path)


def _record(tmp_path: Path, book: Path) -> tuple[Path, dict, dict]:
    data = tmp_path / "data"
    index = load_index(data)
    entry = CatalogEntry(
        id="codes",
        source_id="test",
        source_url=book.as_uri(),
        page_url=book.as_uri(),
        parser="gfb",
        status="stable",
        school_year=2024,
    )
    record = store_bytes(entry, book.read_bytes(), data, index, book.name)
    return data, index, record


def _frame(record: dict) -> pd.DataFrame:
    meta = json.loads((Path(record["extract_path"]) / "meta.json").read_text())
    sheet = meta["sheets"][0]
    return pd.read_parquet(Path(record["extract_path"]) / sheet["file"])


def test_codes_round_trip_as_text_and_blanks_stay_null(tmp_path: Path, monkeypatch) -> None:
    book = tmp_path / "codes.xlsx"
    _book(book)
    data, index, record = _record(tmp_path, book)
    calls = {"n": 0}
    original = read_workbook

    def counting(path: Path):
        calls["n"] += 1
        return original(path)

    monkeypatch.setattr("pa_edu.extract.read_workbook", counting)
    record = ensure_extract(data, index, record)
    frame = _frame(record)
    assert calls["n"] == 1
    assert frame["AUN"].iloc[0] == "101260303"
    assert pd.isna(frame["AUN"].iloc[1])
    assert frame["School Number"].tolist() == ["9999", "0"]
    assert frame["Amount"].iloc[0] == "0"
    assert pd.isna(frame["Amount"].iloc[1])
    assert frame["source_row"].tolist() == [2, 3]
    assert set(frame["document_id"]) == {record["document_id"]}
    assert set(frame["sheet"]) == {"Exp"}
    saved = load_index(data)["documents"][record["document_id"]]
    assert saved["extract_id"] == record["extract_id"]
    assert saved["extract_path"] == record["extract_path"]
    assert saved["source_url"] == book.as_uri()
    assert saved["sha256"] == record["sha256"]
    assert saved["school_year"] == 2024

    ensure_extract(data, index, record)
    assert calls["n"] == 1


def test_a_changed_extract_code_rebuilds(tmp_path: Path, monkeypatch) -> None:
    book = tmp_path / "codes.xlsx"
    _book(book)
    data, index, record = _record(tmp_path, book)
    record = ensure_extract(data, index, record)
    meta_path = Path(record["extract_path"]) / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta["extract_code"] = "stale"
    meta_path.write_text(json.dumps(meta))
    calls = {"n": 0}
    original = read_workbook

    def counting(path: Path):
        calls["n"] += 1
        return original(path)

    monkeypatch.setattr("pa_edu.extract.read_workbook", counting)
    ensure_extract(data, load_index(data), record)
    assert calls["n"] == 1
    assert json.loads(meta_path.read_text())["extract_code"] != "stale"


def test_a_sheet_index_reads_the_extracted_sheet(tmp_path: Path) -> None:
    book = tmp_path / "codes.xlsx"
    _book(book)
    data, index, record = _record(tmp_path, book)
    record = ensure_extract(data, index, record)
    with use_extract(book, record["extract_path"]):
        frame = read_sheet(book, 0)
    assert list(frame.columns) == ["AUN", "School Number", "Amount"]
    assert frame["AUN"].iloc[0] == "101260303"


def test_a_missing_discovered_link_is_skipped(tmp_path: Path, monkeypatch, capsys) -> None:
    import pa_edu.extract as extract

    page = "https://example.test/reports"
    gone = "https://www.pa.gov/portals/66/gone.xlsx"
    kept = "https://www.pa.gov/portals/66/kept.xlsx"
    monkeypatch.setattr(extract, "PAGES", [page])
    monkeypatch.setattr(extract, "fetch_hrefs", lambda url: [gone, kept])
    seen = []

    def materialize(entry, data_dir, index):
        seen.append(entry.source_url)
        if entry.source_url == gone:
            response = requests.Response()
            response.status_code = 404
            response.url = gone
            raise requests.HTTPError("404", response=response)
        return {"path": str(data_dir / "kept.xlsx")}

    monkeypatch.setattr(extract, "materialize", materialize)
    monkeypatch.setattr(extract, "ensure_extract", lambda *args: None)
    extract.ingest_discovered(tmp_path / "data", {"current": {}, "documents": {}})
    assert seen == [gone, kept]
    output = capsys.readouterr().out
    assert "missing " in output
    assert "gone.xlsx" in output
    assert "kept.xlsx" in output
