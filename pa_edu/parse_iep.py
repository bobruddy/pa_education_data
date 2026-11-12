"""Special education (IEP) enrollment by LEA from PennData.

PennData publishes one multi-year workbook of December 1 school-age child count
versus total enrollment by LEA. Each sheet is a school year. Suppressed counts
(`*`) are skipped — absence, not zero. “Wards of State” placeholder AUNs are
not LEAs and are dropped.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from pa_edu.codes import as_amount, as_code, as_text, sheet_names

YEAR_SHEET = re.compile(r"^(\d{4})\s*[-–]\s*(\d{4})$")
WARD_AUN = re.compile(r"^\d{3}999999$")


def parse_iep(path: Path, document: dict) -> dict[str, pd.DataFrame]:
    document_id = document["document_id"]
    parts: list[pd.DataFrame] = []
    for name in sheet_names(path):
        year = _sheet_year(name)
        if year is None:
            continue
        frame = _read_year(path, name, year, document_id)
        if not frame.empty:
            parts.append(frame)
    if not parts:
        raise ValueError(f"{path.name} has no IEP-by-LEA year sheets")
    return {"enrollment_iep": pd.concat(parts, ignore_index=True)}


def _sheet_year(name: str) -> int | None:
    match = YEAR_SHEET.fullmatch(str(name).strip())
    if not match:
        return None
    start = int(match.group(1))
    end = int(match.group(2))
    if end != start + 1:
        raise ValueError(f"IEP sheet {name!r} years are not consecutive")
    return start


def _read_year(path: Path, sheet: str, year: int, document_id: str) -> pd.DataFrame:
    engine = "xlrd" if path.suffix.lower() == ".xls" else "openpyxl"
    raw = pd.read_excel(path, sheet_name=sheet, header=None, engine=engine)
    header_index = None
    for index, row in raw.iterrows():
        labels = [_label(value) for value in row.tolist()]
        if "aun" in labels and any("special education" in label for label in labels):
            header_index = int(index)
            break
    if header_index is None:
        raise ValueError(f"{path.name} sheet {sheet} has no AUN / special education header")
    columns = [_label(value) or f"col_{position}" for position, value in enumerate(raw.iloc[header_index].tolist())]
    frame = raw.iloc[header_index + 1 :].copy()
    frame.columns = columns
    frame = frame.loc[:, ~pd.Index(frame.columns).duplicated()].copy()
    aun_column = _column(frame, {"aun"})
    name_column = _column(frame, {"school name", "lea", "lea name"})
    iep_column = _column(frame, {"number of special education students"}, contains=("special education",))
    total_column = _column(frame, {"total enrollment"})
    pct_column = _column(frame, set(), contains=("special ed", "%"))
    if aun_column is None or iep_column is None:
        raise ValueError(f"{path.name} sheet {sheet} missing AUN or special education count")
    rows: list[dict] = []
    seen: set[str] = set()
    auns = as_code(frame[aun_column], 9)
    iep_counts = frame[iep_column]
    totals = as_amount(frame[total_column]) if total_column else pd.Series(pd.NA, index=frame.index)
    pcts = as_amount(frame[pct_column]) if pct_column else pd.Series(pd.NA, index=frame.index)
    names = frame[name_column].map(as_text) if name_column else pd.Series(pd.NA, index=frame.index)
    for index, aun in auns.items():
        if aun is None or pd.isna(aun):
            continue
        aun = str(aun)
        if WARD_AUN.fullmatch(aun):
            continue
        if aun in seen:
            raise ValueError(f"{path.name} sheet {sheet} repeats AUN {aun}")
        count = _published_count(iep_counts.at[index])
        if count is None:
            continue
        seen.add(aun)
        total = totals.at[index]
        pct = pcts.at[index]
        rows.append(
            {
                "aun": aun,
                "school_year": year,
                "lea_name": names.at[index],
                "iep_enrollment": count,
                "total_enrollment": None if pd.isna(total) else int(round(float(total))),
                "pct_iep": None if pd.isna(pct) else _as_percent(float(pct)),
                "document_id": document_id,
            }
        )
    return pd.DataFrame(rows)


def _published_count(value: object) -> int | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, str):
        text = value.strip()
        if text in {"", "*"} or text.endswith("^"):
            return None
        try:
            return int(round(float(text)))
        except ValueError:
            return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if pd.isna(value):
            return None
        return int(round(float(value)))
    return None


def _column(
    frame: pd.DataFrame,
    exact: set[str],
    contains: tuple[str, ...] | None = None,
) -> str | None:
    for column in frame.columns:
        label = str(column).casefold().strip()
        if label in exact:
            return column
    if contains:
        found = [
            column
            for column in frame.columns
            if all(token in str(column).casefold() for token in contains)
        ]
        if len(found) == 1:
            return found[0]
    return None


def _label(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).replace("\xa0", " ").strip().casefold()


def _as_percent(value: float) -> float:
    """Newer sheets publish a fraction; older sheets already use 0–100."""
    if 0 <= value <= 1:
        return round(value * 100, 4)
    return float(value)
