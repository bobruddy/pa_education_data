"""Serve refined Parquet over HTTP. Workbooks and raw extracts stay off this port.

DuckDB ``httpfs`` reads ``/refined/<table>.parquet``. Range requests are
supported so a query can fetch the row groups it needs. Files are replaced
by rename, and names that are not a finished table are not served.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from pa_edu.common import DATA_DIR

TABLE_NAME = re.compile(r"[A-Za-z0-9_]+\.parquet")
PORT = int(os.environ.get("PDE_DATA_PORT", "8091"))


class Handler(BaseHTTPRequestHandler):
    root: Path = DATA_DIR / "refined"

    def do_GET(self) -> None:
        self._handle(send_body=True)

    def do_HEAD(self) -> None:
        self._handle(send_body=False)

    def log_message(self, fmt: str, *args) -> None:
        print(f"{self.address_string()} {fmt % args}")

    def _handle(self, send_body: bool) -> None:
        path = urllib.parse.unquote(urllib.parse.urlparse(self.path).path)
        if path in {"/refined", "/refined/"}:
            self._list(send_body)
            return
        name = path.removeprefix("/refined/")
        if name == path or not TABLE_NAME.fullmatch(name):
            self.send_error(404)
            return
        file = (self.root / name).resolve()
        if file.parent != self.root.resolve() or not file.is_file():
            self.send_error(404)
            return
        self._send_file(file, send_body)

    def _list(self, send_body: bool) -> None:
        if self.root.is_dir():
            names = sorted(path.name for path in self.root.glob("*.parquet") if TABLE_NAME.fullmatch(path.name))
        else:
            names = []
        body = (json.dumps({"tables": names}) + "\n").encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def _send_file(self, file: Path, send_body: bool) -> None:
        size = file.stat().st_size
        start, end, status = _range(self.headers.get("Range"), size)
        if status == 416:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return
        length = 0 if start is None else end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if not send_body or start is None:
            return
        with file.open("rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining:
                chunk = handle.read(min(remaining, 1024 * 1024))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)


def _range(header: str | None, size: int) -> tuple[int | None, int, int]:
    """Return start, end, and status. start is None when the body is empty."""
    if size == 0:
        if header:
            return None, 0, 416
        return None, 0, 200
    if not header:
        return 0, size - 1, 200
    if not header.startswith("bytes=") or "," in header:
        return None, 0, 416
    left, _, right = header.removeprefix("bytes=").partition("-")
    try:
        if left == "":
            if not right:
                return None, 0, 416
            length = int(right)
            if length <= 0:
                return None, 0, 416
            start = max(size - length, 0)
            end = size - 1
        else:
            start = int(left)
            end = int(right) if right else size - 1
    except ValueError:
        return None, 0, 416
    if start < 0 or start >= size or end < start:
        return None, 0, 416
    return start, min(end, size - 1), 206


def serve(host: str = "0.0.0.0", port: int = PORT, directory: Path | None = None) -> ThreadingHTTPServer:
    Handler.root = directory or (DATA_DIR / "refined")
    server = ThreadingHTTPServer((host, port), Handler)
    server.serve_forever()
    return server


def main() -> None:
    directory = DATA_DIR / "refined"
    print(f"serving {directory} on {PORT}")
    serve(port=PORT, directory=directory)


if __name__ == "__main__":
    main()
