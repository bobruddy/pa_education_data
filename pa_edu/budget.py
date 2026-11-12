"""General Fund Budget expenses: PDE workbooks to SQLite."""

from __future__ import annotations

import re

import pandas as pd

from pa_edu.common import (
    DATA_DIR,
    LOOKUP_PATH,
    absolute_url,
    cache_download,
    connect,
    fetch_hrefs,
    id_to_str,
    sheet_names,
)

BUDGET_PAGE = (
    "https://www.pa.gov/agencies/education/programs-and-services/schools/"
    "grants-and-funding/school-finances/financial-data/general-fund-budget-gfb-data"
)
RAW_DIR = DATA_DIR / "raw" / "finance_expenses"
LINK_RE = re.compile(r"(20\d{2})-(\d{2})gfbdata\.xlsx$", re.IGNORECASE)
ID_COLUMNS = ["InstCat", "AUN", "InstName", "CountyName"]


def budget_sources() -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for href in fetch_hrefs(BUDGET_PAGE):
        url = absolute_url(href)
        match = LINK_RE.search(url)
        if match is None:
            continue
        found.append((int(match.group(1)), url))
    found.sort()
    return found


def load_budget() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for school_year, url in budget_sources():
        path = cache_download(url, RAW_DIR)
        print(f"budget {school_year}: {path.name}")
        try:
            frames.append(_one_year(path, school_year))
        except Exception as error:
            print(f"  skipped {school_year}: {error}")
    if not frames:
        raise RuntimeError("no budget files were loaded")
    frame = pd.concat(frames, ignore_index=True)
    lookup = pd.read_csv(LOOKUP_PATH)
    frame = frame.merge(lookup, left_on="expense_category", right_on="raw_category", how="left")
    frame = frame.drop(columns=["raw_category", "instname", "countyname", "instcat"], errors="ignore")
    frame["school_year"] = frame["school_year"].astype(int)
    frame["expense_value"] = pd.to_numeric(frame["expense_value"], errors="coerce")
    _write_sqlite(frame)
    years = sorted(frame["school_year"].unique())
    print(f"budget rows {len(frame):,}  years {years[0]}-{years[-1]}")
    return frame


def _one_year(path, school_year: int) -> pd.DataFrame:
    sheet = _expense_sheet(path)
    engine = "openpyxl"
    frame = pd.read_excel(path, sheet_name=sheet, engine=engine)
    frame.columns = [str(column).strip() for column in frame.columns]
    missing = [column for column in ID_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"{path.name} sheet {sheet} missing {missing}")
    long = frame.melt(
        id_vars=ID_COLUMNS,
        var_name="expense_category",
        value_name="expense_value",
    )
    long["school_year"] = school_year
    long["AUN"] = id_to_str(long["AUN"])
    long.columns = [column.strip().replace(" ", "_").lower() for column in long.columns]
    return long


def _expense_sheet(path) -> str:
    available = sheet_names(path)
    for name in ("ExpDetail", "Exp"):
        if name in available:
            return name
    raise ValueError(f"no expense sheet in {available}")


def _write_sqlite(frame: pd.DataFrame) -> None:
    pickle_path = DATA_DIR / "budget_expense.pkl.bz2"
    frame.to_pickle(pickle_path, compression="infer")
    indexed = frame.set_index(["aun", "school_year", "expense_category"])
    with connect() as connection:
        indexed.to_sql("finance_expense", connection, if_exists="replace", index=True)
