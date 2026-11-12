"""AFR tuition schedule: charter tuition versus special-education tuition.

The General Fund Budget rolls every purchased-service object into codes like
1100-500. Charter tuition (object 562) is in that rollup, and so is tuition
paid to approved private schools and PRRIs. The AFR tuition schedule is the
published split.
"""

from __future__ import annotations

import re

import pandas as pd

from pa_edu.common import DATA_DIR, absolute_url, cache_download, connect, id_to_str

TUITION_URL = absolute_url(
    "/content/dam/copapwp-pagov/en/education/documents/schools/grants-and-funding/"
    "school-finances/summary-of-afr-data/afr-data-detailed/"
    "finances%20afr%20tuitionsched%201516-2425.xlsx"
)
RAW_DIR = DATA_DIR / "raw" / "finance_expenses"
SHEET_YEAR = re.compile(r"^(20\d{2})-(\d{2})$")


def load_tuition() -> pd.DataFrame:
    path = cache_download(TUITION_URL, RAW_DIR)
    print(f"tuition schedule: {path.name}")
    sheets = pd.ExcelFile(path).sheet_names
    frames = [_one_sheet(path, sheet) for sheet in sheets if SHEET_YEAR.match(sheet)]
    if not frames:
        raise RuntimeError(f"no tuition sheets in {path}")
    frame = pd.concat(frames, ignore_index=True)
    _write_sqlite(frame)
    years = sorted(frame["school_year"].unique())
    print(f"tuition rows {len(frame):,}  years {years[0]}-{years[-1]}")
    return frame


def _one_sheet(path, sheet: str) -> pd.DataFrame:
    school_year = int(SHEET_YEAR.match(sheet).group(1))
    raw = pd.read_excel(path, sheet_name=sheet)
    raw = raw.loc[:, [column for column in raw.columns if not str(column).startswith("Unnamed")]]
    raw.columns = [_norm(column) for column in raw.columns]
    aun_column = next(column for column in raw.columns if column == "aun")
    frame = pd.DataFrame({"aun": id_to_str(raw[aun_column]), "school_year": school_year})
    frame["charter_nonspecial"] = _sum_matching(raw, lambda name: "charter" in name and "nonspecial" in name)
    frame["charter_special"] = _sum_matching(
        raw, lambda name: "charter" in name and "special" in name and "nonspecial" not in name
    )
    frame["sped_aps"] = _sum_matching(raw, lambda name: "approved private" in name)
    frame["sped_prri"] = _sum_matching(raw, lambda name: "prri" in name)
    frame = frame.dropna(subset=["aun"])
    for column in ("charter_nonspecial", "charter_special", "sped_aps", "sped_prri"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    return frame


def _sum_matching(raw: pd.DataFrame, predicate) -> pd.Series:
    columns = [column for column in raw.columns if predicate(column)]
    if not columns:
        return pd.Series(0.0, index=raw.index)
    return raw[columns].apply(pd.to_numeric, errors="coerce").fillna(0.0).sum(axis=1)


def _norm(value: object) -> str:
    return re.sub(r"\s+", " ", str(value).replace("\n", " ")).strip().lower()


def _write_sqlite(frame: pd.DataFrame) -> None:
    indexed = frame.set_index(["aun", "school_year"])
    with connect() as connection:
        indexed.to_sql("tuition_paid", connection, if_exists="replace", index=True)


if __name__ == "__main__":
    load_tuition()
