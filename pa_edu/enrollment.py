"""Public school enrollment: PDE workbooks to SQLite."""

from __future__ import annotations

import re
import urllib.parse

import pandas as pd

from pa_edu.common import (
    DATA_DIR,
    GRADE_COLUMNS,
    STRING_COLUMNS,
    absolute_url,
    cache_download,
    connect,
    fetch_hrefs,
    id_to_str,
    normalize_grade_columns,
    read_excel,
    sheet_names,
)

ENROLLMENT_PAGE = (
    "https://www.education.pa.gov/DataAndReporting/Enrollment/Pages/PublicSchEnrReports.aspx"
)
RAW_DIR = DATA_DIR / "raw" / "basic_enrollment"
LINK_RE = re.compile(
    r"/enrollment/public-school/enrollment public schools? (20\d{2})-(\d{2,4})\.xlsx?$",
    re.IGNORECASE,
)
# Years before 2007 were left out of the original notebooks. The files are
# still on the site, but LEA type and AUN were not reliable enough to load.
EARLIEST_YEAR = 2007
SHEET_BY_YEAR = {
    2010: ("School", 4),
    2009: ("School - Data File", 4),
    2008: ("School - Datafile", 4),
    2007: ("LEA - Data File", 6),
}


def enrollment_sources() -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for href in fetch_hrefs(ENROLLMENT_PAGE):
        decoded = urllib.parse.unquote(absolute_url(href))
        match = LINK_RE.search(decoded)
        if match is None:
            continue
        start = int(match.group(1))
        end_raw = match.group(2)
        end = int(end_raw) if len(end_raw) == 4 else int(str(start)[:2] + end_raw)
        if end != start + 1 or start < EARLIEST_YEAR:
            continue
        found.append((start, decoded.split("?", 1)[0]))
    found.sort()
    return found


def load_enrollment() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for school_year, url in enrollment_sources():
        path = cache_download(url, RAW_DIR)
        print(f"enrollment {school_year}: {path.name}")
        try:
            frames.append(_one_year(path, school_year))
        except Exception as error:
            print(f"  skipped {school_year}: {error}")
    if not frames:
        raise RuntimeError("no enrollment files were loaded")
    frame = pd.concat(frames, ignore_index=True)
    frame = _fill_missing_aun(frame)
    long = _melt(frame)
    _write_sqlite(long)
    years = sorted(long["school_year"].unique())
    print(f"enrollment rows {len(long):,}  years {years[0]}-{years[-1]}")
    return long


def _one_year(path, school_year: int) -> pd.DataFrame:
    sheet, skiprows = _sheet_spec(school_year, path)
    frame = normalize_grade_columns(read_excel(path, sheet, skiprows))
    if "School Number" in frame.columns:
        frame["School Number"] = frame["School Number"].map(_clean_id)
        frame = frame[frame["School Number"].str.contains(r"^\d+$", na=False)].copy()
    for column in ("County", "LEA Name", "AUN"):
        if column in frame.columns:
            frame[column] = frame[column].ffill()
    if "LEA Type" not in frame.columns and "LEA Name" in frame.columns:
        frame["LEA Type"] = (
            frame["LEA Name"].astype("string").str.extract(r"(\S+)$", expand=False)
        )
    for column in STRING_COLUMNS + GRADE_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    frame = frame[STRING_COLUMNS + GRADE_COLUMNS]
    frame = frame[~frame["LEA Name"].astype("string").str.contains(r"Total$", na=False)].copy()
    frame["school_year"] = school_year
    for column in GRADE_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["AUN"] = id_to_str(frame["AUN"])
    frame["School Number"] = id_to_str(frame["School Number"])
    for column in ("LEA Name", "LEA Type", "County", "School Name"):
        frame[column] = frame[column].astype("string").str.strip()
    return frame


def _sheet_spec(school_year: int, path) -> tuple[str, int]:
    preferred, skiprows = (
        ("LEA and School", 4) if school_year >= 2011 else SHEET_BY_YEAR[school_year]
    )
    available = sheet_names(path)
    if preferred in available:
        return preferred, skiprows
    folded = {name.casefold(): name for name in available}
    if preferred.casefold() in folded:
        return folded[preferred.casefold()], skiprows
    raise ValueError(f"sheet {preferred!r} not in {available}")


def _clean_id(value: object) -> object:
    if pd.isna(value):
        return pd.NA
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    text = str(value).strip()
    if re.fullmatch(r"\d+\.0", text):
        return text[:-2]
    return text


def _fill_missing_aun(frame: pd.DataFrame) -> pd.DataFrame:
    newest = (
        frame.sort_values("school_year", ascending=False)
        .drop_duplicates("LEA Name")
        .loc[:, ["LEA Name", "AUN"]]
        .rename(columns={"AUN": "aun_fix"})
    )
    frame = frame.merge(newest, on="LEA Name", how="left")
    missing = frame["AUN"].isna() | (frame["AUN"].astype("string").str.strip() == "")
    frame.loc[missing, "AUN"] = frame.loc[missing, "aun_fix"]
    return frame.drop(columns=["aun_fix"])


def _melt(frame: pd.DataFrame) -> pd.DataFrame:
    renamed = frame.rename(
        columns={
            "AUN": "aun",
            "LEA Name": "lea_name",
            "LEA Type": "lea_type",
            "County": "county",
            "School Number": "school_number",
            "School Name": "school_name",
        }
    )
    long = renamed.melt(
        id_vars=["aun", "lea_name", "lea_type", "county", "school_number", "school_name", "school_year"],
        value_vars=GRADE_COLUMNS,
        var_name="grade",
        value_name="enrollment",
    )
    long["grade"] = long["grade"].str.lower()
    long["enrollment"] = pd.to_numeric(long["enrollment"], errors="coerce").astype("Int64")
    long["school_year"] = long["school_year"].astype(int)
    return long


def _write_sqlite(frame: pd.DataFrame) -> None:
    pickle_path = DATA_DIR / "basic_enrollment.pkl.bz2"
    frame.to_pickle(pickle_path, compression="infer")
    with connect() as connection:
        lea_info = (
            frame.sort_values("school_year", ascending=False)
            .drop_duplicates("aun")
            .loc[:, ["aun", "lea_name", "lea_type", "county"]]
            .set_index("aun")
        )
        school_info = (
            frame.sort_values("school_year", ascending=False)
            .drop_duplicates("school_number")
            .loc[:, ["school_number", "school_name", "aun"]]
            .set_index("school_number")
        )
        basic = frame.loc[:, ["aun", "school_number", "school_year", "grade", "enrollment"]].set_index(
            ["aun", "school_number", "school_year", "grade"]
        )
        lea_totals = (
            frame.groupby(["aun", "school_year"], dropna=False)["enrollment"]
            .sum()
            .rename("enrollment")
            .reset_index()
            .set_index(["aun", "school_year"])
        )
        school_totals = (
            frame.groupby(["school_number", "school_year"], dropna=False)["enrollment"]
            .sum()
            .rename("enrollment")
            .reset_index()
            .set_index(["school_number", "school_year"])
        )
        lea_info.to_sql("lea_info", connection, if_exists="replace", index=True)
        school_info.to_sql("school_info", connection, if_exists="replace", index=True)
        basic.to_sql("basic_enrollment", connection, if_exists="replace", index=True)
        lea_totals.to_sql("lea_w_enrollment", connection, if_exists="replace", index=True)
        school_totals.to_sql("school_w_enrollment", connection, if_exists="replace", index=True)
