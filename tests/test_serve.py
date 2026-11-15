"""The data service serves refined Parquet and a status page, not workbooks."""

import json
import os
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd

from pa_edu.publish import resolve_refined
from pa_edu.serve import Handler


def _server(directory: Path) -> tuple[ThreadingHTTPServer, int]:
    Handler.root = directory
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1]


def test_range_requests_and_raw_files_stay_unserved(tmp_path: Path, monkeypatch) -> None:
    refined = tmp_path / "refined"
    refined.mkdir()
    payload = b"abcdefghijklmnopqrstuvwxyz"
    (refined / "lea.parquet").write_bytes(payload)
    (refined / ".lea.parquet.tmp").write_bytes(b"partial")
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "index.json").write_text("WORKBOOK-SENTINEL")
    server, port = _server(refined)
    try:
        listing = json.loads(urlopen(f"http://127.0.0.1:{port}/refined/").read())
        assert listing["tables"] == ["lea.parquet"]
        whole = urlopen(f"http://127.0.0.1:{port}/refined/lea.parquet")
        assert whole.status == 200
        assert whole.headers["Accept-Ranges"] == "bytes"
        assert whole.read() == payload
        partial = urlopen(Request(
            f"http://127.0.0.1:{port}/refined/lea.parquet",
            headers={"Range": "bytes=0-3"},
        ))
        assert partial.status == 206
        assert partial.headers["Content-Range"] == f"bytes 0-3/{len(payload)}"
        assert partial.read() == payload[:4]
        for path in (
            "/raw/index.json",
            "/extract/sheet.parquet",
            "/refined/../raw/index.json",
            "/refined/.lea.parquet.tmp",
            "/status/runs.json",
        ):
            try:
                urlopen(f"http://127.0.0.1:{port}{path}")
            except Exception as error:
                assert getattr(error, "code", None) == 404
            else:
                raise AssertionError(f"{path} was served")
        frame = pd.DataFrame({"aun": ["101260303"], "school_year": [2024]})
        frame.to_parquet(refined / "lea.parquet", index=False)
        monkeypatch.setenv("PDE_REFINED_URL", f"http://127.0.0.1:{port}/refined")
        staged = resolve_refined()
        try:
            found = pd.read_parquet(staged / "lea.parquet")
            assert found["aun"].tolist() == ["101260303"]
            assert not (staged / "index.json").exists()
        finally:
            for child in staged.iterdir():
                child.unlink()
            staged.rmdir()
    finally:
        server.shutdown()
        monkeypatch.delenv("PDE_REFINED_URL", raising=False)


def test_site_image_does_not_copy_the_data_directory() -> None:
    dockerfile = Path("Dockerfile").read_text()
    data_image = Path("Dockerfile.data").read_text()
    assert "pde_site" in dockerfile
    assert "data/refined" not in dockerfile
    assert "data/raw" not in dockerfile
    assert "COPY pa_edu" in data_image
    assert "data/refined" not in data_image
    assert "ARG PDE_GIT_SHA" in data_image
    assert 'PDE_GIT_SHA="$tag"' in Path("Jenkinsfile").read_text()
    assert 'PDE_GIT_SHA="$sha"' in Path("scripts/docker09-data.sh").read_text()
    assert os.environ.get("PDE_REFINED_URL", "") == ""
