"""Checks a local refine against the source workbooks. Needs the raw cache."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from pa_edu.catalog import load_checks
from pa_edu.codes import as_code, find_sheet, read_headed, read_sheet, sheet_names
from pa_edu.parse_act1 import YEAR_COLUMN
from pa_edu.common import DATA_DIR, ROOT
from pa_edu.parse_enrollment import _grade_label
from pa_edu.storage import load_index

FACT_TABLES = [
    "lea_year",
    "gfb_expenditure",
    "afr_expenditure",
    "afr_expenditure_school",
    "enrollment",
    "enrollment_gender",
    "enrollment_race",
    "assessment_result",
    "school",
    "act1_index",
    "act1_base",
    "real_estate_tax",
    "charter_adm",
    "home_education",
]
GRAIN = {
    "gfb_expenditure": ["aun", "school_year", "function_code", "object_code", "program_code"],
    "afr_expenditure": ["aun", "school_year", "fund_code", "function_code", "object_code", "program_code"],
    "afr_expenditure_school": [
        "aun", "school_number", "school_year", "fund_code", "function_code", "object_code", "program_code",
    ],
    "enrollment": ["aun", "school_number", "school_year", "grade_code"],
    "enrollment_gender": ["aun", "school_number", "school_year", "gender", "grade_code"],
    "enrollment_race": ["aun", "school_year", "race", "grade_code"],
    "assessment_result": [
        "aun", "school_year", "assessment", "subject", "grade", "student_group",
    ],
    "act1_index": ["aun", "school_year"],
    "act1_base": ["school_year"],
    "real_estate_tax": ["aun", "school_year", "county", "locality"],
    "charter_adm": ["aun", "school_year"],
    "home_education": ["aun", "school_year"],
}
MONEY = 0.01


def main() -> None:
    errors = run_checks()
    if errors:
        for error in errors:
            print(error)
        raise SystemExit(1)
    print("checks passed")


def run_checks(data_dir: Path | None = None) -> list[str]:
    data_dir = data_dir or DATA_DIR
    refined = data_dir / "refined"
    index = load_index(data_dir)
    checks = load_checks(ROOT / "sources" / "checks.toml")
    tables = {name: pd.read_parquet(refined / f"{name}.parquet") for name in ["lea", "document", *FACT_TABLES]}
    errors: list[str] = []
    errors.extend(_lea_coverage(tables, index, checks))
    errors.extend(_identity(tables))
    errors.extend(_grain(tables))
    errors.extend(_cells(tables, index, checks))
    errors.extend(_published_totals(tables, index, checks))
    errors.extend(_school_rollup(tables, checks))
    errors.extend(_enrollment(tables, index))
    return errors


def _lea_coverage(tables: dict[str, pd.DataFrame], index: dict, checks: dict) -> list[str]:
    record = _record(index, "gfb", int(checks["gfb_year"]))
    if record is None:
        return [f"no stable GFB file for {checks['gfb_year']}"]
    frame = read_sheet(Path(record["path"]), _expense_sheet(Path(record["path"])))
    auns = set(as_code(frame["AUN"], 9).dropna())
    missing = sorted(auns - set(tables["lea"]["aun"].astype(str)))
    expected = int(checks["gfb_aun_count"])
    if len(auns) != expected or missing:
        return [f"GFB {checks['gfb_year']} AUNs {len(auns)} missing from lea {missing[:8]}"]
    return []


def _identity(tables: dict[str, pd.DataFrame]) -> list[str]:
    errors = []
    leas = set(tables["lea"]["aun"].astype(str))
    documents = tables["document"].set_index("document_id")
    for name in FACT_TABLES:
        frame = tables[name]
        if frame.empty:
            continue
        if "aun" in frame.columns:
            present = frame["aun"].dropna()
            missing = sorted(set(present.astype(str)) - leas)
            if missing:
                errors.append(f"{name} AUNs missing from lea: {missing[:8]}")
            if frame["aun"].isna().any():
                errors.append(f"{name} has a null aun")
        if "document_id" not in frame.columns:
            continue
        unknown = sorted(set(frame["document_id"]) - set(documents.index))
        if unknown:
            errors.append(f"{name} document_id missing: {unknown[:4]}")
        else:
            blank = documents.loc[frame["document_id"].unique(), "source_url"].isna()
            if blank.any():
                errors.append(f"{name} document is missing source_url")
    return errors


def _grain(tables: dict[str, pd.DataFrame]) -> list[str]:
    errors = []
    for name, keys in GRAIN.items():
        frame = tables[name]
        if frame.empty:
            continue
        counts = frame.groupby(keys, dropna=False).size()
        collisions = int((counts > 1).sum())
        if collisions:
            sample = counts[counts > 1].head(3)
            errors.append(f"{name} has {collisions} duplicate keys, e.g. {sample.index.tolist()}")
    return errors


def _cells(tables: dict[str, pd.DataFrame], index: dict, checks: dict) -> list[str]:
    errors = []
    for cell in checks.get("gfb_cell", []):
        errors.extend(_gfb_cell(tables, index, cell))
    for cell in checks.get("afr_cell", []):
        errors.extend(_afr_cell(tables, index, cell))
    for cell in checks.get("enrollment_cell", []):
        errors.extend(_enrollment_cell(tables, index, cell))
    for cell in checks.get("assessment_cell", []):
        errors.extend(_assessment_cell(tables, index, cell))
    for cell in checks.get("act1_cell", []):
        errors.extend(_act1_cell(tables, index, cell))
    errors.extend(_act1_base_matches_floor(tables))
    for cell in checks.get("retax_cell", []):
        errors.extend(_retax_cell(tables, index, cell))
    for cell in checks.get("charter_adm_cell", []):
        errors.extend(_charter_adm_cell(tables, index, cell))
    for cell in checks.get("homeschool_cell", []):
        errors.extend(_homeschool_cell(tables, index, cell))
    return errors


def _gfb_cell(tables, index, cell) -> list[str]:
    record = _record(index, "gfb", int(cell["school_year"]))
    if record is None:
        return [f"no GFB file for {cell['school_year']}"]
    frame = read_sheet(Path(record["path"]), _expense_sheet(Path(record["path"])))
    frame.columns = [str(column).strip() for column in frame.columns]
    header = cell["function_code"] + "-" + cell["object_code"]
    if cell.get("program_code"):
        header = f"{header}-{cell['program_code']}"
        frame = read_sheet(Path(record["path"]), find_sheet(Path(record["path"]), "IUExp_Prog"))
        frame.columns = [str(column).strip() for column in frame.columns]
    if header not in frame.columns:
        return [f"GFB column {header} is not on {record['catalog_id']}"]
    row = frame.loc[as_code(frame["AUN"], 9) == cell["aun"]]
    if row.empty:
        return [f"GFB {cell['aun']} is not on {record['catalog_id']}"]
    source = float(row.iloc[0][header])
    fact = _match(
        tables["gfb_expenditure"],
        {
            "aun": cell["aun"],
            "school_year": int(cell["school_year"]),
            "function_code": cell["function_code"],
            "object_code": cell["object_code"],
            "program_code": cell.get("program_code") or "",
        },
    )
    if fact.empty or not _money(fact.iloc[0]["amount"], source):
        found = None if fact.empty else fact.iloc[0]["amount"]
        return [f"GFB {header} for {cell['aun']} is {found} in parquet and {source} in the workbook"]
    return []


def _afr_cell(tables, index, cell) -> list[str]:
    record = _record(index, "afr", int(cell["school_year"]))
    if record is None:
        return [f"no AFR file for {cell['school_year']}"]
    frame = read_sheet(Path(record["path"]), find_sheet(Path(record["path"]), "EXP"))
    frame["aun"] = as_code(frame["AUN"], 9)
    frame["fund"] = as_code(frame["FundCode"])
    frame["function_code"] = as_code(frame["AccountCode"])
    frame["object_code"] = as_code(frame["ObjectCode"])
    frame["program_code"] = as_code(frame["ProgramCode"]).fillna("")
    row = frame.loc[
        (frame["aun"] == cell["aun"])
        & (frame["fund"] == str(cell["fund_code"]))
        & (frame["function_code"] == cell["function_code"])
        & (frame["object_code"] == cell["object_code"])
        & (frame["program_code"] == (cell.get("program_code") or ""))
    ]
    if row.empty:
        return [f"AFR {cell['aun']} {cell['function_code']}-{cell['object_code']} is not on {record['catalog_id']}"]
    source = float(row["TotalAmount"].sum())
    fact = _match(
        tables["afr_expenditure"],
        {
            "aun": cell["aun"],
            "school_year": int(cell["school_year"]),
            "fund_code": str(cell["fund_code"]),
            "function_code": cell["function_code"],
            "object_code": cell["object_code"],
            "program_code": cell.get("program_code") or "",
        },
    )
    found = None if fact.empty else float(fact["total_amount"].sum())
    if found is None or not _money(found, source):
        return [f"AFR {cell['function_code']}-{cell['object_code']} for {cell['aun']} is {found} in parquet and {source} in EXP"]
    return []


def _assessment_cell(tables, index, cell) -> list[str]:
    assessment = cell["assessment"]
    record = _record(index, assessment, int(cell["school_year"]))
    if record is None:
        return [f"no {assessment} file for {cell['school_year']}"]
    from pa_edu.parse_assessment import parse_keystone, parse_pssa

    parser = parse_pssa if assessment == "pssa" else parse_keystone
    parsed = parser(Path(record["path"]), record)["assessment_result"]
    source = parsed.loc[
        (parsed["aun"] == cell["aun"])
        & (parsed["subject"] == cell["subject"])
        & (parsed["grade"] == cell["grade"])
        & (parsed["student_group"] == cell["student_group"])
    ]
    if source.empty:
        return [
            f"{assessment} {cell['aun']} {cell['subject']} {cell['grade']} "
            f"{cell['student_group']} is not on {record['catalog_id']}"
        ]
    fact = _match(
        tables["assessment_result"],
        {
            "aun": cell["aun"],
            "school_year": int(cell["school_year"]),
            "assessment": assessment,
            "subject": cell["subject"],
            "grade": cell["grade"],
            "student_group": cell["student_group"],
        },
    )
    source_value = source.iloc[0]["pct_proficient_and_above"]
    found = None if fact.empty else fact.iloc[0]["pct_proficient_and_above"]
    if found is None or abs(float(found) - float(source_value)) > 0.05:
        return [
            f"{assessment} {cell['subject']} grade {cell['grade']} for {cell['aun']} "
            f"is {found} in parquet and {source_value} in the workbook"
        ]
    return []


def _enrollment_cell(tables, index, cell) -> list[str]:
    record = _record(index, "enrollment", int(cell["school_year"]))
    if record is None:
        return [f"no enrollment file for {cell['school_year']}"]
    from pa_edu.parse_enrollment import _sheet_spec

    sheet, skiprows = _sheet_spec(int(cell["school_year"]))
    frame = read_headed(Path(record["path"]), find_sheet(Path(record["path"]), sheet), skiprows)
    frame = frame.rename(columns={column: _grade_label(column) for column in frame.columns})
    frame["aun"] = as_code(frame["AUN"], 9)
    frame["school_number"] = as_code(frame["School Number"])
    row = frame.loc[(frame["aun"] == cell["aun"]) & (frame["school_number"] == cell["school_number"])]
    grade = cell["grade_code"]
    if row.empty or grade not in row.columns:
        return [f"enrollment {cell['aun']} school {cell['school_number']} grade {grade} is not on {record['catalog_id']}"]
    source = int(pd.to_numeric(row.iloc[0][grade], errors="coerce"))
    fact = _match(
        tables["enrollment"],
        {
            "aun": cell["aun"],
            "school_number": cell["school_number"],
            "school_year": int(cell["school_year"]),
            "grade_code": grade,
        },
    )
    found = None if fact.empty else int(fact.iloc[0]["enrollment"])
    if found != source:
        return [f"enrollment grade {grade} for {cell['aun']} school {cell['school_number']} is {found} in parquet and {source} in the workbook"]
    return []


def _published_totals(tables, index, checks) -> list[str]:
    errors = []
    detail = _by_catalog(index, "afr-expdetail")
    objects = _by_catalog(index, "afr-majorobject")
    if detail is None or objects is None:
        return ["expenditure detail or object-level reference file is not in the raw cache"]
    expense = tables["afr_expenditure"]
    expense = expense.loc[expense["fund_code"].astype(str) == "10"].copy()
    for aun in checks["total_auns"]:
        for record in _records(index, "afr"):
            year = int(record["school_year"])
            errors.extend(_function_totals(expense, detail, aun, year))
            errors.extend(_object_totals(expense, objects, aun, year))
    return errors


def _function_totals(expense, detail, aun, year) -> list[str]:
    sheet = _year_sheet(Path(detail["path"]), year)
    if sheet is None:
        return []
    frame = read_sheet(Path(detail["path"]), sheet)
    row = frame.loc[as_code(frame["AUN"], 9) == aun]
    if row.empty:
        return [f"expenditure detail {year} has no {aun}"]
    leaf = set(expense.loc[(expense["aun"] == aun) & (expense["school_year"] == year), "function_code"].astype(str))
    errors = []
    for column in frame.columns:
        code = _trailing_code(column)
        if code is None or code not in leaf:
            continue
        source = float(pd.to_numeric(row.iloc[0][column], errors="coerce") or 0)
        found = float(
            expense.loc[
                (expense["aun"] == aun) & (expense["school_year"] == year) & (expense["function_code"] == code),
                "total_amount",
            ].sum()
        )
        if not _money(found, source):
            errors.append(f"AFR function {code} for {aun} {year} is {found} and the detail column is {source}")
    return errors


def _object_totals(expense, reference, aun, year) -> list[str]:
    sheet = _year_sheet(Path(reference["path"]), year)
    if sheet is None:
        return []
    frame = read_sheet(Path(reference["path"]), sheet)
    row = frame.loc[as_code(frame["AUN"], 9) == aun]
    if row.empty:
        return [f"object-level file {year} has no {aun}"]
    subset = expense.loc[(expense["aun"] == aun) & (expense["school_year"] == year)].copy()
    subset["major"] = subset["object_code"].map(_major_object)
    errors = []
    for column in frame.columns:
        match = re.search(r"Object\s+(\d{3})", str(column))
        if match is None:
            continue
        code = match.group(1)
        if not code.endswith("00"):
            continue
        source = float(pd.to_numeric(row.iloc[0][column], errors="coerce") or 0)
        found = float(subset.loc[subset["major"] == code, "total_amount"].sum())
        if not _money(found, source):
            errors.append(f"AFR object {code} for {aun} {year} is {found} and the object column is {source}")
    return errors


def _school_rollup(tables, checks) -> list[str]:
    school = tables["afr_expenditure_school"]
    expense = tables["afr_expenditure"]
    if school.empty:
        return ["SLFS produced no school rows"]
    keys = ["aun", "school_year", "fund_code", "function_code", "object_code", "program_code"]
    rolled = school.groupby(keys, dropna=False)["total_amount"].sum()
    leaf = expense.groupby(keys, dropna=False)["total_amount"].sum()
    compared = rolled.to_frame("school").join(leaf.rename("lea"), how="left")
    gap = (compared["school"] - compared["lea"]).abs()
    bad = compared.loc[compared["lea"].isna() | (gap > MONEY)]
    allowed = {
        (
            str(row["aun"]),
            int(row["school_year"]),
            str(row["fund_code"]),
            str(row["function_code"]),
            str(row["object_code"]),
            str(row.get("program_code") or ""),
        )
        for row in checks.get("school_rollup_gap", [])
    }
    if allowed:
        keep = [key for key in bad.index if _rollup_key(key) not in allowed]
        bad = bad.loc[keep]
    if bad.empty:
        return []
    return [f"{len(bad)} school AFR keys do not sum to EXP, e.g. {bad.head(3).index.tolist()}"]


def _rollup_key(key) -> tuple:
    aun, year, fund, function, obj, program = key
    return (str(aun), int(year), str(fund), str(function), str(obj), str(program or ""))


def _enrollment(tables, index) -> list[str]:
    from pa_edu.parse_enrollment import GRADE_LABELS, _sheet_spec

    errors = []
    enrollment = tables["enrollment"]
    for record in _records(index, "enrollment"):
        year = int(record["school_year"])
        path = Path(record["path"])
        sheet, skiprows = _sheet_spec(year)
        frame = read_headed(path, find_sheet(path, sheet), skiprows)
        frame = frame.rename(columns={column: _grade_label(column) for column in frame.columns})
        frame["aun"] = as_code(frame["AUN"], 9)
        frame["school_number"] = as_code(frame["School Number"])
        frame = frame.loc[frame["aun"].str.fullmatch(r"\d{9}", na=False)].copy()
        grades = [column for column in frame.columns if str(column).casefold() in GRADE_LABELS]
        unmapped = [
            column
            for column in frame.columns
            if str(column).casefold() not in GRADE_LABELS and _looks_like_grade(column)
        ]
        if unmapped:
            errors.append(f"enrollment {year} has unmapped columns {unmapped[:6]}")
        frame["_sum"] = frame[grades].apply(pd.to_numeric, errors="coerce").sum(axis=1) if grades else 0
        fact = enrollment.loc[enrollment["school_year"] == year]
        summed = fact.groupby(["aun", "school_number"])["enrollment"].sum()
        source = frame.groupby(["aun", "school_number"])["_sum"].sum()
        both = summed.to_frame("fact").join(source.rename("source"), how="outer")
        bad = int((both["fact"].fillna(-1) - both["source"].fillna(-1)).abs().gt(0.1).sum())
        if bad:
            errors.append(f"enrollment {year} parquet does not match the grade columns for {bad} schools")
        names = {name.casefold(): name for name in sheet_names(path)}
        lea = None
        if "lea" in names and names["lea"].casefold() == "lea":
            lea = read_headed(path, names["lea"], skiprows)
            lea = lea.rename(columns={column: _grade_label(column) for column in lea.columns})
            lea["aun"] = as_code(lea["AUN"], 9)
            lea = lea.loc[lea["aun"].str.fullmatch(r"\d{9}", na=False)].copy()
            lea_grades = [column for column in grades if column in lea.columns]
            lea_sum = lea[lea_grades].apply(pd.to_numeric, errors="coerce").sum(axis=1) if lea_grades else 0
            lea_by_aun = pd.Series(lea_sum.to_numpy(), index=lea["aun"].to_numpy()).groupby(level=0).sum()
            fact_sum = fact.groupby("aun")["enrollment"].sum()
            both = fact_sum.to_frame("fact").join(lea_by_aun.rename("source"), how="outer")
            bad = int((both["fact"].fillna(-1) - both["source"].fillna(-1)).abs().gt(0.1).sum())
            if bad:
                errors.append(f"enrollment {year} schools do not match the LEA sheet for {bad} AUNs")
        if "Total" in frame.columns and lea is not None and "Total" in lea.columns:
            frame["_gap"] = pd.to_numeric(frame["Total"], errors="coerce") - frame["_sum"]
            lea_gap = pd.to_numeric(lea["Total"], errors="coerce") - lea[lea_grades].apply(
                pd.to_numeric, errors="coerce"
            ).sum(axis=1)
            school_gap = frame.groupby("aun")["_gap"].sum()
            lea_gap = pd.Series(lea_gap.to_numpy(), index=lea["aun"].to_numpy()).groupby(level=0).sum()
            gaps = school_gap.to_frame("school").join(lea_gap.rename("lea"), how="outer")
            unexplained = int((gaps["school"].fillna(0) - gaps["lea"].fillna(0)).abs().gt(0.1).sum())
            if unexplained:
                errors.append(
                    f"enrollment {year} Total does not match the grade columns for {unexplained} AUNs"
                )
        if not tables["enrollment_gender"].empty:
            gender = tables["enrollment_gender"]
            gender = gender.loc[gender["school_year"] == year]
            if not gender.empty:
                left = fact.groupby(["aun", "school_number", "grade_code"])["enrollment"].sum()
                right = gender.groupby(["aun", "school_number", "grade_code"])["enrollment"].sum()
                both = left.to_frame("school").join(right.rename("gender"), how="outer")
                bad = int((both["school"].fillna(-1) != both["gender"].fillna(-1)).sum())
                if bad:
                    errors.append(f"enrollment {year} gender split misses {bad} grade cells")
        if (
            not tables["enrollment_race"].empty
            and "lea and race" in names
        ):
            race = tables["enrollment_race"]
            race = race.loc[race["school_year"] == year]
            if not race.empty:
                suppressed = _suppressed_race_grades(path, names["lea and race"], skiprows, grades)
                left = fact.groupby(["aun", "grade_code"])["enrollment"].sum()
                right = race.groupby(["aun", "grade_code"])["enrollment"].sum()
                both = left.to_frame("school").join(right.rename("race"), how="outer").reset_index()
                both = both.loc[~both.apply(lambda row: (row["aun"], row["grade_code"]) in suppressed, axis=1)]
                bad = int((both["school"].fillna(-1) - both["race"].fillna(-1)).abs().gt(0.1).sum())
                if bad:
                    errors.append(f"enrollment {year} race split misses {bad} LEA grade cells")
    return errors


def _looks_like_grade(column: object) -> bool:
    text = str(column).strip()
    return re.fullmatch(r"(?i)(\d{1,3}|pk[apfh]?|k4[apf]?|k5[apf]?|eug|sug|prek)", text) is not None


def _suppressed_race_grades(path: Path, sheet: str, skiprows: int, grades: list[str]) -> set[tuple[str, str]]:
    from pa_edu.parse_enrollment import _published_count

    frame = read_headed(path, sheet, skiprows)
    frame = frame.rename(columns={column: _grade_label(column) for column in frame.columns})
    frame["aun"] = as_code(frame["AUN"], 9)
    hidden: set[tuple[str, str]] = set()
    for column in grades:
        if column not in frame.columns:
            continue
        mask = frame[column].map(lambda value: _published_count(value)[1])
        for aun in frame.loc[mask, "aun"]:
            hidden.add((aun, column.lower()))
    return hidden


def _record(index: dict, parser: str, year: int) -> dict | None:
    found = [record for record in _records(index, parser) if int(record["school_year"]) == year]
    return found[0] if found else None


def _records(index: dict, parser: str) -> list[dict]:
    records = []
    for document_id in index.get("current", {}).values():
        record = index["documents"][document_id]
        if record["parser"] == parser and record["status"] == "stable":
            records.append(record)
    return records


def _by_catalog(index: dict, catalog_id: str) -> dict | None:
    document_id = index.get("current", {}).get(catalog_id)
    if document_id is None:
        return None
    return index["documents"][document_id]


def _expense_sheet(path: Path) -> str:
    try:
        return find_sheet(path, "Exp")
    except ValueError:
        return find_sheet(path, "ExpDetail")


def _year_sheet(path: Path, year: int) -> str | None:
    suffix = f"{year + 1:04d}"[-2:]
    wanted = {f"{year}-{suffix}", f"{year}-{year + 1}"}
    names = {name.casefold(): name for name in sheet_names(path)}
    for label in wanted:
        if label.casefold() in names:
            return names[label.casefold()]
    return None


def _trailing_code(label: object) -> str | None:
    parts = str(label).replace("\n", " ").split()
    if parts and re.fullmatch(r"\d{4}", parts[-1]):
        return parts[-1]
    return None


def _major_object(code: object) -> str:
    text = str(code).zfill(3)
    return text if text.endswith("00") else f"{text[0]}00"


def _act1_cell(tables: dict[str, pd.DataFrame], index: dict, cell: dict) -> list[str]:
    records = _records(index, "act1")
    if len(records) != 1:
        return [f"expected one Act 1 index file, found {len(records)}"]
    record = records[0]
    path = Path(record["path"])
    frame = read_sheet(path, sheet_names(path)[0])
    frame.columns = [str(column).strip() for column in frame.columns]
    header = _act1_year_column(frame.columns, int(cell["school_year"]))
    if header is None:
        return [f"Act 1 column for {cell['school_year']} is not on {record['catalog_id']}"]
    row = frame.loc[as_code(frame["AUN"], 9) == cell["aun"]]
    if row.empty:
        return [f"Act 1 {cell['aun']} is not on {record['catalog_id']}"]
    source = row.iloc[0][header]
    if pd.isna(source):
        return [f"Act 1 {cell['aun']} {cell['school_year']} is blank in the workbook"]
    fact = _match(
        tables["act1_index"],
        {"aun": cell["aun"], "school_year": int(cell["school_year"])},
    )
    if fact.empty or abs(float(fact.iloc[0]["adjusted_index"]) - float(source)) > 1e-6:
        found = None if fact.empty else fact.iloc[0]["adjusted_index"]
        return [f"Act 1 {cell['school_year']} for {cell['aun']} is {found} in parquet and {source} in the workbook"]
    return []


def _act1_year_column(columns, year: int) -> str | None:
    for column in columns:
        match = YEAR_COLUMN.fullmatch(str(column).strip())
        if match and int(match.group(1)) == year:
            return column
    return None


def _act1_base_matches_floor(tables: dict[str, pd.DataFrame]) -> list[str]:
    base = tables.get("act1_base")
    index = tables.get("act1_index")
    if base is None or index is None or base.empty or index.empty:
        return ["Act 1 index or base table is empty"]
    base_years = set(base["school_year"].astype(int))
    index_years = set(index["school_year"].astype(int))
    if base_years != index_years:
        return [f"Act 1 years differ: base {sorted(base_years)} index {sorted(index_years)}"]
    errors = []
    for row in base.itertuples(index=False):
        year = int(row.school_year)
        rates = index.loc[index["school_year"].astype(int) == year, "adjusted_index"]
        floor = round(float(rates.min()), 3)
        published = round(float(row.base_index), 3)
        if floor != published:
            errors.append(f"Act 1 base {year} is {published} but the lowest district index is {floor}")
    return errors


def _retax_cell(tables: dict[str, pd.DataFrame], index: dict, cell: dict) -> list[str]:
    record = _record(index, "retax", int(cell["school_year"]))
    if record is None:
        return [f"no real estate tax file for {cell['school_year']}"]
    path = Path(record["path"])
    frame = read_sheet(path, sheet_names(path)[0])
    frame.columns = [str(column).strip() for column in frame.columns]
    mills_column = _named_column(frame.columns, "real estate mills")
    if mills_column is None:
        return [f"real estate mills column is not on {record['catalog_id']}"]
    locality = str(cell.get("locality") or "")
    places = frame["Municipality / Other Info"].map(lambda value: "" if pd.isna(value) else str(value).strip())
    row = frame.loc[
        (as_code(frame["AUN"], 9) == cell["aun"])
        & (frame["Tax County"].map(lambda value: "" if pd.isna(value) else str(value).strip()) == cell["county"])
        & (places == locality)
    ]
    if row.empty:
        return [f"real estate tax {cell['aun']} {cell['county']} is not on {record['catalog_id']}"]
    source = row.iloc[0][mills_column]
    if pd.isna(source):
        return [f"real estate tax {cell['aun']} {cell['school_year']} is blank in the workbook"]
    fact = _match(
        tables["real_estate_tax"],
        {
            "aun": cell["aun"],
            "school_year": int(cell["school_year"]),
            "county": cell["county"],
            "locality": locality,
        },
    )
    if fact.empty or abs(float(fact.iloc[0]["mills"]) - float(source)) > 1e-4:
        found = None if fact.empty else fact.iloc[0]["mills"]
        return [f"real estate mills for {cell['aun']} {cell['school_year']} is {found} in parquet and {source} in the workbook"]
    return []


def _charter_adm_cell(tables: dict[str, pd.DataFrame], index: dict, cell: dict) -> list[str]:
    record = _record(index, "charter_adm", int(cell["school_year"]))
    if record is None:
        return [f"no charter ADM file for {cell['school_year']}"]
    path = Path(record["path"])
    sheet = next((name for name in sheet_names(path) if "cs adm by sd" in name.casefold()), None)
    if sheet is None:
        return [f"CS ADM by SD sheet is not on {record['catalog_id']}"]
    frame = read_sheet(path, sheet)
    frame.columns = [str(column).strip() for column in frame.columns]
    amount = _named_column(frame.columns, "charter")
    if amount is None or "adm" not in amount.casefold():
        amount = next(
            (column for column in frame.columns if "charter" in column.casefold() and "adm" in column.casefold()),
            None,
        )
    if amount is None:
        return [f"charter ADM column is not on {record['catalog_id']}"]
    row = frame.loc[as_code(frame["AUN"], 9) == cell["aun"]]
    if row.empty:
        return [f"charter ADM {cell['aun']} is not on {record['catalog_id']}"]
    source = row.iloc[0][amount]
    if pd.isna(source):
        return [f"charter ADM {cell['aun']} {cell['school_year']} is blank in the workbook"]
    fact = _match(
        tables["charter_adm"],
        {"aun": cell["aun"], "school_year": int(cell["school_year"])},
    )
    if fact.empty or abs(float(fact.iloc[0]["adm"]) - float(source)) > 0.001:
        found = None if fact.empty else fact.iloc[0]["adm"]
        return [f"charter ADM for {cell['aun']} {cell['school_year']} is {found} in parquet and {source} in the workbook"]
    return []


def _homeschool_cell(tables: dict[str, pd.DataFrame], index: dict, cell: dict) -> list[str]:
    record = _record(index, "homeschool", int(cell["school_year"]))
    if record is None:
        return [f"no home-education file for {cell['school_year']}"]
    path = Path(record["path"])
    frame = read_sheet(path, sheet_names(path)[0])
    frame.columns = [str(column).strip() for column in frame.columns]
    if "District Code" not in frame.columns or "Home Education Student Total" not in frame.columns:
        return [f"home-education columns are not on {record['catalog_id']}"]
    row = frame.loc[as_code(frame["District Code"], 9) == cell["aun"]]
    if row.empty:
        return [f"home education {cell['aun']} is not on {record['catalog_id']}"]
    source = row.iloc[0]["Home Education Student Total"]
    if pd.isna(source):
        return [f"home education {cell['aun']} {cell['school_year']} is blank in the workbook"]
    fact = _match(
        tables["home_education"],
        {"aun": cell["aun"], "school_year": int(cell["school_year"])},
    )
    if fact.empty or abs(float(fact.iloc[0]["students"]) - float(source)) > 0.001:
        found = None if fact.empty else fact.iloc[0]["students"]
        return [f"home education for {cell['aun']} {cell['school_year']} is {found} in parquet and {source} in the workbook"]
    return []


def _named_column(columns, needle: str) -> str | None:
    found = [column for column in columns if needle in str(column).casefold()]
    if len(found) != 1:
        return None
    return found[0]


def _match(frame: pd.DataFrame, keys: dict) -> pd.DataFrame:
    mask = pd.Series(True, index=frame.index)
    for column, value in keys.items():
        if column == "school_year":
            mask &= frame[column].astype(int) == int(value)
        else:
            mask &= frame[column].astype(str) == str(value)
    return frame.loc[mask]


def _money(found, source) -> bool:
    return abs(round(float(found), 2) - round(float(source), 2)) <= MONEY


if __name__ == "__main__":
    main()
