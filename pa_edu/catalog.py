"""Checked-in list of PDE documents the rebuild is allowed to fetch."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CatalogEntry:
    id: str
    source_id: str
    source_url: str
    page_url: str
    parser: str
    status: str
    school_year: int | None = None
    span: int | None = None
    fetch: str = "http"
    filename: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"stable", "review"}:
            raise ValueError(f"{self.id} has status {self.status!r}")


def load_catalog(path: Path) -> list[CatalogEntry]:
    payload = tomllib.loads(path.read_text())
    entries = [CatalogEntry(**row) for row in payload.get("document", [])]
    ids = [entry.id for entry in entries]
    if len(ids) != len(set(ids)):
        raise ValueError("catalog document ids are not unique")
    return entries


def load_checks(path: Path) -> dict:
    return tomllib.loads(path.read_text())
