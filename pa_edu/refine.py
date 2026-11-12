"""Download cataloged PDE files and write the refined Parquet tables."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from pa_edu.catalog import load_catalog
from pa_edu.codes import empty_frame
from pa_edu.common import DATA_DIR, ROOT
from pa_edu.parse_act1 import parse_act1, parse_act1_base
from pa_edu.parse_afr import parse_afr
from pa_edu.parse_assessment import parse_keystone, parse_pssa
from pa_edu.parse_chart import parse_chart
from pa_edu.parse_charter_adm import parse_charter_adm
from pa_edu.parse_cohort_grad import parse_cohort_grad
from pa_edu.parse_edna import parse_edna
from pa_edu.parse_enrollment import grade_table, parse_enrollment
from pa_edu.parse_gfb import parse_gfb
from pa_edu.parse_homeschool import parse_homeschool
from pa_edu.parse_iep import parse_iep
from pa_edu.parse_low_income import parse_low_income
from pa_edu.parse_retax import parse_retax
from pa_edu.storage import load_index, materialize

PARSERS = {
    "gfb": parse_gfb,
    "afr": parse_afr,
    "enrollment": parse_enrollment,
    "edna": parse_edna,
    "chart": parse_chart,
    "pssa": parse_pssa,
    "keystone": parse_keystone,
    "act1": parse_act1,
    "act1_base": parse_act1_base,
    "retax": parse_retax,
    "charter_adm": parse_charter_adm,
    "homeschool": parse_homeschool,
    "low_income": parse_low_income,
    "iep": parse_iep,
    "cohort_grad": parse_cohort_grad,
}

COLUMNS = {
    "document": [
        "document_id", "catalog_id", "source_id", "source_url", "page_url",
        "sha256", "retrieved_at", "school_year", "parser",
    ],
    "lea": [
        "aun", "lea_name", "category", "status", "county", "iu_aun",
        "in_directory", "document_id",
    ],
    "lea_year": ["aun", "school_year", "lea_name", "county", "inst_cat", "document_id"],
    "gfb_expenditure": [
        "aun", "school_year", "function_code", "object_code", "program_code",
        "amount", "fund_code", "document_id",
    ],
    "afr_expenditure": [
        "aun", "school_year", "fund_code", "function_code", "object_code", "program_code",
        "rollup_fund_code", "rollup1_account_code", "rollup2_account_code", "rollup3_account_code",
        "rollup1_object_code", "rollup2_object_code",
        "elementary_amount", "secondary_amount", "federal_amount", "total_amount", "document_id",
    ],
    "enrollment": [
        "aun", "school_number", "school_name", "school_year", "grade_code", "enrollment",
        "lea_name", "lea_type", "county", "document_id",
    ],
    "enrollment_gender": [
        "aun", "school_number", "school_name", "school_year", "gender", "grade_code",
        "enrollment", "lea_name", "lea_type", "county", "document_id",
    ],
    "enrollment_race": [
        "aun", "school_year", "race", "grade_code", "enrollment",
        "lea_name", "lea_type", "county", "document_id",
    ],
    "enrollment_low_income": [
        "aun", "school_year", "lea_name", "lea_type",
        "low_income_enrollment", "total_enrollment", "pct_low_income", "document_id",
    ],
    "enrollment_iep": [
        "aun", "school_year", "lea_name",
        "iep_enrollment", "total_enrollment", "pct_iep", "document_id",
    ],
    "assessment_result": [
        "aun", "school_year", "assessment", "subject", "grade", "student_group",
        "number_scored", "pct_advanced", "pct_proficient", "pct_basic",
        "pct_below_basic", "pct_proficient_and_above",
        "lea_name", "county", "document_id",
    ],
    "act1_index": [
        "aun", "school_year", "lea_name", "county", "adjusted_index", "document_id",
    ],
    "act1_base": [
        "school_year", "base_index", "saww_increase", "eci_increase", "document_id",
    ],
    "real_estate_tax": [
        "aun", "school_year", "county", "locality", "mills", "college_mills", "document_id",
    ],
    "charter_adm": [
        "aun", "school_year", "lea_name", "county", "adm", "document_id",
    ],
    "home_education": [
        "aun", "school_year", "lea_name", "county", "students",
        "private_tutor", "age_5_11", "age_12_plus", "document_id",
    ],
    "cohort_graduation": [
        "aun", "school_year", "span", "lea_name", "lea_type",
        "graduates", "cohort", "rate", "document_id",
    ],
    "cohort_graduation_group": [
        "aun", "school_year", "span", "student_group", "rate", "document_id",
    ],
    "school": ["aun", "school_number", "school_name"],
    "grade": ["grade_code", "label", "band", "session"],
    "account": [
        "function_code", "object_code", "function_name", "object_name",
        "major_function", "major_object",
    ],
}
COLUMNS["afr_expenditure_school"] = [
    "aun", "school_number", "school_name", *COLUMNS["afr_expenditure"][1:],
]

SORT = {
    "document": ["document_id"],
    "lea": ["aun"],
    "lea_year": ["school_year", "aun", "document_id"],
    "gfb_expenditure": ["school_year", "aun", "function_code", "object_code", "program_code"],
    "afr_expenditure": ["school_year", "aun", "fund_code", "function_code", "object_code", "program_code"],
    "afr_expenditure_school": [
        "school_year", "aun", "school_number", "fund_code", "function_code", "object_code", "program_code",
    ],
    "enrollment": ["school_year", "aun", "school_number", "grade_code"],
    "enrollment_gender": ["school_year", "aun", "school_number", "gender", "grade_code"],
    "enrollment_race": ["school_year", "aun", "race", "grade_code"],
    "enrollment_low_income": ["school_year", "aun"],
    "enrollment_iep": ["school_year", "aun"],
    "assessment_result": [
        "school_year", "assessment", "aun", "subject", "grade", "student_group",
    ],
    "act1_index": ["school_year", "aun"],
    "act1_base": ["school_year"],
    "real_estate_tax": ["school_year", "aun", "county", "locality"],
    "charter_adm": ["school_year", "aun"],
    "home_education": ["school_year", "aun"],
    "cohort_graduation": ["school_year", "span", "aun"],
    "cohort_graduation_group": ["school_year", "span", "aun", "student_group"],
    "school": ["aun", "school_number"],
    "grade": ["grade_code"],
    "account": ["function_code", "object_code"],
}

INST_CATEGORY = {
    "01": "school_district",
    "02": "intermediate_unit",
    "03": "career_and_technical_center",
    "04": "charter_school",
    "06": "jointure",
}
ENROLLMENT_CATEGORY = {
    "sd": "school_district",
    "cs": "charter_school",
    "cyber cs": "charter_school",
    "iu": "intermediate_unit",
    "occctc": "career_and_technical_center",
    "comctc": "career_and_technical_center",
    "sjci": "state_juvenile_correctional",
    "spj": "jointure",
}


def main() -> None:
    run()


def run(data_dir: Path | None = None, catalog_path: Path | None = None) -> Path:
    data_dir = data_dir or DATA_DIR
    catalog_path = catalog_path or ROOT / "sources" / "catalog.toml"
    entries = load_catalog(catalog_path)
    index = load_index(data_dir)
    collected: dict[str, list[pd.DataFrame]] = {name: [] for name in COLUMNS if name != "document"}
    functions: dict[str, str] = {}
    objects: dict[str, str] = {}
    for entry in entries:
        record = materialize(entry, data_dir, index)
        print(f"{entry.status:6} {entry.id}: {Path(record['path']).name}")
        if entry.status != "stable":
            continue
        parser = PARSERS.get(entry.parser)
        if parser is None:
            raise RuntimeError(f"{entry.id} has no parser {entry.parser!r}")
        try:
            parsed = parser(Path(record["path"]), record)
        except Exception as error:
            raise RuntimeError(f"{entry.id} failed: {error}") from error
        if entry.parser == "chart":
            functions = dict(zip(parsed["function"]["function_code"], parsed["function"]["name"], strict=True))
            objects = dict(zip(parsed["object"]["object_code"], parsed["object"]["name"], strict=True))
            print(f"         chart titles: {len(functions)} functions, {len(objects)} objects")
            continue
        for table, frame in parsed.items():
            if frame is None or frame.empty:
                continue
            collected[table].append(frame)
    frames = {name: _concat(parts, COLUMNS[name]) for name, parts in collected.items()}
    frames["lea"] = _lea(
        frames["lea"],
        frames["lea_year"],
        frames["enrollment"],
        frames["assessment_result"],
        frames["enrollment_iep"],
        frames["enrollment_low_income"],
        frames["cohort_graduation"],
    )
    frames["school"] = _school(frames["enrollment"])
    frames["grade"] = grade_table()
    frames["account"] = _account(frames, functions, objects)
    frames["document"] = _documents(index)
    refined = data_dir / "refined"
    refined.mkdir(parents=True, exist_ok=True)
    for name, frame in frames.items():
        frame = _align(frame, COLUMNS[name], SORT[name])
        frame.to_parquet(refined / f"{name}.parquet", index=False)
        print(f"wrote {name} {len(frame):,}")
    _duckdb(data_dir / "pde.duckdb", refined)
    print(f"wrote {data_dir / 'pde.duckdb'}")
    return refined


def _concat(parts: list[pd.DataFrame], columns: list[str]) -> pd.DataFrame:
    if not parts:
        return empty_frame(columns)
    return pd.concat(parts, ignore_index=True)


def _lea(
    directory: pd.DataFrame,
    finance: pd.DataFrame,
    enrollment: pd.DataFrame,
    assessment: pd.DataFrame | None = None,
    *extras: pd.DataFrame,
) -> pd.DataFrame:
    base = directory.copy() if not directory.empty else empty_frame(COLUMNS["lea"])
    known = set(base["aun"].dropna().astype(str)) if "aun" in base.columns else set()
    candidates = []
    if not finance.empty:
        finance = finance.copy()
        finance["category"] = finance["inst_cat"].map(INST_CATEGORY)
        finance["rank"] = 0
        candidates.append(finance)
    if not enrollment.empty:
        enroll = enrollment.loc[:, ["aun", "school_year", "lea_name", "county", "lea_type", "document_id"]].copy()
        enroll["category"] = enroll["lea_type"].map(lambda value: ENROLLMENT_CATEGORY.get(str(value).casefold(), pd.NA))
        enroll["rank"] = 1
        candidates.append(enroll)
    if assessment is not None and not assessment.empty:
        assess = assessment.loc[:, ["aun", "school_year", "lea_name", "county", "document_id"]].copy()
        assess["category"] = "unknown"
        assess["rank"] = 2
        candidates.append(assess)
    for rank, extra in enumerate(extras, start=3):
        if extra is None or extra.empty or "aun" not in extra.columns:
            continue
        cols = ["aun", "school_year", "document_id"]
        if "lea_name" in extra.columns:
            cols.insert(2, "lea_name")
        work = extra.loc[:, [column for column in cols if column in extra.columns]].copy()
        if "lea_name" not in work.columns:
            work["lea_name"] = pd.NA
        work["county"] = pd.NA
        work["category"] = "unknown"
        work["rank"] = rank
        candidates.append(work)
    if not candidates:
        return base
    extra = pd.concat(candidates, ignore_index=True)
    extra = extra.loc[~extra["aun"].isin(known) & extra["aun"].notna()].copy()
    if extra.empty:
        return base
    extra = extra.sort_values(["school_year", "rank"], ascending=[False, True])
    extra = extra.drop_duplicates("aun", keep="first")
    added = pd.DataFrame(
        {
            "aun": extra["aun"],
            "lea_name": extra["lea_name"],
            "category": extra["category"].fillna("unknown"),
            "status": "unknown",
            "county": extra["county"],
            "iu_aun": pd.NA,
            "in_directory": False,
            "document_id": extra["document_id"],
        }
    )
    return pd.concat([base, added], ignore_index=True)


def _school(enrollment: pd.DataFrame) -> pd.DataFrame:
    if enrollment.empty:
        return empty_frame(COLUMNS["school"])
    frame = enrollment.dropna(subset=["aun", "school_number"]).sort_values(["school_year", "school_name"])
    latest = frame.groupby(["aun", "school_number"], as_index=False).tail(1)
    return latest.loc[:, ["aun", "school_number", "school_name"]]


def _account(frames: dict[str, pd.DataFrame], functions: dict[str, str], objects: dict[str, str]) -> pd.DataFrame:
    pairs = []
    for name in ("gfb_expenditure", "afr_expenditure", "afr_expenditure_school"):
        frame = frames[name]
        if frame.empty:
            continue
        pairs.append(frame.loc[:, ["function_code", "object_code"]])
    if not pairs:
        return empty_frame(COLUMNS["account"])
    account = pd.concat(pairs, ignore_index=True).drop_duplicates()
    account["function_name"] = account["function_code"].map(functions)
    account["object_name"] = account["object_code"].map(objects)
    account["major_function"] = account["function_code"].map(lambda code: functions.get(_major_function(code)))
    account["major_object"] = account["object_code"].map(lambda code: objects.get(_major_object(code)))
    return account


def _major_function(code: object) -> str:
    text = str(code)
    return text if text.endswith("000") else f"{text[0]}000"


def _major_object(code: object) -> str:
    text = str(code).zfill(3)
    return text if text.endswith("00") else f"{text[0]}00"


def _documents(index: dict) -> pd.DataFrame:
    rows = []
    for record in index["documents"].values():
        rows.append({column: record.get(column) for column in COLUMNS["document"]})
    if not rows:
        return empty_frame(COLUMNS["document"])
    return pd.DataFrame(rows)


def _align(frame: pd.DataFrame, columns: list[str], sort: list[str]) -> pd.DataFrame:
    for column in columns:
        if column not in frame.columns:
            frame[column] = pd.NA
    frame = frame.loc[:, columns]
    if frame.empty:
        return frame
    return frame.sort_values(sort, kind="mergesort").reset_index(drop=True)


def _duckdb(database: Path, refined: Path) -> None:
    sql = (ROOT / "sql" / "model.sql").read_text()
    sql = sql.replace("data/refined", refined.as_posix())
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(database))
    try:
        connection.execute(sql)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
