"""The data service status page reports runs and inventory, not file paths."""

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd
import pytest

from pa_edu import check, personnel, refine
from pa_edu.catalog import load_catalog
from pa_edu.common import ROOT
from pa_edu.serve import Handler
from pa_edu.status import git_sha, record_run, render_status, status_report


def _server(directory: Path) -> tuple[ThreadingHTTPServer, int]:
    Handler.root = directory
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1]


def test_runs_merge_and_drop_the_data_path(tmp_path: Path) -> None:
    record_run("refine", ok=True, documents=4, data_dir=tmp_path)
    record_run(
        "check",
        ok=False,
        errors=[f"missing {tmp_path}/raw/file.xlsx", "<script>alert(1)</script>"],
        data_dir=tmp_path,
    )
    stored = json.loads((tmp_path / "status" / "runs.json").read_text())
    assert stored["refine"]["documents"] == 4
    assert stored["check"]["ok"] is False
    assert stored["check"]["error_count"] == 2
    text = json.dumps(stored)
    assert str(tmp_path) not in text
    assert "<data>" in text

    report = status_report(tmp_path)
    assert report["ok"] is False
    assert report["runs_readable"] is True
    page = render_status(report)
    assert str(tmp_path) not in page
    assert "<script>" not in page
    assert "&lt;script&gt;" in page
    assert "Checks failed · 2 errors" in page


def test_check_and_refine_failures_are_recorded(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("pa_edu.status.DATA_DIR", tmp_path)
    monkeypatch.setattr("pa_edu.check.run_checks", lambda data_dir=None: ["lea has a null aun"])
    with pytest.raises(SystemExit) as caught:
        check.main()
    assert caught.value.code == 1
    failed = json.loads((tmp_path / "status" / "runs.json").read_text())
    assert failed["check"]["errors"] == ["lea has a null aun"]

    monkeypatch.setattr("pa_edu.check.run_checks", lambda data_dir=None: [])
    check.main()
    passed = json.loads((tmp_path / "status" / "runs.json").read_text())
    assert passed["check"]["ok"] is True
    assert passed["check"]["error_count"] == 0

    def boom() -> None:
        raise RuntimeError(f"cannot read {tmp_path}/raw/book.xlsx")

    monkeypatch.setattr("pa_edu.refine.run", boom)
    with pytest.raises(RuntimeError):
        refine.main()
    text = (tmp_path / "status" / "runs.json").read_text()
    assert str(tmp_path) not in text
    recorded = json.loads(text)
    assert recorded["check"]["ok"] is True
    assert recorded["refine"]["ok"] is False
    assert "<data>" in recorded["refine"]["error"]

    def no_page(data_dir=None) -> None:
        raise RuntimeError(f"no page at {tmp_path}")

    monkeypatch.setattr("pa_edu.personnel.load_personnel", no_page)
    with pytest.raises(RuntimeError):
        personnel.main()
    personnel_text = (tmp_path / "status" / "runs.json").read_text()
    assert str(tmp_path) not in personnel_text
    assert json.loads(personnel_text)["personnel"]["ok"] is False


def test_inventory_uses_parquet_metadata_and_skips_junk(tmp_path: Path) -> None:
    refined = tmp_path / "refined"
    refined.mkdir()
    pd.DataFrame({"aun": ["101260303", "101000000"]}).to_parquet(refined / "lea.parquet", index=False)
    pd.DataFrame({
        "catalog_id": ["gfb-2024", "gfb-2020", "act1"],
        "source_id": ["gfb", "gfb", "act1"],
        "retrieved_at": [
            "2025-06-01T00:00:00+00:00",
            "2020-01-01T00:00:00+00:00",
            "2024-01-01T00:00:00+00:00",
        ],
        "school_year": [2024, 2020, None],
    }).to_parquet(refined / "document.parquet", index=False)
    (refined / ".lea.parquet.tmp").write_bytes(b"partial")
    (refined / "broken.parquet").write_bytes(b"not parquet")
    (refined / "_parts").mkdir()
    (refined / "_parts" / "shard.parquet").write_bytes(b"hidden")

    report = status_report(tmp_path)
    tables = {table["file"]: table for table in report["refined"]["tables"]}
    assert tables["lea.parquet"]["rows"] == 2
    assert tables["lea.parquet"]["bytes"] > 0
    assert "broken.parquet" in tables
    assert tables["broken.parquet"]["rows"] is None
    assert ".lea.parquet.tmp" not in tables
    assert "shard.parquet" not in tables
    assert report["refined"]["school_years"] == [2020, 2024]
    newest = report["refined"]["newest_document"]
    assert newest["catalog_id"] == "gfb-2024"
    assert newest["school_year"] == 2024
    page = render_status(report)
    assert "No refined tables." not in page
    assert "gfb-2024" in page
    assert "2020, 2024" in page
    assert "—" in page


def test_a_later_refine_failure_fails_the_page(tmp_path: Path) -> None:
    record_run("check", ok=True, errors=[], data_dir=tmp_path)
    record_run("refine", ok=False, error="duckdb locked", data_dir=tmp_path)
    report = status_report(tmp_path)
    assert report["ok"] is False
    assert report["check"]["ok"] is True
    page = render_status(report)
    assert "refine failed" in page
    assert "Checks passed" not in page


def test_unreadable_run_record_and_catalog_counts(tmp_path: Path) -> None:
    status = tmp_path / "status"
    status.mkdir()
    (status / "runs.json").write_text("{")
    report = status_report(tmp_path)
    assert report["ok"] is False
    assert report["runs_readable"] is False
    assert report["check"] is None
    page = render_status(report)
    assert "could not be read" in page

    entries = load_catalog(ROOT / "sources" / "catalog.toml")
    assert report["catalog"]["stable"] == sum(entry.status == "stable" for entry in entries)
    assert report["catalog"]["review"] == sum(entry.status == "review" for entry in entries)
    assert str(tmp_path) not in json.dumps(report)


def test_git_sha_must_look_like_a_commit(monkeypatch) -> None:
    monkeypatch.delenv("PDE_GIT_SHA", raising=False)
    assert git_sha() is None
    monkeypatch.setenv("PDE_GIT_SHA", "latest")
    assert git_sha() is None
    monkeypatch.setenv("PDE_GIT_SHA", "A" * 40)
    assert git_sha() == "a" * 40


def test_status_page_hides_raw_bytes(tmp_path: Path, monkeypatch) -> None:
    refined = tmp_path / "refined"
    refined.mkdir()
    pd.DataFrame({"aun": ["101260303"]}).to_parquet(refined / "lea.parquet", index=False)
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "index.json").write_text("WORKBOOK-SENTINEL")
    record_run("check", ok=True, errors=[], data_dir=tmp_path)
    monkeypatch.setenv("PDE_GIT_SHA", "abc1234")
    server, port = _server(refined)
    try:
        page = urlopen(f"http://127.0.0.1:{port}/")
        body = page.read().decode()
        assert page.status == 200
        assert "text/html" in page.headers["Content-Type"]
        assert page.headers["Cache-Control"] == "no-store"
        assert "Checks passed" in body
        assert "abc1234" in body
        assert "WORKBOOK-SENTINEL" not in body
        assert str(tmp_path) not in body
        same = urlopen(f"http://127.0.0.1:{port}/status").read().decode()
        assert "Checks passed" in same
        payload = json.loads(urlopen(f"http://127.0.0.1:{port}/status.json").read())
        assert payload["ok"] is True
        assert payload["git_sha"] == "abc1234"
        assert payload["refined"]["tables"][0]["file"] == "lea.parquet"
        assert payload["refined"]["tables"][0]["rows"] == 1
        assert "WORKBOOK-SENTINEL" not in json.dumps(payload)
        assert str(tmp_path) not in json.dumps(payload)
        head = urlopen(Request(f"http://127.0.0.1:{port}/status", method="HEAD"))
        assert head.status == 200
        assert head.read() == b""
        assert int(head.headers["Content-Length"]) > 0
    finally:
        server.shutdown()
        monkeypatch.delenv("PDE_GIT_SHA", raising=False)


def test_long_error_lists_are_truncated(tmp_path: Path) -> None:
    errors = [f"error {index} " + ("x" * 600) for index in range(45)]
    record_run("check", ok=False, errors=errors, data_dir=tmp_path)
    stored = json.loads((tmp_path / "status" / "runs.json").read_text())["check"]
    assert stored["error_count"] == 45
    assert len(stored["errors"]) == 40
    assert stored["errors_omitted"] == 5
    assert len(stored["errors"][0]) == 500
    assert stored["errors"][0].endswith("…")
