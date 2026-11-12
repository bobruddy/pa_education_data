"""Home-education (and private tutor) counts by school district.

PDE publishes one statewide workbook on the enrollment page. District rows
carry an AUN; county and grand-total rows do not and are dropped. The chart
uses `Home Education Student Total`; private-tutor and age bands stay beside
it as published.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from pa_edu.codes import as_amount, as_code, as_text, read_sheet, require_columns, sheet_names


def parse_homeschool(path: Path, document: dict) -> dict[str, pd.DataFrame]:
    frame, columns = _table(path)
    year = int(document["school_year"])
    document_id = document["document_id"]
    students = as_amount(frame[columns["students"]])
    tutors = as_amount(frame[columns["tutors"]])
    young = as_amount(frame[columns["age_5_11"]])
    older = as_amount(frame[columns["age_12_plus"]])
    rows: list[dict] = []
    for index, count in students.items():
        aun = columns["aun"].at[index]
        if aun is None or pd.isna(aun):
            continue
        if pd.isna(count):
            continue
        tutor = tutors.at[index]
        young_count = young.at[index]
        older_count = older.at[index]
        rows.append(
            {
                "aun": aun,
                "school_year": year,
                "lea_name": columns["lea_name"].at[index],
                "county": columns["county"].at[index],
                "students": float(count),
                "private_tutor": None if pd.isna(tutor) else float(tutor),
                "age_5_11": None if pd.isna(young_count) else float(young_count),
                "age_12_plus": None if pd.isna(older_count) else float(older_count),
                "document_id": document_id,
            }
        )
    if not rows:
        raise ValueError(f"{path.name} has no home-education district rows")
    return {"home_education": pd.DataFrame(rows)}


def _table(path: Path) -> tuple[pd.DataFrame, dict[str, pd.Series | str]]:
    last_error: Exception | None = None
    for name in sheet_names(path):
        frame = read_sheet(path, name)
        try:
            found = require_columns(
                frame,
                [
                    "District Code",
                    "County Name",
                    "Private Tutor Total",
                    "Home Education Student Total",
                    "Home School Students  5-11 yrs.",
                    "Home School Students  12+  yrs.",
                ],
                path,
                name,
            )
        except ValueError as error:
            last_error = error
            continue
        # First column header is the school-year label; cells are LEA names.
        name_column = frame.columns[0]
        return frame, {
            "aun": as_code(frame[found["District Code"]], 9),
            "lea_name": frame[name_column].map(as_text),
            "county": frame[found["County Name"]].map(as_text),
            "students": found["Home Education Student Total"],
            "tutors": found["Private Tutor Total"],
            "age_5_11": found["Home School Students  5-11 yrs."],
            "age_12_plus": found["Home School Students  12+  yrs."],
        }
    raise ValueError(last_error or f"{path.name} has no home-education sheet")
