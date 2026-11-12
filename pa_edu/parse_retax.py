"""School district real estate millage from the general fund budget.

PDE posts one workbook a year. A district that crosses a county line, or that
taxes land and buildings separately, has more than one row. Pittsburgh and
Scranton are listed with a calendar-year note and no millage; those rows are
not rates.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from pa_edu.codes import as_amount, as_code, as_text, read_sheet, require_columns, sheet_names

ID_COLUMNS = ["AUN", "School District", "Tax County", "Municipality / Other Info"]
_CALENDAR_NOTE = re.compile(r"^20\d{2}\s+(?:calendar year|cy)$", re.IGNORECASE)


def parse_retax(path: Path, document: dict) -> dict[str, pd.DataFrame]:
    frame, columns, mills_column, college_column = _table(path)
    year = int(document["school_year"])
    document_id = document["document_id"]
    rates = as_amount(frame[mills_column])
    college = as_amount(frame[college_column]) if college_column else None
    rows: list[dict] = []
    for index, rate in rates.items():
        if pd.isna(rate):
            continue
        aun = columns["aun"].at[index]
        county = columns["county"].at[index]
        if aun is None or pd.isna(aun) or county is None or pd.isna(county):
            raise ValueError(f"{path.name} has a millage row without an AUN and county")
        college_rate = None if college is None else college.at[index]
        rows.append(
            {
                "aun": aun,
                "school_year": year,
                "county": county,
                "locality": columns["locality"].at[index] or "",
                "mills": float(rate),
                "college_mills": None if college_rate is None or pd.isna(college_rate) else float(college_rate),
                "document_id": document_id,
            }
        )
    if not rows:
        raise ValueError(f"{path.name} has no real estate millage")
    return {"real_estate_tax": pd.DataFrame(rows)}


def _table(path: Path) -> tuple[pd.DataFrame, dict[str, pd.Series], str, str | None]:
    last_error: Exception | None = None
    for name in sheet_names(path):
        frame = read_sheet(path, name)
        try:
            found = require_columns(frame, ID_COLUMNS, path, name)
        except ValueError as error:
            last_error = error
            continue
        mills = _named(frame.columns, "real estate mills")
        if mills is None:
            raise ValueError(f"{path.name} sheet {name} has no real estate mills column")
        return (
            frame,
            {
                "aun": as_code(frame[found["AUN"]], 9),
                "county": frame[found["Tax County"]].map(as_text),
                "locality": frame[found["Municipality / Other Info"]].map(_place),
            },
            mills,
            _named(frame.columns, "community college"),
        )
    raise ValueError(last_error or f"{path.name} has no real estate tax sheet")


def _named(columns, needle: str) -> str | None:
    found = [column for column in columns if needle in str(column).casefold()]
    if len(found) != 1:
        return None
    return found[0]


def _place(value: object) -> str:
    text = as_text(value)
    if text is None or _CALENDAR_NOTE.match(text):
        return ""
    return text
