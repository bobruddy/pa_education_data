"""Checks a local refine against the source workbooks. Needs the raw cache."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from pa_edu.catalog import load_checks
from pa_edu.codes import as_code, as_text, find_sheet, read_headed, read_sheet, sheet_names
from pa_edu.parse_act1 import YEAR_COLUMN
from pa_edu.common import DATA_DIR, ROOT
from pa_edu.status import public_error, record_run
from pa_edu.parse_enrollment import _grade_label
from pa_edu.storage import load_index

FACT_TABLES = [
    "lea_year",
    "gfb_expenditure",
    "afr_expenditure",
    "afr_expenditure_school",
    "afr_revenue",
    "gfb_revenue",
    "enrollment",
    "enrollment_gender",
    "enrollment_race",
    "enrollment_low_income",
    "enrollment_iep",
    "assessment_result",
    "assessment_result_school",
    "school",
    "act1_index",
    "act1_base",
    "real_estate_tax",
    "charter_adm",
    "home_education",
    "cohort_graduation",
    "cohort_graduation_group",
    "district_population",
]
GRAIN = {
    "gfb_expenditure": ["aun", "school_year", "function_code", "object_code", "program_code"],
    "afr_expenditure": ["aun", "school_year", "fund_code", "function_code", "object_code", "program_code"],
    "afr_expenditure_school": [
        "aun", "school_number", "school_year", "fund_code", "function_code", "object_code", "program_code",
    ],
    "afr_revenue": ["aun", "school_year", "fund_code", "account_code", "program_code"],
    "gfb_revenue": ["aun", "school_year", "account_code"],
    "enrollment": ["aun", "school_number", "school_year", "grade_code"],
    "enrollment_gender": ["aun", "school_number", "school_year", "gender", "grade_code"],
    "enrollment_race": ["aun", "school_year", "race", "grade_code"],
    "enrollment_low_income": ["aun", "school_year"],
    "enrollment_iep": ["aun", "school_year"],
    "assessment_result": [
        "aun", "school_year", "assessment", "subject", "grade", "student_group",
    ],
    "assessment_result_school": [
        "aun", "school_number", "school_year", "assessment", "subject", "grade", "student_group",
    ],
    "act1_index": ["aun", "school_year"],
    "act1_base": ["school_year"],
    "real_estate_tax": ["aun", "school_year", "county", "locality"],
    "charter_adm": ["aun", "school_year"],
    "home_education": ["aun", "school_year"],
    "cohort_graduation": ["aun", "school_year", "span"],
    "cohort_graduation_group": ["aun", "school_year", "span", "student_group"],
    "district_population": ["aun", "school_year"],
}
MONEY = 0.01


def main() -> None:
    try:
        errors = run_checks()
    except Exception as exc:
        record_run("check", ok=False, error=public_error(exc))
        raise
    record_run("check", ok=not errors, errors=errors)
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
    tables = {
        name: pd.read_parquet(refined / f"{name}.parquet")
        for name in ["lea", "document", "revenue_account", "chart_description", *FACT_TABLES]
    }
    errors: list[str] = []
    errors.extend(_lea_coverage(tables, index, checks))
    errors.extend(_identity(tables))
    errors.extend(_grain(tables))
    errors.extend(_cells(tables, index, checks))
    errors.extend(_population_districts(tables))
    errors.extend(_saipe_counts(tables, index))
    errors.extend(_revenue_title(tables))
    errors.extend(_chart_descriptions(tables))
    errors.extend(_revenue_not_doubled(tables))
    errors.extend(_published_totals(tables, index, checks))
    errors.extend(_school_rollup(tables, checks))
    errors.extend(_enrollment(tables, index))
    errors.extend(_assessment_school_lea(tables))
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
    for cell in checks.get("afr_revenue_cell", []):
        errors.extend(_afr_revenue_cell(tables, index, cell))
    for cell in checks.get("gfb_revenue_cell", []):
        errors.extend(_gfb_revenue_cell(tables, index, cell))
    for cell in checks.get("enrollment_cell", []):
        errors.extend(_enrollment_cell(tables, index, cell))
    for cell in checks.get("assessment_cell", []):
        errors.extend(_assessment_cell(tables, index, cell))
    for cell in checks.get("assessment_school_cell", []):
        errors.extend(_assessment_school_cell(tables, index, cell))
    for cell in checks.get("act1_cell", []):
        errors.extend(_act1_cell(tables, index, cell))
    errors.extend(_act1_base_matches_floor(tables))
    for cell in checks.get("retax_cell", []):
        errors.extend(_retax_cell(tables, index, cell))
    for cell in checks.get("charter_adm_cell", []):
        errors.extend(_charter_adm_cell(tables, index, cell))
    for cell in checks.get("homeschool_cell", []):
        errors.extend(_homeschool_cell(tables, index, cell))
    for cell in checks.get("low_income_cell", []):
        errors.extend(_low_income_cell(tables, index, cell))
    for cell in checks.get("iep_cell", []):
        errors.extend(_iep_cell(tables, index, cell))
    for cell in checks.get("cohort_grad_cell", []):
        errors.extend(_cohort_grad_cell(tables, index, cell))
    for cell in checks.get("saipe_cell", []):
        errors.extend(_saipe_cell(tables, index, cell))
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


def _afr_revenue_cell(tables, index, cell) -> list[str]:
    from pa_edu.parse_afr import reported_revenue

    record = _record(index, "afr", int(cell["school_year"]))
    if record is None:
        return [f"no AFR file for {cell['school_year']}"]
    frame = read_sheet(Path(record["path"]), find_sheet(Path(record["path"]), "REV"))
    frame["aun"] = as_code(frame["AUN"], 9)
    frame["fund"] = as_code(frame["FundCode"])
    frame["account_code"] = as_code(frame["AccountCode"])
    row = frame.loc[
        (frame["aun"] == cell["aun"])
        & (frame["fund"] == str(cell["fund_code"]))
        & (frame["account_code"] == cell["account_code"])
    ]
    if row.empty:
        return [f"AFR revenue {cell['aun']} {cell['account_code']} is not on {record['catalog_id']}"]
    amount_1 = pd.to_numeric(row["Amount1"], errors="coerce")
    total = pd.to_numeric(row["TotalAmount"], errors="coerce")
    if amount_1.isna().all() and total.isna().all():
        return [f"AFR revenue {cell['account_code']} for {cell['aun']} is blank in the workbook"]
    source = float(reported_revenue(amount_1, total).sum())
    fact = _match(
        tables["afr_revenue"],
        {
            "aun": cell["aun"],
            "school_year": int(cell["school_year"]),
            "fund_code": str(cell["fund_code"]),
            "account_code": cell["account_code"],
        },
    )
    found = None if fact.empty else float(fact["amount"].sum())
    if found is None or not _money(found, source):
        return [
            f"AFR revenue {cell['account_code']} for {cell['aun']} is {found} in parquet and {source} in REV"
        ]
    return []


def _gfb_revenue_cell(tables, index, cell) -> list[str]:
    from pa_edu.parse_gfb import revenue_budget_sheet

    record = _record(index, "gfb", int(cell["school_year"]))
    if record is None:
        return [f"no GFB file for {cell['school_year']}"]
    path = Path(record["path"])
    frame = read_sheet(path, revenue_budget_sheet(path))
    frame.columns = [str(column).strip() for column in frame.columns]
    header = cell["account_code"]
    if header not in frame.columns:
        return [f"GFB revenue column {header} is not on {record['catalog_id']}"]
    row = frame.loc[as_code(frame["AUN"], 9) == cell["aun"]]
    if row.empty:
        return [f"GFB revenue {cell['aun']} is not on {record['catalog_id']}"]
    source = float(row.iloc[0][header])
    fact = _match(
        tables["gfb_revenue"],
        {
            "aun": cell["aun"],
            "school_year": int(cell["school_year"]),
            "account_code": header,
        },
    )
    if fact.empty or not _money(fact.iloc[0]["amount"], source):
        found = None if fact.empty else fact.iloc[0]["amount"]
        return [f"GFB revenue {header} for {cell['aun']} is {found} in parquet and {source} in the workbook"]
    return []


def _revenue_title(tables: dict[str, pd.DataFrame]) -> list[str]:
    frame = tables["revenue_account"]
    row = frame.loc[frame["account_code"].astype(str) == "6111"]
    if row.empty:
        return ["revenue account 6111 is missing from the chart"]
    name = str(row.iloc[0]["name"])
    if "real estate" not in name.casefold():
        return [f"revenue account 6111 title is {name!r}"]
    return []


def _chart_descriptions(tables: dict[str, pd.DataFrame]) -> list[str]:
    """The paragraph under a heading stays with that code.

    6110 and 6111 each keep their own sentence. 1801 is not folded into 1800.
    """
    frame = tables["chart_description"]
    if frame.empty:
        return ["chart descriptions are missing"]

    def text(kind: str, code: str) -> str | None:
        rows = frame.loc[(frame["kind"] == kind) & (frame["code"].astype(str) == code), "description"]
        if rows.empty or _missing_text(rows.iloc[0]):
            return None
        return str(rows.iloc[0])

    expected = [
        ("function", "1000", "Instruction includes all those activities dealing directly"),
        ("function", "1100", "Activities designed to provide grades K–12 students with learning experiences"),
        ("function", "1801", "Include in this function costs for salaries"),
        ("object", "100", "Gross salaries paid to employees of the LEA"),
        ("object", "562", "Expenditures to reimburse Pennsylvania charter schools"),
        ("revenue", "6110", "Taxes levied by an LEA on the assessed valuation"),
        ("revenue", "6111", "Revenue received from taxes assessed and levied upon real property."),
    ]
    errors = []
    for kind, code, prefix in expected:
        found = text(kind, code)
        if found is None or not found.startswith(prefix):
            errors.append(f"chart {kind} {code} description is {found!r}")
    parent = text("revenue", "6110")
    child = text("revenue", "6111")
    if parent and child and (parent == child or child.startswith(parent[:40])):
        errors.append("chart revenue 6111 kept 6110's description")
    function_1800 = text("function", "1800")
    if function_1800 and "Include in this function costs for salaries" in function_1800:
        errors.append("chart function 1800 absorbed 1801's description")
    return errors


def _missing_text(value: object) -> bool:
    return value is None or str(value) in {"", "None", "nan", "<NA>"}


def _revenue_not_doubled(tables: dict[str, pd.DataFrame]) -> list[str]:
    """A posted account that is also another row's rollup must not be summed twice.

    7500, 7900, 8530, and 9200 are both a posted account and someone else's
    rollup. No single LEA currently posts both. Fail if one does, instead of
    inventing a rule that adds the parent on top of its children.
    """
    errors = []
    actual = tables["afr_revenue"]
    if not actual.empty:
        fund = actual.loc[actual["fund_code"].astype(str) == "10"]
        posted = fund.loc[fund["amount"].abs() > MONEY, ["aun", "school_year", "account_code"]]
        long = fund.melt(
            id_vars=["aun", "school_year", "account_code", "amount"],
            value_vars=["rollup1_account_code", "rollup2_account_code", "rollup3_account_code"],
            value_name="parent",
        )
        long = long.loc[long["parent"].notna() & (long["amount"].abs() > MONEY)]
        both = long.merge(
            posted,
            left_on=["aun", "school_year", "parent"],
            right_on=["aun", "school_year", "account_code"],
            suffixes=("", "_parent"),
        )
        both = both.loc[both["account_code"].astype(str) != both["parent"].astype(str)]
        if not both.empty:
            sample = both.iloc[0]
            errors.append(
                "AFR revenue posts "
                f"{sample['parent']} and {sample['account_code']} for {sample['aun']} "
                f"{int(sample['school_year'])}; a parent account is not added to its children"
            )
    budget = tables["gfb_revenue"]
    chains = tables["revenue_account"]
    if budget.empty or chains.empty:
        return errors
    lookup = {}
    for row in chains.itertuples(index=False):
        parents = [
            str(value)
            for value in (row.rollup1_account_code, row.rollup2_account_code, row.rollup3_account_code)
            if pd.notna(value) and str(value) not in {"", "None", "<NA>"}
        ]
        lookup[str(row.account_code)] = parents
    nonzero = budget.loc[budget["amount"].abs() > MONEY, ["aun", "school_year", "account_code"]]
    posted_budget = {
        (str(row.aun), int(row.school_year), str(row.account_code))
        for row in nonzero.itertuples(index=False)
    }
    for aun, year, account in posted_budget:
        for parent in lookup.get(account, []):
            if parent != account and (aun, year, parent) in posted_budget:
                errors.append(
                    f"GFB revenue posts {parent} and {account} for {aun} {year}; "
                    "a parent account is not added to its children"
                )
                return errors
    return errors


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


_SCHOOL_SUBJECT = {
    "english language arts": "ela",
    "math": "math",
    "mathematics": "math",
    "science": "science",
    "algebra i": "algebra_i",
    "algebra 1": "algebra_i",
    "biology": "biology",
    "literature": "literature",
}
_SCHOOL_MEASURE = {
    "number_scored": ["number scored"],
    "pct_advanced": ["% advanced", "percent advanced"],
    "pct_proficient": ["% proficient", "percent proficient"],
    "pct_basic": ["% basic", "percent basic"],
    "pct_below_basic": ["% below basic", "percent below basic"],
    "pct_proficient_and_above": [
        "percent proficient and above",
        "% advanced/proficient",
        "% proficient and above",
        "percent advanced/proficient",
    ],
    "growth": ["growth**"],
}
_SCHOOL_COUNT = {"number_scored"}
_SCHOOL_COPIED = [
    "number_scored",
    "pct_advanced",
    "pct_proficient",
    "pct_basic",
    "pct_below_basic",
    "pct_proficient_and_above",
    "school_name",
    "lea_name",
    "county",
    "document_id",
]


def _assessment_school_cell(tables, index, cell) -> list[str]:
    assessment = str(cell.get("assessment") or "pssa")
    parser_name = {"pssa": "pssa_school", "keystone": "keystone_school"}.get(assessment)
    if parser_name is None:
        return [f"unknown school assessment {assessment}"]
    record = _record(index, parser_name, int(cell["school_year"]))
    name = "PSSA" if assessment == "pssa" else "Keystone"
    if record is None:
        return [f"no {name} school file for {cell['school_year']}"]
    path = Path(record["path"])
    sheet = _school_sheet(path)
    if sheet is None:
        return [f"{record['catalog_id']} has no school sheet"]
    frame = read_headed(path, sheet, 0)
    columns = {_header_key(column): column for column in frame.columns}
    needed = ["aun", "school number", "subject", "group", "grade"]
    missing = [header for header in needed if header not in columns]
    if missing:
        return [f"{record['catalog_id']} is missing {missing}"]
    frame = frame.copy()
    frame["aun"] = as_code(frame[columns["aun"]], 9)
    frame["school_number"] = _published_school_number(frame[columns["school number"]])
    frame["subject"] = frame[columns["subject"]].map(_school_subject)
    frame["grade"] = frame[columns["grade"]].map(_school_grade)
    frame["student_group"] = frame[columns["group"]].map(lambda value: as_text(value) or "")
    source = frame.loc[
        (frame["aun"] == cell["aun"])
        & (frame["school_number"] == cell["school_number"])
        & (frame["subject"] == cell["subject"])
        & (frame["grade"] == cell["grade"])
        & (frame["student_group"] == cell["student_group"])
    ]
    label = (
        f"{name} school {cell['aun']} {cell['school_number']} {cell['subject']} "
        f"grade {cell['grade']} {cell['student_group']}"
    )
    if len(source) != 1:
        return [f"{label} has {len(source)} workbook rows on {record['catalog_id']}"]
    fact = _match(
        tables["assessment_result_school"],
        {
            "aun": cell["aun"],
            "school_number": cell["school_number"],
            "school_year": int(cell["school_year"]),
            "assessment": assessment,
            "subject": cell["subject"],
            "grade": cell["grade"],
            "student_group": cell["student_group"],
        },
    )
    if len(fact) != 1:
        return [f"{label} has {len(fact)} parquet rows"]
    errors = []
    for field, headers in _SCHOOL_MEASURE.items():
        header = next((columns[name] for name in headers if name in columns), None)
        if header is None:
            found = fact.iloc[0][field]
            if not _missing_number(found):
                errors.append(f"{label} {field} is {found} in parquet and the workbook has no column")
            continue
        source_value = source.iloc[0][header]
        found = fact.iloc[0][field]
        tolerance = 0.0 if field in _SCHOOL_COUNT else 0.05
        if not _same_number(found, source_value, tolerance):
            errors.append(f"{label} {field} is {found} in parquet and {source_value} in the workbook")
    return errors


def _assessment_school_lea(tables: dict[str, pd.DataFrame]) -> list[str]:
    """A non-district LEA is its single school row that year. Schools are not summed.

    Two PSSA schools fail the check. Two Keystone schools stay in the school
    table and are left out of the LEA view. That exclusion is expected.
    """
    school = tables["assessment_result_school"]
    district = tables["assessment_result"]
    directory = tables["lea"].drop_duplicates("aun")
    categories = dict(zip(directory["aun"].astype(str), directory["category"].astype(str), strict=True))
    view, school_view = _assessment_lea_frame(tables)
    errors = []
    if "growth" in view.columns:
        errors.append("assessment_lea carries growth")
    counts = (
        school.groupby(["aun", "school_year", "assessment"], dropna=False)["school_number"].nunique()
        if not school.empty
        else pd.Series(dtype="int64")
    )
    for (aun, year, assessment), schools in counts.items():
        category = categories.get(str(aun))
        if category is None or category == "school_district" or int(schools) <= 1:
            continue
        promoted = view.loc[
            (view["aun"].astype(str) == str(aun))
            & (view["school_year"].astype(int) == int(year))
            & (view["assessment"].astype(str) == str(assessment))
        ]
        if str(assessment) == "keystone":
            if not promoted.empty:
                errors.append(
                    f"Keystone {int(year)} AUN {aun} has an LEA row from {int(schools)} schools"
                )
            continue
        errors.append(
            f"PSSA {int(year)} AUN {aun} has {int(schools)} schools; "
            "a non-district LEA row is not published"
        )
        if not promoted.empty:
            errors.append(f"PSSA {int(year)} AUN {aun} has an LEA row from {int(schools)} schools")
    errors.extend(_lea_matches_school(view, school_view, categories))
    errors.extend(_lea_matches_district(view, district, categories))
    return errors


def _lea_matches_school(view, school, categories: dict[str, str]) -> list[str]:
    """The LEA copy matches the school view, including a filled Keystone proficient+."""
    if school.empty:
        extra = view.loc[view["category"].astype(str) != "school_district"] if not view.empty else view
        if extra is not None and not extra.empty:
            return [f"assessment_lea has {len(extra)} non-district rows and no school rows"]
        return []
    single = []
    for (aun, year), rows in school.groupby(["aun", "school_year"], dropna=False):
        if categories.get(str(aun)) in {None, "school_district"}:
            continue
        if rows["school_number"].nunique(dropna=False) == 1:
            single.append(rows)
    promoted = view.loc[view["category"].astype(str) != "school_district"] if not view.empty else view.iloc[0:0]
    if not single:
        if not promoted.empty:
            return [f"assessment_lea has {len(promoted)} non-district rows without a single school"]
        return []
    expected = pd.concat(single, ignore_index=True)
    return _same_rows(
        promoted,
        expected,
        ["aun", "school_year", "assessment", "school_number", "subject", "grade", "student_group"],
        _SCHOOL_COPIED,
        "assessment_lea school",
    )


def _lea_matches_district(view, district, categories: dict[str, str]) -> list[str]:
    if not view.empty and (view["category"].astype(str) == "school_district").any():
        districts = view.loc[view["category"].astype(str) == "school_district"]
        if districts["school_number"].notna().any() or districts["school_name"].notna().any():
            return ["assessment_lea has a school id on a district row"]
    else:
        districts = view.iloc[0:0]
    if district.empty:
        if not districts.empty:
            return [f"assessment_lea has {len(districts)} district rows and no district workbook rows"]
        return []
    expected = district.loc[district["aun"].astype(str).map(categories).eq("school_district")].copy()
    fields = [
        "number_scored",
        "pct_advanced",
        "pct_proficient",
        "pct_basic",
        "pct_below_basic",
        "pct_proficient_and_above",
        "lea_name",
        "county",
        "document_id",
    ]
    return _same_rows(
        districts,
        expected,
        ["aun", "school_year", "assessment", "subject", "grade", "student_group"],
        fields,
        "assessment_lea district",
    )


def _assessment_lea_frame(tables: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """LEA view, and the school view it copies.

    The school view fills a null Keystone proficient+ from the level percents.
    The LEA copy matches that view value. The stored parquet cell is unchanged.
    """
    import duckdb

    from pa_edu.portal import assessment_school_select, load_views

    statement = next(view.sql for view in load_views() if view.name == "assessment_lea")
    connection = duckdb.connect()
    try:
        connection.register("assessment_result", tables["assessment_result"])
        connection.register("_assessment_result_school", tables["assessment_result_school"])
        connection.execute(
            "CREATE VIEW assessment_result_school AS "
            + assessment_school_select("_assessment_result_school")
        )
        connection.register("lea", tables["lea"])
        connection.execute(statement)
        lea = connection.execute("SELECT * FROM assessment_lea").fetchdf()
        school = connection.execute("SELECT * FROM assessment_result_school").fetchdf()
        return lea, school
    finally:
        connection.close()


def _same_rows(left, right, keys: list[str], fields: list[str], label: str) -> list[str]:
    left = left.copy()
    right = right.copy()
    for frame in (left, right):
        frame["aun"] = frame["aun"].astype(str)
        frame["school_year"] = frame["school_year"].astype(int)
        for key in keys:
            if key in {"aun", "school_year"}:
                continue
            frame[key] = frame[key].map(lambda value: "" if _missing_text(value) else str(value))
    if len(left) != len(right):
        return [f"{label} has {len(left)} rows and the source has {len(right)}"]
    if left.empty:
        return []
    paired = left.merge(right, on=keys, how="outer", suffixes=("_lea", "_src"), indicator=True)
    missing = paired.loc[paired["_merge"] != "both"]
    if not missing.empty:
        sample = missing.iloc[0]
        return [f"{label} key {tuple(sample[key] for key in keys)} is {sample['_merge']}"]
    errors = []
    for field in fields:
        numeric = field in _SCHOOL_COUNT or field.startswith("pct_") or field == "number_scored"
        for row in paired.itertuples(index=False):
            found = getattr(row, f"{field}_lea")
            source = getattr(row, f"{field}_src")
            same = _same_number(found, source, 0.0 if field == "number_scored" else 0.05) if numeric else _same_text(found, source)
            if same:
                continue
            key = tuple(getattr(row, key) for key in keys)
            errors.append(f"{label} {field} for {key} is {found} and the source is {source}")
            break
    return errors


def _school_sheet(path: Path) -> str | None:
    found = []
    for name in sheet_names(path):
        frame = read_headed(path, name, 0)
        labels = {_header_key(column) for column in frame.columns}
        if "aun" in labels and "school number" in labels:
            found.append(name)
    if len(found) == 1:
        return found[0]
    return None


def _published_school_number(values: pd.Series) -> pd.Series:
    """The workbook pads with zeros. ``000007691`` is school 7691."""
    codes = as_code(values)

    def one(value: object) -> object:
        if value is None or pd.isna(value):
            return pd.NA
        token = str(value)
        if token.isdigit():
            return token.lstrip("0") or "0"
        return token

    return codes.map(one).astype("string")


def _school_subject(value: object) -> object:
    text = as_text(value)
    if text is None:
        return pd.NA
    return _SCHOOL_SUBJECT.get(text.casefold(), pd.NA)


def _school_grade(value: object) -> object:
    text = as_text(value)
    if text is None:
        return pd.NA
    folded = text.casefold()
    if folded in {"total", "school total", "district total"}:
        return "total"
    if text.isdigit():
        return f"{int(text):03d}"
    return folded


def _header_key(column: object) -> str:
    return re.sub(r"\s+", " ", str(column).replace("\n", " ")).strip().casefold()


def _same_number(found, source, tolerance: float) -> bool:
    if _missing_number(found) and _missing_number(source):
        return True
    if _missing_number(found) or _missing_number(source):
        return False
    found_value = float(found)
    source_value = float(pd.to_numeric(pd.Series([source]), errors="coerce").iloc[0])
    if pd.isna(source_value):
        return False
    return abs(found_value - source_value) <= tolerance


def _same_text(found, source) -> bool:
    if _missing_text(found) and _missing_text(source):
        return True
    if _missing_text(found) or _missing_text(source):
        return False
    return str(found) == str(source)


def _missing_number(value) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except TypeError:
        return False


def _missing_text(value) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except TypeError:
        return False
    return str(value) in {"", "nan", "None", "<NA>"}


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


def _low_income_cell(tables: dict[str, pd.DataFrame], index: dict, cell: dict) -> list[str]:
    record = _record(index, "low_income", int(cell["school_year"]))
    if record is None:
        return [f"no low-income file for {cell['school_year']}"]
    from pa_edu.parse_low_income import parse_low_income

    parsed = parse_low_income(Path(record["path"]), record)["enrollment_low_income"]
    source = parsed.loc[parsed["aun"] == cell["aun"]]
    if source.empty:
        return [f"low income {cell['aun']} is not on {record['catalog_id']}"]
    source_count = int(source.iloc[0]["low_income_enrollment"])
    fact = _match(
        tables["enrollment_low_income"],
        {"aun": cell["aun"], "school_year": int(cell["school_year"])},
    )
    if fact.empty or int(fact.iloc[0]["low_income_enrollment"]) != source_count:
        found = None if fact.empty else fact.iloc[0]["low_income_enrollment"]
        return [
            f"low income for {cell['aun']} {cell['school_year']} is {found} in parquet "
            f"and {source_count} in the workbook"
        ]
    return []


def _iep_cell(tables: dict[str, pd.DataFrame], index: dict, cell: dict) -> list[str]:
    records = _records(index, "iep")
    if len(records) != 1:
        return [f"expected one IEP-by-LEA file, found {len(records)}"]
    record = records[0]
    from pa_edu.parse_iep import parse_iep

    parsed = parse_iep(Path(record["path"]), record)["enrollment_iep"]
    source = parsed.loc[
        (parsed["aun"] == cell["aun"]) & (parsed["school_year"].astype(int) == int(cell["school_year"]))
    ]
    if source.empty:
        return [f"IEP {cell['aun']} {cell['school_year']} is not on {record['catalog_id']}"]
    source_count = int(source.iloc[0]["iep_enrollment"])
    fact = _match(
        tables["enrollment_iep"],
        {"aun": cell["aun"], "school_year": int(cell["school_year"])},
    )
    if fact.empty or int(fact.iloc[0]["iep_enrollment"]) != source_count:
        found = None if fact.empty else fact.iloc[0]["iep_enrollment"]
        return [
            f"IEP for {cell['aun']} {cell['school_year']} is {found} in parquet "
            f"and {source_count} in the workbook"
        ]
    return []


_COHORT_COLUMNS = {
    "lea type": "lea_type",
    "aun": "aun",
    "lea": "lea_name",
    "grads": "graduates",
    "cohort": "cohort",
    "cohort grad rate": "rate",
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
_COHORT_FACTS = {"lea_type", "aun", "lea_name", "graduates", "cohort", "rate"}


def _cohort_grad_cell(tables: dict[str, pd.DataFrame], index: dict, cell: dict) -> list[str]:
    catalog_id = f"cohort-grad-{int(cell['school_year'])}-{int(cell['span'])}"
    record = _by_catalog(index, catalog_id)
    if record is None or record.get("status") != "stable":
        return [f"no cohort graduation file {catalog_id}"]
    frame = _cohort_lea_table(Path(record["path"]))
    if "aun" not in frame.columns:
        return [f"{catalog_id} LEA sheet has no AUN column"]
    rows = frame.loc[as_code(frame["aun"], 9) == cell["aun"]]
    if len(rows) != 1:
        return [f"cohort graduation {cell['aun']} on {catalog_id} matched {len(rows)} rows"]
    source = rows.iloc[0]
    label = f"{cell['aun']} {cell['school_year']} span {cell['span']}"
    fact = _match(
        tables["cohort_graduation"],
        {"aun": cell["aun"], "school_year": int(cell["school_year"]), "span": int(cell["span"])},
    )
    if fact.empty:
        return [f"cohort graduation {label} is missing from parquet"]
    got = fact.iloc[0]
    errors = []
    for column in ("graduates", "cohort"):
        source_count = int(round(float(source[column])))
        if int(got[column]) != source_count:
            errors.append(f"cohort graduation {column} for {label} is {got[column]} in parquet and {source_count} in the workbook")
    source_rate = float(source["rate"])
    if abs(float(got["rate"]) - source_rate) > 1e-9:
        errors.append(f"cohort graduation rate for {label} is {got['rate']} in parquet and {source_rate} in the workbook")
    published: dict[str, float] = {}
    for column in frame.columns:
        if column in _COHORT_FACTS:
            continue
        value = source[column]
        if _cohort_unpublished(value):
            continue
        published[str(column)] = float(value)
    group_rows = _match(
        tables["cohort_graduation_group"],
        {"aun": cell["aun"], "school_year": int(cell["school_year"]), "span": int(cell["span"])},
    )
    found = {str(row.student_group): float(row.rate) for row in group_rows.itertuples(index=False)}
    if set(found) != set(published):
        errors.append(f"cohort graduation groups for {label} are {sorted(found)} in parquet and {sorted(published)} in the workbook")
    for group, rate in published.items():
        if group not in found:
            continue
        if abs(found[group] - rate) > 1e-9:
            errors.append(f"cohort graduation {group} for {label} is {found[group]} in parquet and {rate} in the workbook")
    return errors


def _cohort_lea_table(path: Path) -> pd.DataFrame:
    matches = [name for name in sheet_names(path) if "by lea" in name.casefold()]
    if len(matches) != 1:
        raise ValueError(f"{path.name} has LEA sheets {matches}")
    engine = "xlrd" if path.suffix.lower() == ".xls" else "openpyxl"
    raw = pd.read_excel(path, sheet_name=matches[0], header=None, engine=engine)
    header_index = None
    for index, row in raw.iterrows():
        if any(_cohort_norm(value) == "aun" for value in row.tolist()):
            header_index = int(index)
            break
    if header_index is None:
        raise ValueError(f"{path.name} LEA sheet has no AUN header")
    columns: dict[str, int] = {}
    for position, value in enumerate(raw.iloc[header_index].tolist()):
        name = _cohort_norm(value)
        if not name:
            continue
        field = _COHORT_COLUMNS.get(name)
        if field is None or field in columns:
            continue
        columns[field] = position
    data = raw.iloc[header_index + 1 :]
    return pd.DataFrame(
        {field: data.iloc[:, position].reset_index(drop=True) for field, position in columns.items()}
    )


def _cohort_norm(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return " ".join(str(value).replace("\n", " ").split()).casefold()


def _cohort_unpublished(value: object) -> bool:
    if value is None or pd.isna(value):
        return True
    text = str(value).strip()
    if not text:
        return True
    folded = text.casefold()
    return "ferpa" in folded and "supress" in folded.replace("pp", "p")


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


def _population_districts(tables: dict[str, pd.DataFrame]) -> list[str]:
    frame = tables["district_population"]
    if frame.empty:
        return []
    directory = tables["lea"].drop_duplicates("aun")
    categories = dict(zip(directory["aun"].astype(str), directory["category"].astype(str), strict=True))
    bad = sorted({
        aun for aun in frame["aun"].dropna().astype(str)
        if aun in categories and categories[aun] != "school_district"
    })
    if not bad:
        return []
    return [f"district_population AUN is not a school district: {bad[:8]}"]


def _saipe_counts(tables: dict[str, pd.DataFrame], index: dict) -> list[str]:
    """501 districts in each file for 2004–2008, and 500 for 2009–2024."""
    errors = []
    frame = tables["district_population"]
    for record in _records(index, "saipe"):
        year = int(record["school_year"])
        if 2004 <= year <= 2008:
            expected = 501
        elif 2009 <= year <= 2024:
            expected = 500
        else:
            errors.append(f"no SAIPE district count for {year}")
            continue
        lines = Path(record["path"]).read_bytes().decode("ascii").splitlines()
        if len(lines) != expected:
            errors.append(f"SAIPE {year} file has {len(lines)} records, expected {expected}")
        got = 0 if frame.empty else int((frame["school_year"].astype(int) == year).sum())
        if got != expected:
            errors.append(f"SAIPE {year} district_population has {got} rows, expected {expected}")
    return errors


def _saipe_cell(tables, index, cell) -> list[str]:
    """Re-read the retained text. Positions come from that year's Census layout."""
    year = int(cell["school_year"])
    record = _record(index, "saipe", year)
    if record is None:
        return [f"no SAIPE file for {year}"]
    layout = _saipe_layout(year)
    if layout is None:
        return [f"no SAIPE layout for {year}"]
    length, total, children, poverty = layout
    line, problem = _saipe_line(Path(record["path"]), str(cell["nces_leaid"]), length)
    if problem:
        return [f"SAIPE {cell['nces_leaid']} {year} {problem} on {record['catalog_id']}"]
    if line is None:
        return [f"SAIPE {cell['nces_leaid']} is not on {record['catalog_id']}"]
    source = {
        "total_population": _saipe_count(line, total),
        "population_5_17": _saipe_count(line, children),
        "children_5_17_in_poverty": _saipe_count(line, poverty),
    }
    if any(value is None for value in source.values()):
        return [f"SAIPE {cell['nces_leaid']} {year} count is not an integer in the file"]
    found = _match(
        tables["district_population"],
        {"aun": cell["aun"], "school_year": year, "nces_leaid": cell["nces_leaid"]},
    )
    if len(found) != 1:
        return [f"SAIPE {cell['aun']} {year} has {len(found)} district_population rows"]
    row = found.iloc[0]
    errors = []
    for column, source_value in source.items():
        if pd.isna(row[column]) or int(row[column]) != source_value:
            errors.append(
                f"SAIPE {column} for {cell['aun']} {year} is {row[column]} in parquet and {source_value} in the file"
            )
    return errors


def _saipe_layout(year: int):
    if 2004 <= year <= 2009:
        return 124, (76, 83), (85, 92), (94, 101)
    if 2010 <= year <= 2024:
        return 131, (83, 90), (92, 99), (101, 108)
    return None


def _saipe_line(path: Path, leaid: str, length: int) -> tuple[str | None, str | None]:
    text = path.read_bytes().decode("ascii")
    found = None
    for line in text.splitlines():
        if len(line) < 8 or line[0:2] + line[3:8] != leaid:
            continue
        if len(line) != length:
            return None, f"record length is {len(line)}, not {length}"
        if found is not None:
            return None, "is on more than one record"
        found = line
    return found, None


def _saipe_count(line: str, span: tuple[int, int]) -> int | None:
    token = line[span[0] - 1:span[1]].strip()
    if not token.isdigit():
        return None
    return int(token)


if __name__ == "__main__":
    main()
