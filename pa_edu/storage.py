"""Download PDE files once and keep every hash that has been fetched."""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import requests

from pa_edu.catalog import CatalogEntry
from pa_edu.common import HEADERS

INDEX_NAME = "index.json"


def index_path(data_dir: Path) -> Path:
    return data_dir / "raw" / INDEX_NAME


def load_index(data_dir: Path) -> dict:
    path = index_path(data_dir)
    if not path.exists():
        return {"current": {}, "documents": {}}
    return json.loads(path.read_text())


def save_index(data_dir: Path, index: dict) -> None:
    path = index_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")


def materialize(entry: CatalogEntry, data_dir: Path, index: dict) -> dict:
    current = index["current"].get(entry.id)
    if current and _file_ok(index["documents"][current]):
        return index["documents"][current]
    content, filename = fetch(entry)
    return store_bytes(entry, content, data_dir, index, filename)


def store_bytes(
    entry: CatalogEntry,
    content: bytes,
    data_dir: Path,
    index: dict,
    filename: str | None = None,
    retrieved_at: str | None = None,
) -> dict:
    digest = hashlib.sha256(content).hexdigest()
    document_id = f"{entry.id}-{digest[:12]}"
    name = _filename(entry, filename)
    destination = data_dir / "raw" / entry.source_id / digest / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        destination.write_bytes(content)
    record = {
        "document_id": document_id,
        "catalog_id": entry.id,
        "source_id": entry.source_id,
        "source_url": entry.source_url,
        "page_url": entry.page_url,
        "sha256": digest,
        "retrieved_at": retrieved_at or _now(),
        "school_year": entry.school_year,
        "parser": entry.parser,
        "status": entry.status,
        "path": str(destination),
        "filename": name,
    }
    previous = index["documents"].get(document_id)
    if previous:
        record["retrieved_at"] = previous["retrieved_at"]
    index["documents"][document_id] = record
    index["current"][entry.id] = document_id
    save_index(data_dir, index)
    return record


def fetch(entry: CatalogEntry) -> tuple[bytes, str]:
    if entry.fetch == "edna":
        return _fetch_edna(entry.source_url), entry.filename or "ExtractEntitiesAdmin.xlsx"
    if entry.source_url.startswith("file:"):
        path = Path(file_url_path(entry.source_url))
        return path.read_bytes(), entry.filename or path.name
    response = requests.get(entry.source_url, headers=HEADERS, timeout=600)
    response.raise_for_status()
    name = entry.filename or _name_from_url(entry.source_url)
    return response.content, name


def file_url_path(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return urllib.parse.unquote(parsed.path)


def _fetch_edna(url: str) -> bytes:
    session = requests.Session()
    session.headers.update(HEADERS)
    page = session.get(url, timeout=60)
    page.raise_for_status()
    html = page.text

    def hidden(name: str) -> str:
        match = re.search(rf'name="{name}"[^>]*value="([^"]*)"', html)
        if match is None:
            raise RuntimeError(f"EdNA form has no {name}; leave the extract at review")
        return match.group(1)

    data = {
        "__EVENTTARGET": "",
        "__EVENTARGUMENT": "",
        "__VIEWSTATE": hidden("__VIEWSTATE"),
        "__VIEWSTATEGENERATOR": hidden("__VIEWSTATEGENERATOR"),
        "__EVENTVALIDATION": hidden("__EVENTVALIDATION"),
        "ctl00$MainContent$chkStatusList$0": "1",
        "ctl00$MainContent$chkStatusList$1": "2",
        "ctl00$MainContent$chkPublicEntityCategoryList$0": "3",
        "ctl00$MainContent$chkPublicEntityCategoryList$1": "4",
        "ctl00$MainContent$chkPublicEntityCategoryList$2": "2",
        "ctl00$MainContent$chkPublicEntityCategoryList$3": "1",
        "ctl00$MainContent$chkPublicEntityCategoryList$4": "6",
        "ctl00$MainContent$chkPublicEntityCategoryList$5": "7",
        "ctl00$MainContent$rbAdminTypeList": "0",
        "ctl00$MainContent$cmdExport": "Export",
    }
    response = session.post(url, data=data, timeout=180)
    response.raise_for_status()
    kind = response.headers.get("content-type", "")
    if "spreadsheetml" not in kind and "excel" not in kind:
        raise RuntimeError(f"EdNA export returned {kind or 'an empty type'}")
    return response.content


def _filename(entry: CatalogEntry, filename: str | None) -> str:
    name = filename or entry.filename or _name_from_url(entry.source_url)
    return name.replace("/", "_").strip() or "download"


def _name_from_url(url: str) -> str:
    path = urllib.parse.unquote(urllib.parse.urlparse(url).path)
    return path.rstrip("/").rsplit("/", 1)[-1] or "download"


def _file_ok(record: dict) -> bool:
    path = Path(record["path"])
    return path.exists() and path.stat().st_size > 0


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
