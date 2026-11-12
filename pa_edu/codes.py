"""Shared id cleanup and Excel reads for the refined tables."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from pa_edu.common import id_to_str, sheet_names

ACCOUNT_RE = re.compile(r"^(\d{4})-(\d{3})(?:-(\d+))?$")


def as_text(value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)) or pd.isna(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    text = str(value).strip()
    if text in {"", "nan", "None", "<NA>"}:
        return None
    if re.fullmatch(r"\d+\.0", text):
        return text[:-2]
    return text


def as_code(values: pd.Series, width: int | None = None) -> pd.Series:
    text = id_to_str(values)

    def one(value: object) -> object:
        if value is None or pd.isna(value):
            return pd.NA
        token = str(value).strip()
        if width and token.isdigit():
            return token.zfill(width)
        return token

    return text.map(one).astype("string")


def as_amount(values: pd.Series) -> pd.Series:
    return pd.to_numeric(values, errors="coerce")


def find_sheet(path: Path, preferred: str) -> str:
    names = sheet_names(path)
    if preferred in names:
        return preferred
    folded = {name.casefold(): name for name in names}
    if preferred.casefold() in folded:
        return folded[preferred.casefold()]
    raise ValueError(f"{path.name} has no sheet {preferred!r} in {names}")


def sheets_starting(path: Path, prefix: str) -> list[str]:
    folded = prefix.casefold()
    return [name for name in sheet_names(path) if name.casefold().startswith(folded)]


def read_sheet(path: Path, sheet: str, skiprows: int = 0) -> pd.DataFrame:
    engine = "xlrd" if path.suffix.lower() == ".xls" else "openpyxl"
    frame = pd.read_excel(path, sheet_name=sheet, skiprows=skiprows, engine=engine)
    frame.columns = [str(column).strip() for column in frame.columns]
    return frame


def read_headed(path: Path, sheet: str, skiprows: int) -> pd.DataFrame:
    frame = read_sheet(path, sheet, skiprows)
    if _headed(frame):
        return frame
    engine = "xlrd" if path.suffix.lower() == ".xls" else "openpyxl"
    raw = pd.read_excel(path, sheet_name=sheet, header=None, nrows=20, engine=engine)
    for index, row in raw.iterrows():
        labels = ["" if pd.isna(value) else str(value).strip() for value in row.tolist()]
        if "AUN" in labels:
            return read_sheet(path, sheet, int(index))
    return frame


def column_map(frame: pd.DataFrame) -> dict[str, str]:
    return {str(column).strip().casefold(): column for column in frame.columns}


def require_columns(frame: pd.DataFrame, names: list[str], path: Path, sheet: str) -> dict[str, str]:
    found = column_map(frame)
    missing = [name for name in names if name.casefold() not in found]
    if missing:
        raise ValueError(f"{path.name} sheet {sheet} missing {missing}")
    return {name: found[name.casefold()] for name in names}


def empty_frame(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame({column: pd.Series(dtype="object") for column in columns})


def _headed(frame: pd.DataFrame) -> bool:
    labels = {str(column).strip().casefold() for column in frame.columns}
    return "aun" in labels
