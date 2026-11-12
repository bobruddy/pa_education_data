"""Public-school October 1 enrollment at school, gender, and race."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from pa_edu.codes import as_code, as_text, find_sheet, read_headed, sheet_names

SHEET_BY_YEAR = {
    2010: ("School", 4),
    2009: ("School - Data File", 4),
    2008: ("School - Datafile", 4),
    2007: ("LEA - Data File", 6),
}
SESSION = {"a": "am", "p": "pm", "f": "full"}
GRADE_LABELS = {
    "prek": "Pre-kindergarten",
    "k4": "Kindergarten, first year",
    "k5": "Kindergarten",
    "pka": "Pre-kindergarten, morning",
    "pkp": "Pre-kindergarten, afternoon",
    "pkf": "Pre-kindergarten, full day",
    "k4a": "K4, morning",
    "k4p": "K4, afternoon",
    "k4f": "K4, full day",
    "k5a": "K5, morning",
    "k5p": "K5, afternoon",
    "k5f": "K5, full day",
    "eug": "Ungraded elementary",
    "sug": "Ungraded secondary",
}
for _grade in range(1, 13):
    GRADE_LABELS[f"{_grade:03d}"] = f"Grade {_grade}"


def grade_table() -> pd.DataFrame:
    rows = []
    for code, label in GRADE_LABELS.items():
        if code in {"prek", "k4", "k5"}:
            band, session = code, ""
        elif code in {"eug", "sug"}:
            band, session = "ungraded", ""
        elif code.isdigit():
            band, session = "grade", ""
        else:
            band, session = code[:2] if code.startswith("k") else "prek", SESSION[code[-1]]
            if code.startswith("pk"):
                band = "prek"
            elif code.startswith("k4"):
                band = "k4"
            elif code.startswith("k5"):
                band = "k5"
        rows.append({"grade_code": code, "label": label, "band": band, "session": session})
    return pd.DataFrame(rows)


def parse_enrollment(path: Path, document: dict) -> dict[str, pd.DataFrame]:
    year = int(document["school_year"])
    document_id = document["document_id"]
    sheet, skiprows = _sheet_spec(year)
    headcount = _melt_grades(
        _prepare(read_headed(path, find_sheet(path, sheet), skiprows)),
        year,
        document_id,
        school=True,
    )
    gender = _optional(path, "LEA, School and Gender", skiprows, year, document_id, "gender")
    race = _optional(path, "LEA and Race", skiprows, year, document_id, "race")
    return {
        "enrollment": headcount,
        "enrollment_gender": gender,
        "enrollment_race": race,
    }


def _sheet_spec(year: int) -> tuple[str, int]:
    if year >= 2011:
        return "LEA and School", 4
    if year not in SHEET_BY_YEAR:
        raise ValueError(f"no enrollment sheet rule for {year}")
    return SHEET_BY_YEAR[year]


def _optional(
    path: Path,
    preferred: str,
    skiprows: int,
    year: int,
    document_id: str,
    kind: str,
) -> pd.DataFrame:
    names = {name.casefold(): name for name in sheet_names(path)}
    if preferred.casefold() not in names:
        return pd.DataFrame()
    frame = _prepare(read_headed(path, names[preferred.casefold()], skiprows))
    return _melt_grades(frame, year, document_id, school=kind != "race", kind=kind)


def _prepare(frame: pd.DataFrame) -> pd.DataFrame:
    renamed = {}
    for column in frame.columns:
        label = _grade_label(column)
        if label != column:
            renamed[column] = label
    if renamed:
        frame = frame.rename(columns=renamed)
    frame.columns = [str(column).strip() for column in frame.columns]
    for column in ("County", "LEA Name", "LEA Type", "AUN"):
        if column in frame.columns:
            frame[column] = frame[column].ffill()
    if "LEA Name" in frame.columns:
        frame = frame.loc[~frame["LEA Name"].map(_is_total)].copy()
    if "AUN" in frame.columns:
        frame["AUN"] = as_code(frame["AUN"], 9)
        frame = frame.loc[frame["AUN"].str.fullmatch(r"\d{9}", na=False)].copy()
    if "School Number" in frame.columns:
        frame["School Number"] = as_code(frame["School Number"])
    return frame


def _melt_grades(
    frame: pd.DataFrame,
    year: int,
    document_id: str,
    school: bool,
    kind: str = "headcount",
) -> pd.DataFrame:
    grade_columns = [column for column in frame.columns if str(column).casefold() in GRADE_LABELS]
    if not grade_columns or "AUN" not in frame.columns:
        return pd.DataFrame()
    if kind == "race":
        race_column = _find_column(frame, "race")
        if race_column is not None:
            frame = _drop_blank_twins(frame, grade_columns, ["AUN", race_column])
    id_columns = ["AUN"]
    if school:
        if "School Number" not in frame.columns:
            return pd.DataFrame()
        frame = frame.loc[frame["School Number"].notna()].copy()
        id_columns.append("School Number")
    extra = []
    if kind == "gender":
        gender_column = _find_column(frame, "gender")
        if gender_column is None:
            return pd.DataFrame()
        extra.append(gender_column)
    if kind == "race":
        race_column = _find_column(frame, "race")
        if race_column is None:
            return pd.DataFrame()
        extra.append(race_column)
    for column in ("LEA Name", "LEA Type", "County", "School Name"):
        if column in frame.columns and column not in id_columns:
            id_columns.append(column)
    long = frame.melt(
        id_vars=id_columns + extra,
        value_vars=grade_columns,
        var_name="grade_code",
        value_name="enrollment",
    )
    parsed = long["enrollment"].map(_published_count)
    long["enrollment"] = [item[0] for item in parsed]
    long = long.loc[pd.Series(long["enrollment"]).notna().to_numpy()].copy()
    long["enrollment"] = long["enrollment"].astype("int64")
    long["grade_code"] = long["grade_code"].str.lower()
    long["school_year"] = year
    long["document_id"] = document_id
    long["aun"] = long["AUN"]
    long["lea_name"] = long["LEA Name"].map(_name) if "LEA Name" in long.columns else pd.NA
    long["lea_type"] = long["LEA Type"].map(_name) if "LEA Type" in long.columns else pd.NA
    long["county"] = long["County"].map(_name) if "County" in long.columns else pd.NA
    columns = ["aun", "school_year", "grade_code", "enrollment", "lea_name", "lea_type", "county", "document_id"]
    if school:
        long["school_number"] = long["School Number"]
        long["school_name"] = long["School Name"].map(_name) if "School Name" in long.columns else pd.NA
        columns[1:1] = ["school_number", "school_name"]
    if kind == "gender":
        long["gender"] = long[extra[0]].map(_name)
        columns.insert(3, "gender")
        long = long.loc[long["gender"].notna()]
    if kind == "race":
        long["race"] = long[extra[0]].map(_name)
        columns.insert(2, "race")
        long = long.loc[long["race"].notna()]
        long = _sum_grain(long, ["aun", "school_year", "race", "grade_code"])
    return long.loc[:, columns]


def _published_count(value: object) -> tuple[int | None, bool]:
    """A count, or a cell PDE did not publish exactly.

    ``*`` is suppressed. A trailing ``^`` is a count rounded to a multiple of 5,
    so it is not an exact enrollment either.
    """
    if value is None or isinstance(value, bool):
        return None, False
    if isinstance(value, (int, float)):
        if pd.isna(value):
            return None, False
        return int(round(float(value))), False
    text = str(value).strip()
    if text == "*" or text.endswith("^"):
        return None, True
    try:
        return int(round(float(text))), False
    except ValueError:
        return None, False


def _drop_blank_twins(
    frame: pd.DataFrame, grade_columns: list[str], identity: list[str]
) -> pd.DataFrame:
    """Drop an all-zero copy of a race row when the same AUN and race also has the real counts."""
    duplicated = frame.duplicated(identity, keep=False)
    if not duplicated.any():
        return frame

    def blank(row: pd.Series) -> bool:
        for value in row:
            number, suppressed = _published_count(value)
            if suppressed or number not in (None, 0):
                return False
        return True

    work = frame.copy()
    work["_blank"] = False
    work.loc[duplicated, "_blank"] = work.loc[duplicated, grade_columns].apply(blank, axis=1)
    sibling = work.loc[duplicated].groupby(identity, dropna=False)["_blank"].transform("all")
    work.loc[duplicated, "_keep_blank"] = sibling.to_numpy()
    drop = work["_blank"].eq(True) & work["_keep_blank"].fillna(False).eq(False)
    return work.loc[~drop].drop(columns=["_blank", "_keep_blank"])


def _sum_grain(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    if frame.empty or not frame.duplicated(keys).any():
        return frame
    others = [column for column in frame.columns if column not in keys and column != "enrollment"]
    return frame.groupby(keys, dropna=False, as_index=False).agg(
        {**{column: "first" for column in others}, "enrollment": "sum"}
    )


def _grade_label(column: object) -> str:
    if isinstance(column, float) and column.is_integer():
        text = str(int(column))
    elif isinstance(column, int) and not isinstance(column, bool):
        text = str(column)
    else:
        text = str(column).strip()
    if text.casefold() == "total":
        return "Total"
    folded = text.casefold().replace(" ", "")
    aliases = {"prek": "prek", "pk": "prek", "k4": "k4", "k5": "k5", "eug": "eug", "sug": "sug"}
    if folded in aliases:
        return aliases[folded]
    match = re.fullmatch(r"(pk|k4|k5)([apf])", folded)
    if match:
        return match.group(1) + match.group(2)
    if re.fullmatch(r"\d{1,2}", text):
        number = int(text)
        if 1 <= number <= 12:
            return f"{number:03d}"
    return text


def _find_column(frame: pd.DataFrame, token: str) -> str | None:
    for column in frame.columns:
        if token in str(column).casefold():
            return column
    return None


def _is_total(value: object) -> bool:
    text = as_text(value)
    return bool(text and text.casefold().endswith("total"))


def _name(value: object) -> object:
    text = as_text(value)
    return text if text is not None else pd.NA
