"""Shared paths, downloads, and column cleanup."""

from __future__ import annotations

import os
import re
import sqlite3
import time
import urllib.parse
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(os.environ["PDE_ROOT"]) if os.environ.get("PDE_ROOT") else Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ["PDE_DATA"]) if os.environ.get("PDE_DATA") else ROOT / "data"
DB_PATH = DATA_DIR / "pde.db"
LOOKUP_PATH = ROOT / "lookup_data" / "expense_lookups.csv"
PA_ORIGIN = "https://www.pa.gov"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
}

STRING_COLUMNS = ["LEA Name", "LEA Type", "County", "School Name", "AUN", "School Number"]
GRADE_COLUMNS = [
    "PKA", "PKP", "PKF",
    "K4A", "K4P", "K4F",
    "K5A", "K5P", "K5F",
    "001", "002", "003", "004", "005", "006",
    "007", "008", "009", "010", "011", "012",
]
ID_COLUMNS = ["aun", "lea_name", "lea_type", "county", "school_number", "school_name", "school_year"]


def http_get(url: str, timeout: int = 180, attempts: int = 4) -> requests.Response:
    """GET a PDE URL.

    docker09 drops the occasional handshake to www.pa.gov. The kernel gives up
    after about two minutes, and one failure used to stop the whole refine.
    """
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            response = requests.get(url, headers=HEADERS, timeout=(20, timeout))
            response.raise_for_status()
            return response
        except (requests.ConnectionError, requests.Timeout) as exc:
            last = exc
            if attempt + 1 == attempts:
                raise
            time.sleep(min(5 * (attempt + 1), 15))
    if last is None:
        raise RuntimeError(url)
    raise last


def fetch_hrefs(url: str) -> list[str]:
    response = http_get(url, timeout=60)
    soup = BeautifulSoup(response.text, "html.parser")
    return [a["href"] for a in soup.find_all("a", href=True)]


def absolute_url(href: str) -> str:
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("/"):
        return PA_ORIGIN + href
    return urllib.parse.urljoin(PA_ORIGIN, href)


def cache_download(url: str, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    decoded = urllib.parse.unquote(url.split("?", 1)[0])
    filename = decoded.rstrip("/").rsplit("/", 1)[-1].lower().replace(" ", "_")
    destination = directory / filename
    if destination.exists() and destination.stat().st_size > 0:
        return destination
    print(f"downloading {url}")
    response = http_get(url, timeout=180)
    destination.write_bytes(response.content)
    return destination


def write_parquet(frame: pd.DataFrame, dest: Path) -> None:
    """Write a Parquet file under a temporary name, then rename it into place."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    temporary = dest.parent / f".{dest.name}.{os.getpid()}.tmp"
    frame.to_parquet(temporary, index=False)
    os.replace(temporary, dest)


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def read_excel(path: Path, sheet: str, skiprows: int) -> pd.DataFrame:
    engine = "xlrd" if path.suffix.lower() == ".xls" else "openpyxl"
    frame = pd.read_excel(path, sheet_name=sheet, skiprows=skiprows, engine=engine)
    if _looks_like_header(frame.columns):
        return frame
    raw = pd.read_excel(path, sheet_name=sheet, header=None, engine=engine, nrows=15)
    for index in range(len(raw)):
        labels = [_cell_label(value) for value in raw.iloc[index].tolist()]
        if "AUN" in labels and ("LEA Name" in labels or "School Name" in labels):
            return pd.read_excel(path, sheet_name=sheet, skiprows=index, engine=engine)
    return frame


def sheet_names(path: Path) -> list[str]:
    engine = "xlrd" if path.suffix.lower() == ".xls" else "openpyxl"
    with pd.ExcelFile(path, engine=engine) as workbook:
        return list(workbook.sheet_names)


def id_to_str(values: pd.Series) -> pd.Series:
    def one(value: object) -> object:
        if pd.isna(value):
            return pd.NA
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        if isinstance(value, int) and not isinstance(value, bool):
            return str(value)
        text = str(value).strip()
        if re.fullmatch(r"\d+\.0", text):
            return text[:-2]
        return text

    return values.map(one).astype("string")


def normalize_grade_columns(frame: pd.DataFrame) -> pd.DataFrame:
    renamed: dict[object, str] = {}
    for column in frame.columns:
        label = _cell_label(column)
        if re.fullmatch(r"\d{1,2}", label):
            number = int(label)
            if 1 <= number <= 12:
                renamed[column] = f"{number:03d}"
                continue
        if label in {"PreK", "K4", "K5"}:
            renamed[column] = {"PreK": "PKA", "K4": "K4A", "K5": "K5A"}[label]
        elif label == "County Name":
            renamed[column] = "County"
        elif label != column:
            renamed[column] = label
    if renamed:
        frame = frame.rename(columns=renamed)
    frame.columns = [str(column).strip() for column in frame.columns]
    return frame


def _cell_label(value: object) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return str(value).strip()


def _looks_like_header(columns: pd.Index) -> bool:
    labels = {_cell_label(column) for column in columns}
    return "AUN" in labels or "LEA Name" in labels
