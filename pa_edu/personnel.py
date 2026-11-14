"""Professional personnel salaries, one consistent schema for every school year.

Downloads the individual-staff workbooks from PDE and writes two Parquet tables
under data/refined/:

- professional_assignment: one row per person, LEA, year, and assignment.
  Annual salary is the person's total at that LEA and is repeated on every
  assignment. Do not sum it on this table.
- professional_staff: one row per person, LEA, and year, so salary can be
  summed. The row is the primary assignment when PDE published that flag,
  otherwise the assignment with the highest FTE. `row_rule` says which.

`source_file` is the workbook name in data/raw/personnel/. Run:
python -m pa_edu.personnel
"""

from __future__ import annotations

import re
import tempfile
import urllib.parse
from pathlib import Path

import duckdb
import pandas as pd

from pa_edu.common import DATA_DIR, absolute_url, cache_download, fetch_hrefs
from pa_edu.personnel_layouts import CANONICAL_FIELDS, LAYOUTS, LEA_TYPE_CODES, YEAR_LAYOUT
from pa_edu.refine import COLUMNS, PERSONNEL_TABLES, SORT, _duckdb

PERSONNEL_PAGE = (
    "https://www.pa.gov/agencies/education/data-and-reporting/school-staff/"
    "professional-and-support-personnel"
)
FILE_RE = re.compile(
    r"(20\d{2})-(\d{2}).*professional personnel individual staff.*\.xlsx$",
    re.IGNORECASE,
)

STRING_COLUMNS = (
    "public_id",
    "last_name",
    "first_name",
    "middle_name",
    "suffix",
    "gender",
    "race",
    "degree_code",
    "degree_description",
    "status",
    "aun",
    "lea_name",
    "lea_type",
    "lea_type_code",
    "county_code",
    "county",
    "school_number",
    "school_name",
    "iu_code",
    "iu_name",
    "time_status",
    "job_class",
    "assignment_code",
    "assignment_description",
    "position_code",
    "position_description",
    "edf_code",
    "edf_category",
    "category_description",
    "source_layout",
    "source_file",
)
FLOAT_COLUMNS = ("annual_salary", "years_in_education", "years_in_lea", "fte_percent")


def personnel_sources() -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for href in fetch_hrefs(PERSONNEL_PAGE):
        decoded = urllib.parse.unquote(absolute_url(href))
        name = decoded.rsplit("/", 1)[-1]
        lowered = name.lower()
        if "/individual/" not in decoded.lower():
            continue
        if "notes" in lowered or "mapping" in lowered:
            continue
        match = FILE_RE.search(name)
        if match is None:
            continue
        found.append((int(match.group(1)), decoded.split("?", 1)[0]))
    found = sorted(set(found))
    missing = [year for year, _url in found if year not in YEAR_LAYOUT]
    if missing:
        raise RuntimeError(
            "PDE published staff years with no layout registered: "
            + ", ".join(str(year) for year in missing)
            + ". Add them to pa_edu/personnel_layouts.py."
        )
    return found


def load_personnel(data_dir: Path | None = None) -> None:
    data_dir = data_dir or DATA_DIR
    sources = personnel_sources()
    if not sources:
        raise RuntimeError("PDE personnel page has no individual-staff workbooks")
    refined = data_dir / "refined"
    refined.mkdir(parents=True, exist_ok=True)
    raw_dir = data_dir / "raw" / "personnel"
    with tempfile.TemporaryDirectory(prefix="personnel-") as tmp_name:
        tmp = Path(tmp_name)
        for index, (school_year, url) in enumerate(sources):
            path = cache_download(url, raw_dir)
            print(f"personnel {school_year}: {path.name} ({YEAR_LAYOUT[school_year]})")
            frame = pd.read_excel(path, engine="openpyxl")
            assignments = normalize_assignments(frame, school_year, path.name)
            staff = staff_rows(assignments)
            _cast(assignments, COLUMNS["professional_assignment"]).to_parquet(
                tmp / f"assignment-{index:02d}.parquet", index=False
            )
            _cast(staff, COLUMNS["professional_staff"]).to_parquet(
                tmp / f"staff-{index:02d}.parquet", index=False
            )
            primary = int(assignments["primary_assignment"].fillna(False).sum())
            blank_primary = int(assignments["primary_assignment"].isna().sum())
            print(
                f"  assignments {len(assignments):,}  staff {len(staff):,}  "
                f"primary_yes {primary:,}  primary_blank {blank_primary:,}"
            )
        for name in PERSONNEL_TABLES:
            prefix = "assignment" if name == "professional_assignment" else "staff"
            _combine(tmp, f"{prefix}-*.parquet", refined / f"{name}.parquet", SORT[name])
    _refresh_views(data_dir)
    print(f"wrote professional_assignment and professional_staff for {len(sources)} years")


def write_personnel_tables(
    assignments: list[pd.DataFrame],
    staff: list[pd.DataFrame],
    refined: Path,
) -> None:
    """Write one Parquet file per table from yearly frames. Used by tests."""
    if len(assignments) != len(staff) or not assignments:
        raise ValueError("assignments and staff must be paired, non-empty year lists")
    refined.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="personnel-") as tmp_name:
        tmp = Path(tmp_name)
        for index, (assignment_year, staff_year) in enumerate(zip(assignments, staff, strict=True)):
            _cast(assignment_year, COLUMNS["professional_assignment"]).to_parquet(
                tmp / f"assignment-{index:02d}.parquet", index=False
            )
            _cast(staff_year, COLUMNS["professional_staff"]).to_parquet(
                tmp / f"staff-{index:02d}.parquet", index=False
            )
        for name in PERSONNEL_TABLES:
            prefix = "assignment" if name == "professional_assignment" else "staff"
            _combine(tmp, f"{prefix}-*.parquet", refined / f"{name}.parquet", SORT[name])


def normalize_assignments(frame: pd.DataFrame, school_year: int, source_file: str) -> pd.DataFrame:
    layout_name = YEAR_LAYOUT[school_year]
    renamed = _rename(frame, layout_name, school_year)
    renamed["school_year"] = _school_year(renamed.pop("school_year_label"), school_year)
    renamed["snapshot_date"] = pd.to_datetime(renamed["snapshot_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    renamed["annual_salary"] = pd.to_numeric(renamed["annual_salary"], errors="coerce")
    renamed["years_in_education"] = pd.to_numeric(renamed["years_in_education"], errors="coerce")
    renamed["years_in_lea"] = pd.to_numeric(renamed["years_in_lea"], errors="coerce")
    renamed["fte_percent"] = pd.to_numeric(renamed["fte_percent"], errors="coerce")
    renamed["primary_assignment"] = _primary_flag(renamed["primary_assignment"])
    for column in STRING_COLUMNS:
        if column in ("source_layout", "source_file", "lea_type_code"):
            continue
        renamed[column] = renamed[column].map(_text)
    renamed["lea_type_code"] = renamed["lea_type"].map(_lea_type_code)
    renamed["time_status"] = renamed["time_status"].str.lower()
    renamed["source_layout"] = layout_name
    renamed["source_file"] = source_file
    unknown = sorted(set(renamed.loc[renamed["lea_type"].notna() & renamed["lea_type_code"].isna(), "lea_type"]))
    if unknown:
        print(f"  lea types without a short code: {unknown}")
    return renamed.loc[:, list(COLUMNS["professional_assignment"])]


def staff_rows(assignments: pd.DataFrame) -> pd.DataFrame:
    """One salary per person per LEA per year."""
    frame = assignments.copy()
    counts = frame.groupby(["public_id", "aun", "school_year"], dropna=False).size().rename("assignment_count")
    frame["_is_primary"] = frame["primary_assignment"].fillna(False).astype(bool)
    frame["_fte"] = frame["fte_percent"].fillna(-1)
    frame = frame.sort_values(
        ["public_id", "aun", "school_year", "_is_primary", "_fte", "assignment_code"],
        ascending=[True, True, True, False, False, True],
        kind="mergesort",
    )
    chosen = frame.drop_duplicates(["public_id", "aun", "school_year"], keep="first").copy()
    chosen["row_rule"] = chosen["_is_primary"].map({True: "primary_assignment", False: "highest_fte"})
    chosen = chosen.drop(columns=["_is_primary", "_fte"])
    chosen = chosen.join(counts, on=["public_id", "aun", "school_year"])
    return chosen


def _rename(frame: pd.DataFrame, layout_name: str, school_year: int) -> pd.DataFrame:
    mapping = LAYOUTS[layout_name]
    normalized = {_header(column): column for column in frame.columns}
    if len(normalized) != len(frame.columns):
        raise ValueError(f"{school_year} has duplicate headers after whitespace cleanup")
    missing = sorted(set(mapping) - set(normalized))
    extra = sorted(set(normalized) - set(mapping))
    if missing or extra:
        raise ValueError(
            f"{school_year} headers do not match layout {layout_name}. "
            f"missing={missing} extra={extra}"
        )
    renamed = frame.rename(columns={normalized[source]: target for source, target in mapping.items()})
    return renamed.loc[:, list(CANONICAL_FIELDS)]


def _school_year(labels: pd.Series, expected: int) -> pd.Series:
    text = labels.map(_text)
    parsed = text.str.slice(0, 4)
    bad = parsed.isna() | ~parsed.str.fullmatch(r"20\d{2}") | (parsed.astype("Int64") != expected)
    if bad.any():
        samples = text[bad].dropna().unique()[:5].tolist()
        raise ValueError(f"{expected} file contains other school-year labels: {samples}")
    return parsed.astype(int)


def _primary_flag(values: pd.Series) -> pd.Series:
    text = values.map(_text).str.lower()
    flag = pd.Series(pd.NA, index=values.index, dtype="boolean")
    flag[text.isin(["yes", "y"])] = True
    flag[text.isin(["no", "n"])] = False
    return flag


def _lea_type_code(value: object) -> object:
    if pd.isna(value):
        return pd.NA
    return LEA_TYPE_CODES.get(str(value).lower(), pd.NA)


def _header(value: object) -> str:
    return re.sub(r"\s+", " ", str(value).replace("\n", " ")).strip()


def _text(value: object) -> object:
    if pd.isna(value):
        return pd.NA
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    text = re.sub(r"\s+", " ", str(value)).strip()
    if text == "" or text.lower() == "nan":
        return pd.NA
    if re.fullmatch(r"-?\d+\.0", text):
        return text[:-2]
    return text


def _cast(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = frame.copy()
    for column in columns:
        if column not in out.columns:
            out[column] = pd.NA
    out = out.loc[:, columns]
    for column in columns:
        if column in ("school_year", "assignment_count"):
            values = pd.to_numeric(out[column], errors="coerce")
            if values.isna().any():
                raise ValueError(f"{column} has a missing value")
            out[column] = values.astype("int64")
        elif column == "primary_assignment":
            out[column] = out[column].astype("boolean")
        elif column in FLOAT_COLUMNS:
            out[column] = pd.to_numeric(out[column], errors="coerce")
        else:
            out[column] = out[column].astype("string")
    return out


def _combine(directory: Path, pattern: str, dest: Path, sort: list[str]) -> None:
    files = sorted(directory.glob(pattern))
    if not files:
        raise RuntimeError(f"no rows to write for {dest.name}")
    listed = ", ".join(_quote(path.as_posix()) for path in files)
    order = ", ".join(sort)
    connection = duckdb.connect()
    try:
        connection.execute(
            f"""
            COPY (
                SELECT * FROM read_parquet([{listed}], union_by_name = true)
                ORDER BY {order}
            ) TO {_quote(dest.as_posix())} (FORMAT PARQUET)
            """
        )
        count = connection.execute(
            f"SELECT count(*) FROM read_parquet({_quote(dest.as_posix())})"
        ).fetchone()
    finally:
        connection.close()
    print(f"wrote {dest.name} {int(count[0]):,}")


def _refresh_views(data_dir: Path) -> None:
    refined = data_dir / "refined"
    missing = [name for name in COLUMNS if not (refined / f"{name}.parquet").exists()]
    if missing:
        print("parquet written; duckdb views left in place (refined tables still missing)")
        return
    database = data_dir / "pde.duckdb"
    try:
        _duckdb(database, refined)
    except duckdb.IOException as error:
        print(f"parquet written; could not refresh {database}: {error}")
        return
    print(f"wrote {database}")


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


if __name__ == "__main__":
    load_personnel()
