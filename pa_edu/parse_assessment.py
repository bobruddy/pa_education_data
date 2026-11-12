"""District PSSA and Keystone proficiency results.

PDE publishes one workbook per spring assessment year. Catalog `school_year` is
the start year of that school year (2024 → spring 2025 file). Rows with fewer
than 11 students are suppressed in the source; those percents stay null.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from pa_edu.codes import as_amount, as_code, as_text, read_headed, sheet_names

SUBJECT = {
    "english language arts": "ela",
    "math": "math",
    "mathematics": "math",
    "science": "science",
    "algebra i": "algebra_i",
    "algebra 1": "algebra_i",
    "biology": "biology",
    "literature": "literature",
}
COLUMN = {
    "year": "year",
    "aun": "aun",
    "county": "county",
    "district name": "lea_name",
    "district": "lea_name",
    "subject": "subject",
    "group": "student_group",
    "grade": "grade",
    "number scored": "number_scored",
    "percent advanced": "pct_advanced",
    "percent proficient": "pct_proficient",
    "percent basic": "pct_basic",
    "percent below basic": "pct_below_basic",
    "percent proficient and above": "pct_proficient_and_above",
    "percent advanced/proficient": "pct_proficient_and_above",
    "% advanced/proficient": "pct_proficient_and_above",
    "% proficient and above": "pct_proficient_and_above",
}


def parse_pssa(path: Path, document: dict) -> dict[str, pd.DataFrame]:
    return {"assessment_result": _parse(path, document, "pssa")}


def parse_keystone(path: Path, document: dict) -> dict[str, pd.DataFrame]:
    return {"assessment_result": _parse(path, document, "keystone")}


def _parse(path: Path, document: dict, assessment: str) -> pd.DataFrame:
    school_year = int(document["school_year"])
    document_id = document["document_id"]
    frame = read_headed(path, _sheet(path, assessment), 0)
    frame = _rename(frame)
    required = {"aun", "subject", "student_group", "grade", "pct_proficient_and_above"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{path.name} missing columns {sorted(missing)}")
    frame = frame.loc[frame["aun"].map(as_text).notna()].copy()
    frame["aun"] = as_code(frame["aun"], 9)
    frame["school_year"] = school_year
    frame["assessment"] = assessment
    frame["document_id"] = document_id
    frame["subject"] = frame["subject"].map(_subject)
    frame["grade"] = frame["grade"].map(_grade)
    frame["student_group"] = frame["student_group"].map(lambda value: as_text(value) or "")
    frame["lea_name"] = frame.get("lea_name", pd.Series(index=frame.index)).map(as_text)
    frame["county"] = frame.get("county", pd.Series(index=frame.index)).map(_county)
    for column in (
        "number_scored",
        "pct_advanced",
        "pct_proficient",
        "pct_basic",
        "pct_below_basic",
        "pct_proficient_and_above",
    ):
        if column in frame.columns:
            frame[column] = as_amount(frame[column])
        else:
            frame[column] = pd.NA
    if "year" in frame.columns:
        published = pd.to_numeric(frame["year"], errors="coerce")
        unexpected = published.dropna().loc[published != school_year + 1]
        if len(unexpected):
            raise ValueError(
                f"{path.name} Year values {sorted(unexpected.unique())} "
                f"do not match school_year {school_year} (expected {school_year + 1})"
            )
    frame = frame.loc[frame["subject"].notna() & frame["grade"].notna()].copy()
    return frame.loc[
        :,
        [
            "aun",
            "school_year",
            "assessment",
            "subject",
            "grade",
            "student_group",
            "number_scored",
            "pct_advanced",
            "pct_proficient",
            "pct_basic",
            "pct_below_basic",
            "pct_proficient_and_above",
            "lea_name",
            "county",
            "document_id",
        ],
    ]


def _sheet(path: Path, assessment: str) -> str:
    names = sheet_names(path)
    preferred = "pssa" if assessment == "pssa" else "keystone"
    for name in names:
        if name.casefold() == preferred:
            return name
    for name in names:
        frame = read_headed(path, name, 0)
        labels = {re.sub(r"\s+", " ", str(column).replace("\n", " ")).strip().casefold() for column in frame.columns}
        if "aun" in labels and "year" in labels and "subject" in labels:
            return name
    return names[0]


def _rename(frame: pd.DataFrame) -> pd.DataFrame:
    mapping = {}
    for column in frame.columns:
        key = re.sub(r"\s+", " ", str(column).replace("\n", " ")).strip().casefold()
        if key in COLUMN:
            mapping[column] = COLUMN[key]
    return frame.rename(columns=mapping)


def _subject(value: object) -> object:
    text = as_text(value)
    if text is None:
        return pd.NA
    return SUBJECT.get(text.casefold(), text.casefold().replace(" ", "_"))


def _grade(value: object) -> object:
    text = as_text(value)
    if text is None:
        return pd.NA
    folded = text.casefold()
    if folded in {"total", "district total"}:
        return "total"
    if text.isdigit():
        return f"{int(text):03d}"
    return folded


def _county(value: object) -> object:
    text = as_text(value)
    if text is None:
        return pd.NA
    return text.title() if text.isupper() else text
