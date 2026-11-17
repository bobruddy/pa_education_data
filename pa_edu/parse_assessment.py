"""District PSSA and Keystone proficiency results, and the school-level workbooks.

PDE publishes one workbook per spring assessment year. Catalog `school_year` is
the start year of that school year (2024 → spring 2025 file). Rows with fewer
than 11 students are suppressed in the source; those percents stay null.

School PSSA and school Keystone are different workbooks and a different grain
from the district files. Both land in `assessment_result_school`.
`pct_proficient_and_above` stays null in this table when that column is absent.
The school view fills that cell from advanced plus proficient. `growth` is
the 2015 PSSA PVAAS column, not a proficiency, and it is not added into the
LEA view. The 2015 Keystone school file has no AUN and is not this layout.
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


SCHOOL_COLUMN = {
    "year": "year",
    "aun": "aun",
    "school number": "school_number",
    "county": "county",
    "district name": "lea_name",
    "district": "lea_name",
    "school name": "school_name",
    "school": "school_name",
    "subject": "subject",
    "group": "student_group",
    "grade": "grade",
    "number scored": "number_scored",
    "% advanced": "pct_advanced",
    "percent advanced": "pct_advanced",
    "% proficient": "pct_proficient",
    "percent proficient": "pct_proficient",
    "% basic": "pct_basic",
    "percent basic": "pct_basic",
    "% below basic": "pct_below_basic",
    "percent below basic": "pct_below_basic",
    "percent proficient and above": "pct_proficient_and_above",
    "% advanced/proficient": "pct_proficient_and_above",
    "% proficient and above": "pct_proficient_and_above",
    "percent advanced/proficient": "pct_proficient_and_above",
    "growth**": "growth",
}
SCHOOL_REQUIRED = {
    "aun",
    "school_number",
    "lea_name",
    "school_name",
    "subject",
    "student_group",
    "grade",
    "number_scored",
    "pct_advanced",
    "pct_proficient",
    "pct_basic",
    "pct_below_basic",
}
SCHOOL_OUTPUT = [
    "aun",
    "school_number",
    "school_name",
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
    "growth",
    "lea_name",
    "county",
    "document_id",
]
_UNNAMED = re.compile(r"unnamed: \d+(?:\.\d+)?")


def parse_pssa(path: Path, document: dict) -> dict[str, pd.DataFrame]:
    return {"assessment_result": _parse(path, document, "pssa")}


def parse_keystone(path: Path, document: dict) -> dict[str, pd.DataFrame]:
    return {"assessment_result": _parse(path, document, "keystone")}


def parse_pssa_school(path: Path, document: dict) -> dict[str, pd.DataFrame]:
    return {"assessment_result_school": _parse_school(path, document, "pssa")}


def parse_keystone_school(path: Path, document: dict) -> dict[str, pd.DataFrame]:
    return {"assessment_result_school": _parse_school(path, document, "keystone")}


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
    if folded in {"total", "district total", "school total"}:
        return "total"
    if text.isdigit():
        return f"{int(text):03d}"
    return folded


def _parse_school(path: Path, document: dict, assessment: str) -> pd.DataFrame:
    school_year = int(document["school_year"])
    document_id = document["document_id"]
    frame = read_headed(path, _school_sheet(path), 0)
    frame = _drop_blank_headers(path, frame)
    frame = _rename_school(path, frame)
    missing = SCHOOL_REQUIRED - set(frame.columns)
    if missing:
        raise ValueError(f"{path.name} missing columns {sorted(missing)}")
    frame = frame.loc[frame["aun"].map(as_text).notna()].copy()
    frame["aun"] = as_code(frame["aun"], 9)
    frame["school_number"] = _school_number(frame["school_number"])
    frame["school_year"] = school_year
    frame["assessment"] = assessment
    frame["document_id"] = document_id
    frame["subject"] = frame["subject"].map(_subject)
    frame["grade"] = frame["grade"].map(_grade)
    frame["student_group"] = frame["student_group"].map(lambda value: as_text(value) or "")
    frame["lea_name"] = frame["lea_name"].map(as_text)
    frame["school_name"] = frame["school_name"].map(as_text)
    if "county" in frame.columns:
        frame["county"] = frame["county"].map(_county)
    else:
        frame["county"] = pd.Series(pd.NA, index=frame.index, dtype="object")
    for column in (
        "number_scored",
        "pct_advanced",
        "pct_proficient",
        "pct_basic",
        "pct_below_basic",
        "pct_proficient_and_above",
        "growth",
    ):
        if column in frame.columns:
            frame[column] = as_amount(frame[column])
        else:
            frame[column] = as_amount(pd.Series(pd.NA, index=frame.index))
    if "year" in frame.columns:
        published = pd.to_numeric(frame["year"], errors="coerce")
        unexpected = published.dropna().loc[published != school_year + 1]
        if len(unexpected):
            raise ValueError(
                f"{path.name} Year values {sorted(unexpected.unique())} "
                f"do not match school_year {school_year} (expected {school_year + 1})"
            )
    incomplete = (
        frame["aun"].isna()
        | frame["school_number"].isna()
        | frame["school_name"].isna()
        | frame["lea_name"].isna()
        | frame["subject"].isna()
        | frame["grade"].isna()
        | frame["student_group"].eq("")
    )
    if incomplete.any():
        raise ValueError(
            f"{path.name} has {int(incomplete.sum())} school rows missing an identity field"
        )
    return frame.loc[:, SCHOOL_OUTPUT]


def _school_sheet(path: Path) -> str:
    found = []
    for name in sheet_names(path):
        frame = read_headed(path, name, 0)
        labels = {_header_key(column) for column in frame.columns}
        if "aun" in labels and "school number" in labels:
            found.append(name)
    if len(found) != 1:
        raise ValueError(f"{path.name} has school sheets {found or sheet_names(path)}")
    return found[0]


def _drop_blank_headers(path: Path, frame: pd.DataFrame) -> pd.DataFrame:
    """A cell with no header is not a published column."""
    keep = [column for column in frame.columns if not _UNNAMED.fullmatch(_header_key(column))]
    if not keep:
        raise ValueError(f"{path.name} has no header")
    return frame.loc[:, keep]


def _rename_school(path: Path, frame: pd.DataFrame) -> pd.DataFrame:
    mapping = {}
    unknown = []
    for column in frame.columns:
        target = SCHOOL_COLUMN.get(_header_key(column))
        if target is None:
            unknown.append(str(column))
            continue
        mapping[column] = target
    if unknown:
        raise ValueError(f"{path.name} has unknown columns {unknown}")
    renamed = frame.rename(columns=mapping)
    if renamed.columns.duplicated().any():
        names = renamed.columns[renamed.columns.duplicated()].tolist()
        raise ValueError(f"{path.name} repeats columns {names}")
    return renamed


def _school_number(values: pd.Series) -> pd.Series:
    """Digits only, without leading zeros. ``000007691`` and ``7691`` are one school."""
    codes = as_code(values)

    def one(value: object) -> object:
        if value is None or pd.isna(value):
            return pd.NA
        token = str(value)
        if token.isdigit():
            return token.lstrip("0") or "0"
        return token

    return codes.map(one).astype("string")


def _header_key(column: object) -> str:
    return re.sub(r"\s+", " ", str(column).replace("\n", " ")).strip().casefold()


def _county(value: object) -> object:
    text = as_text(value)
    if text is None:
        return pd.NA
    return text.title() if text.isupper() else text
