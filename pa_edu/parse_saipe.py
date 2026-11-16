"""Census SAIPE school-district estimates, one retained text file per year.

The catalog ``school_year`` is the SAIPE year. A record whose length is not the
one that year's layout describes is rejected, and the file's own tag
(``sd24-pa.txt`` or ``sd08_PA.txt``) must name that same year. A blank count
is null. A reported zero stays. This parser does not look up an AUN.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

TAG = re.compile(r"sd(\d{2})[_-]pa\.txt", re.IGNORECASE)
STATE = (1, 2)
DISTRICT = (4, 8)


@dataclass(frozen=True)
class Layout:
    length: int
    name: tuple[int, int]
    total: tuple[int, int]
    children: tuple[int, int]
    poverty: tuple[int, int]
    tag: tuple[int, int]


# Census school-district layouts. Positions are 1-based and inclusive.
# 2004–2009 records are 124 characters; 2010–2024 records are 131.
_EARLY = Layout(124, (10, 74), (76, 83), (85, 92), (94, 101), (103, 123))
_LATE = Layout(131, (10, 81), (83, 90), (92, 99), (101, 108), (110, 130))


def layout_for(year: int) -> Layout:
    if 2004 <= year <= 2009:
        return _EARLY
    if 2010 <= year <= 2024:
        return _LATE
    raise ValueError(f"no SAIPE layout for {year}")


def parse_saipe(path: Path, document: dict) -> dict[str, pd.DataFrame]:
    year = document.get("school_year")
    if year is None:
        raise ValueError(f"{path.name} has no catalog school_year")
    year = int(year)
    layout = layout_for(year)
    text = path.read_bytes().decode("ascii")
    rows = []
    for line in text.splitlines():
        if len(line) != layout.length:
            raise ValueError(
                f"{path.name} record length is {len(line)}, layout for {year} is {layout.length}"
            )
        rows.append(_row(line, layout, year, document, path))
    if not rows:
        raise ValueError(f"{path.name} has no districts")
    frame = pd.DataFrame(rows)
    frame["nces_leaid"] = frame["nces_leaid"].astype("string")
    frame["census_name"] = frame["census_name"].astype("string")
    frame["document_id"] = frame["document_id"].astype("string")
    for column in ("total_population", "population_5_17", "children_5_17_in_poverty"):
        frame[column] = frame[column].astype("Int64")
    return {"saipe_district": frame}


def _row(line: str, layout: Layout, year: int, document: dict, path: Path) -> dict:
    state = _field(line, STATE)
    district = _field(line, DISTRICT)
    if state != "42" or not re.fullmatch(r"\d{5}", district):
        raise ValueError(f"{path.name} district id {state!r} {district!r} is not a Pennsylvania LEAID")
    tag = _field(line, layout.tag)
    found = TAG.findall(tag)
    if found != [f"{year % 100:02d}"]:
        raise ValueError(f"{path.name} tag {tag.strip()!r} does not match catalog year {year}")
    return {
        "nces_leaid": state + district,
        "school_year": year,
        "census_name": _field(line, layout.name).strip(),
        "total_population": _count(line, layout.total, path),
        "population_5_17": _count(line, layout.children, path),
        "children_5_17_in_poverty": _count(line, layout.poverty, path),
        "document_id": document["document_id"],
    }


def _field(line: str, span: tuple[int, int]) -> str:
    start, end = span
    return line[start - 1:end]


def _count(line: str, span: tuple[int, int], path: Path) -> int | None:
    token = _field(line, span).strip()
    if not token:
        return None
    if not token.isdigit():
        raise ValueError(f"{path.name} count {token!r} is not an integer")
    return int(token)
