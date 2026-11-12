"""Act 1 index: district adjusted rates and the statewide base index.

The adjusted-index workbook is one row per school district and one column per
school year, with the rate as a decimal (0.053 is 5.3%). Philadelphia is on
the sheet with an empty rate. The base index is the one-page history PDF:
statewide average weekly wage, the employment cost index, and their average.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from pa_edu.codes import as_amount, as_code, as_text, read_headed, read_sheet, require_columns, sheet_names

YEAR_COLUMN = re.compile(r"^(20\d{2})-(?:20)?(\d{2})$")
SCHOOL_YEARS = re.compile(r"Use for school year:\s*(.+)")
PERCENT = re.compile(r"\d+(?:\.\d+)?%")


def parse_act1(path: Path, document: dict) -> dict[str, pd.DataFrame]:
    frame, columns = _index_table(path)
    document_id = document["document_id"]
    rows: list[dict] = []
    for header in frame.columns:
        match = YEAR_COLUMN.fullmatch(str(header).strip())
        if match is None:
            continue
        school_year = int(match.group(1))
        if int(match.group(2)) != (school_year + 1) % 100:
            raise ValueError(f"{path.name} column {header} is not a school year")
        rates = as_amount(frame[header])
        if (rates.dropna() >= 1).any():
            raise ValueError(f"{path.name} {header} looks like a percent; expected a decimal such as 0.035")
        for index, rate in rates.items():
            if pd.isna(rate):
                continue
            aun = columns["aun"].at[index]
            if aun is None or pd.isna(aun):
                continue
            rows.append(
                {
                    "aun": aun,
                    "school_year": school_year,
                    "lea_name": columns["lea_name"].at[index],
                    "county": columns["county"].at[index],
                    "adjusted_index": float(rate),
                    "document_id": document_id,
                }
            )
    if not rows:
        raise ValueError(f"{path.name} has no Act 1 index rates")
    return {"act1_index": pd.DataFrame(rows)}


def parse_act1_base(path: Path, document: dict) -> dict[str, pd.DataFrame]:
    frame = base_from_text(_pdf_text(path))
    frame["document_id"] = document["document_id"]
    return {"act1_base": frame}


def base_from_text(text: str) -> pd.DataFrame:
    years = _school_years(text)
    columns = {
        "base_index": _percent_line(text, r"Base index:"),
        "saww_increase": _percent_line(text, r"SAWW"),
        "eci_increase": _percent_line(text, r"ECI"),
    }
    for name, values in columns.items():
        if len(values) != len(years):
            raise ValueError(
                f"Act 1 base history {name} has {len(values)} values for {len(years)} school years"
            )
    return pd.DataFrame({"school_year": years, **columns})


def _index_table(path: Path) -> tuple[pd.DataFrame, dict[str, pd.Series]]:
    last_error: Exception | None = None
    for name in sheet_names(path):
        frame = read_sheet(path, name)
        if "aun" not in {str(column).strip().casefold() for column in frame.columns}:
            frame = read_headed(path, name, 0)
        try:
            found = require_columns(frame, ["AUN", "School District", "County"], path, name)
        except ValueError as error:
            last_error = error
            continue
        return frame, {
            "aun": as_code(frame[found["AUN"]], 9),
            "lea_name": frame[found["School District"]].map(as_text),
            "county": frame[found["County"]].map(as_text),
        }
    raise ValueError(last_error or f"{path.name} has no Act 1 index sheet")


def _school_years(text: str) -> list[int]:
    match = SCHOOL_YEARS.search(text)
    if match is None:
        raise ValueError("Act 1 base history has no school-year line")
    found = re.findall(r"(20\d{2})-20(\d{2})", match.group(1))
    years = [int(start) for start, _end in found]
    if not years:
        raise ValueError("Act 1 base history school-year line has no years")
    if len(set(years)) != len(years):
        raise ValueError("Act 1 base history repeats a school year")
    return years


def _percent_line(text: str, label: str) -> list[float]:
    match = re.search(rf"(?<![A-Za-z]){label}\s+((?:{PERCENT.pattern}\s*)+)", text)
    if match is None:
        raise ValueError(f"Act 1 base history has no {label} line")
    return [round(float(token[:-1]) / 100, 5) for token in PERCENT.findall(match.group(1))]


def _pdf_text(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)
