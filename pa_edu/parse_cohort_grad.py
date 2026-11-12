"""LEA cohort graduation rates.

PDE publishes one workbook per reporting year and per span (4, 5, or 6
years). This parser reads the LEA sheet used from 2017–18 on: graduates,
cohort, and the all-student rate, plus subgroup rates. Foster, homeless,
and military columns are present from 2021–22 and absent before that.
School sheets are left for a later school-grain pass. Files that still
say “Total Grads” or “ELL” are a different layout and are not this parser.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from pa_edu.codes import as_code, as_text, sheet_names

IDENTITY = {
    "lea type": "lea_type",
    "aun": "aun",
    "lea": "lea_name",
    "grads": "graduates",
    "cohort": "cohort",
    "cohort grad rate": "rate",
}
GROUPS = {
    "male grad rate": "male",
    "female grad rate": "female",
    "aian grad rate": "american_indian",
    "native hawaiian or pacific islander grad rate": "pacific_islander",
    "asian grad rate": "asian",
    "black grad rate": "black",
    "hispanic grad rate": "hispanic",
    "white grad rate": "white",
    "multi-racial grad rate": "multi_racial",
    "special ed grad rate": "special_ed",
    "el grad rate": "el",
    "econ disadv grad rate": "econ_disadv",
    "migrant grad rate": "migrant",
    "foster grad rate": "foster",
    "homeless grad rate": "homeless",
    "military grad rate": "military",
}
OPTIONAL_GROUPS = {"foster", "homeless", "military"}
REQUIRED_GROUPS = set(GROUPS.values()) - OPTIONAL_GROUPS
SPANS = {4, 5, 6}


def parse_cohort_grad(path: Path, document: dict) -> dict[str, pd.DataFrame]:
    year = _year(document)
    span = _span(document)
    document_id = document["document_id"]
    header_index, columns = _header(path)
    frame = _table(path, header_index, columns)
    facts: list[dict] = []
    groups: list[dict] = []
    seen: set[str] = set()
    for index in frame.index:
        aun = _aun(frame.at[index, "aun"])
        if aun is None:
            continue
        if aun in seen:
            raise ValueError(f"{path.name} repeats AUN {aun}")
        seen.add(aun)
        facts.append(
            {
                "aun": aun,
                "school_year": year,
                "span": span,
                "lea_name": as_text(frame.at[index, "lea_name"]),
                "lea_type": as_text(frame.at[index, "lea_type"]),
                "graduates": _whole(frame.at[index, "graduates"], f"{aun} graduates", path),
                "cohort": _whole(frame.at[index, "cohort"], f"{aun} cohort", path),
                "rate": _fraction(frame.at[index, "rate"], f"{aun} cohort grad rate", path),
                "document_id": document_id,
            }
        )
        for group in _group_columns(columns):
            raw = frame.at[index, group]
            if _blank(raw):
                continue
            groups.append(
                {
                    "aun": aun,
                    "school_year": year,
                    "span": span,
                    "student_group": group,
                    "rate": _fraction(raw, f"{aun} {group}", path),
                    "document_id": document_id,
                }
            )
    if not facts:
        raise ValueError(f"{path.name} has no LEA cohort rows")
    return {
        "cohort_graduation": pd.DataFrame(facts),
        "cohort_graduation_group": pd.DataFrame(groups),
    }


def _year(document: dict) -> int:
    year = document.get("school_year")
    if year is None:
        raise ValueError("cohort graduation document has no school_year")
    return int(year)


def _span(document: dict) -> int:
    span = document.get("span")
    if span not in SPANS:
        raise ValueError(f"cohort graduation span must be 4, 5, or 6, got {span!r}")
    return int(span)


def _header(path: Path) -> tuple[int, dict[str, int]]:
    sheet = _lea_sheet(path)
    raw = _read(path, sheet)
    header_index = None
    for index, row in raw.iterrows():
        if any(_norm(value) == "aun" for value in row.tolist()):
            header_index = int(index)
            break
    if header_index is None:
        raise ValueError(f"{path.name} LEA sheet has no AUN header")
    columns: dict[str, int] = {}
    for position, value in enumerate(raw.iloc[header_index].tolist()):
        name = _norm(value)
        if not name:
            continue
        field = IDENTITY.get(name) or GROUPS.get(name)
        if field is None:
            raise ValueError(f"{path.name} has an unrecognized LEA column {value!r}")
        if field in columns:
            raise ValueError(f"{path.name} repeats column {value!r}")
        columns[field] = position
    missing = [field for field in (*IDENTITY.values(), *sorted(REQUIRED_GROUPS)) if field not in columns]
    if missing:
        raise ValueError(f"{path.name} LEA sheet is missing {missing}")
    return header_index, columns


def _table(path: Path, header_index: int, columns: dict[str, int]) -> pd.DataFrame:
    raw = _read(path, _lea_sheet(path))
    data = raw.iloc[header_index + 1 :]
    frame = pd.DataFrame({field: data.iloc[:, position].reset_index(drop=True) for field, position in columns.items()})
    return frame


def _lea_sheet(path: Path) -> str:
    matches = [name for name in sheet_names(path) if "by lea" in name.casefold()]
    if len(matches) != 1:
        raise ValueError(f"{path.name} has LEA sheets {matches}")
    return matches[0]


def _read(path: Path, sheet: str) -> pd.DataFrame:
    engine = "xlrd" if path.suffix.lower() == ".xls" else "openpyxl"
    return pd.read_excel(path, sheet_name=sheet, header=None, engine=engine)


def _group_columns(columns: dict[str, int]) -> list[str]:
    return [field for field in columns if field in GROUPS.values()]


def _aun(value: object) -> str | None:
    code = as_code(pd.Series([value]), 9).iloc[0]
    if code is None or pd.isna(code):
        return None
    text = str(code)
    if len(text) == 9 and text.isdigit():
        return text
    return None


def _whole(value: object, label: str, path: Path) -> int:
    if _blank(value):
        raise ValueError(f"{path.name} {label} is blank")
    number = float(value)
    if abs(number - round(number)) > 1e-6:
        raise ValueError(f"{path.name} {label} is not a whole number ({value!r})")
    return int(round(number))


def _fraction(value: object, label: str, path: Path) -> float:
    if _blank(value):
        raise ValueError(f"{path.name} {label} is blank")
    number = float(value)
    if number < 0 or number > 1:
        raise ValueError(f"{path.name} {label} is outside 0–1 ({number})")
    return number


def _blank(value: object) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except TypeError:
        return False
    text = str(value).strip()
    if not text:
        return True
    # PDE writes a sentence in a rate cell when the group is too small to show.
    folded = text.casefold()
    return "ferpa" in folded and "supress" in folded.replace("pp", "p")


def _norm(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass
    return " ".join(str(value).replace("\n", " ").split()).casefold()
