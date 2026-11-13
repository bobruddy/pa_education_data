"""Write the static LEA browser for https://pdenumbers.org.

`python -m pa_edu.publish` reads `data/refined/*.parquet` and writes `pde_site/`.
It then copies that directory to `/data/pdenumbers/htdocs/` on elm. nginx
serves it at https://pdenumbers.org.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from pa_edu.common import DATA_DIR, ROOT

OUT = ROOT / "pde_site"
WEB = Path(__file__).resolve().parent / "web"
REFINED = DATA_DIR / "refined"
SQLITE = DATA_DIR / "pde.db"
ELM_TARGET = "elm:/data/pdenumbers/htdocs/"
PERSONNEL_PAGE = (
    "https://www.pa.gov/agencies/education/data-and-reporting/school-staff/"
    "professional-and-support-personnel"
)
ASSESSMENT_PAGE = (
    "https://www.pa.gov/agencies/education/data-and-reporting/assessment-reporting"
)
ENROLLMENT_PAGE = (
    "https://www.pa.gov/agencies/education/data-and-reporting/enrollment"
)
GRADUATION_PAGE = (
    "https://www.pa.gov/agencies/education/data-and-reporting/high-school-graduation"
)
ADM_PAGE = (
    "https://www.pa.gov/agencies/education/programs-and-services/schools/"
    "grants-and-funding/school-finances/financial-data/financial-data-elements"
)
SALARY_GROUPS = [
    ("elementary", "Elementary teachers"),
    ("secondary", "Secondary teachers"),
    ("administrator", "Administrators"),
    ("support", "Professional support"),
    ("ungraded", "Ungraded teachers"),
]
SALARY_BIN_START = 25_000
SALARY_BIN_STOP = 200_000
SALARY_BIN_WIDTH = 5_000
SALARY_EDGES = list(range(SALARY_BIN_START, SALARY_BIN_STOP + SALARY_BIN_WIDTH, SALARY_BIN_WIDTH))
# Integer years: under 1, then each year through 39, then 40+.
EXPERIENCE_EDGES = list(range(1, 41))
EXPERIENCE_MODES = [
    ("lea", "Years in this LEA"),
    ("edu", "Years in education"),
]
MASTERS_PLUS = {"1054", "1055", "1057"}
SALARY_LABEL_GROUPS = {
    "ELEMENTARY TEACHERS": "elementary",
    "KINDERGARTEN TEACHERS": "elementary",
    "PRE-KINDERGARTEN TEACHERS": "elementary",
    "SECONDARY TEACHERS": "secondary",
    "UNGRADED TEACHERS": "ungraded",
    "SCHOOL ADMINISTRATORS": "administrator",
    "LEA ADMINISTRATORS": "administrator",
}

MAJORS = [
    ("1000", "Instruction"),
    ("2000", "Support services"),
    ("3000", "Noninstructional"),
    ("4000", "Facilities"),
    ("5000", "Other financing uses"),
]
MAJOR_OBJECTS = [
    ("100", "Salaries"),
    ("200", "Benefits"),
    ("300", "Professional services"),
    ("400", "Property services"),
    ("500", "Other purchased services"),
    ("600", "Supplies"),
    ("700", "Property"),
    ("800", "Other objects"),
    ("900", "Other uses of funds"),
]
CATEGORIES = [
    ("school_district", "School district"),
    ("charter_school", "Charter"),
    ("career_and_technical_center", "Career & technical"),
    ("jointure", "Jointure"),
    ("state_juvenile_correctional", "State juvenile"),
    ("unknown", "Other"),
]
SITE_EXCLUDED_CATEGORIES = {"intermediate_unit"}
GRADE_ORDER = [
    ("prek", "Pre-kindergarten"),
    ("pka", "Pre-kindergarten, morning"),
    ("pkp", "Pre-kindergarten, afternoon"),
    ("pkf", "Pre-kindergarten, full day"),
    ("k4", "Kindergarten, first year"),
    ("k4a", "K4, morning"),
    ("k4p", "K4, afternoon"),
    ("k4f", "K4, full day"),
    ("k5", "Kindergarten"),
    ("k5a", "K5, morning"),
    ("k5p", "K5, afternoon"),
    ("k5f", "K5, full day"),
    *[(f"{grade:03d}", f"Grade {grade}") for grade in range(1, 13)],
    ("eug", "Ungraded elementary"),
    ("sug", "Ungraded secondary"),
]


def lea_document(profile: dict, years: dict) -> dict:
    kept = {}
    for year in sorted(years):
        block = years[year]
        if any(
            block.get(key)
            for key in (
                "grades",
                "schools",
                "actual",
                "budget",
                "budgetDetail",
                "actualDetail",
                "actualSchool",
                "salaries",
                "experience",
                "retention",
                "charterTuition",
                "countyRanks",
                "act1",
                "act1Base",
                "mills",
                "keystone",
                "charterAdm",
                "homeEducation",
            )
        ):
            kept[str(year)] = block
    return {**profile, "years": kept}


def directory_row(lea: dict, enrollment: int | None, actual: float | None, budget: float | None) -> dict:
    return {
        "aun": lea["aun"],
        "name": lea["name"],
        "county": lea["county"],
        "category": lea["category"],
        "status": lea["status"],
        "enrollment": enrollment,
        "actual": actual,
        "budget": budget,
    }


def main() -> None:
    if not (REFINED / "lea.parquet").exists():
        raise SystemExit("data/refined is missing. Run python -m pa_edu.refine first.")
    connection = duckdb.connect()
    catalog = _catalog(connection)
    profiles = [
        profile
        for profile in _profiles(connection)
        if profile["category"] not in SITE_EXCLUDED_CATEGORIES
    ]
    grades = _nested(connection, "grades")
    schools = _schools(connection)
    race = _enrollment_dim(connection, "enrollment_race.parquet", "race")
    gender = _enrollment_dim(connection, "enrollment_gender.parquet", "gender")
    pssa = _assessment(connection, "pssa")
    keystone = _keystone(connection)
    actual = _nested(connection, "actual")
    budget = _nested(connection, "budget")
    budget_detail = _detail(connection, "budget")
    actual_detail = _detail(connection, "actual")
    actual_school = _school_detail(connection)
    salaries, experience, retention = _salaries()
    charter = _charter_tuition(connection)
    charter_adm = _charter_adm(connection)
    home_education = _home_education(connection)
    low_income = _low_income(connection)
    iep = _iep(connection)
    graduation = _cohort_graduation(connection)
    act1 = _act1_index(connection)
    act1_base = _act1_base(connection)
    mills = _real_estate_tax(connection)
    ranks = _county_ranks(profiles, grades, actual, budget, charter, keystone, pssa, graduation)
    enrollment_year = catalog["enrollmentYear"]
    actual_year = catalog["actualYear"]
    budget_year = catalog["budgetYear"]
    catalog["salaryYear"] = max((year for years in salaries.values() for year in years), default=None)
    catalog["salaryGroups"] = [{"id": code, "label": label} for code, label in SALARY_GROUPS]
    catalog["salaryEdges"] = SALARY_EDGES
    catalog["experienceEdges"] = EXPERIENCE_EDGES
    catalog["experienceModes"] = [{"id": code, "label": label} for code, label in EXPERIENCE_MODES]
    catalog["sources"]["personnel"] = PERSONNEL_PAGE

    if OUT.exists():
        shutil.rmtree(OUT)
    data_dir = OUT / "data" / "lea"
    data_dir.mkdir(parents=True)
    for name in ("index.html", "app.css", "app.js"):
        shutil.copyfile(WEB / name, OUT / name)

    rows = []
    for profile in profiles:
        aun = profile["aun"]
        document = lea_document(
            profile,
            _years_for(
                aun,
                grades,
                schools,
                race,
                gender,
                pssa,
                actual,
                budget,
                budget_detail,
                actual_detail,
                actual_school,
                salaries,
                experience,
                retention,
                charter,
                ranks,
                act1,
                act1_base,
                mills,
                keystone,
                charter_adm,
                home_education,
                low_income,
                iep,
                graduation,
            ),
        )
        (data_dir / f"{aun}.json").write_text(_dump(document), encoding="utf-8")
        snapshot = document["years"]
        rows.append(directory_row(
            profile,
            _total(snapshot.get(str(enrollment_year), {}).get("grades")),
            _total(snapshot.get(str(actual_year), {}).get("actual")),
            _total(snapshot.get(str(budget_year), {}).get("budget")),
        ))
    payload = {**catalog, "leas": rows}
    (OUT / "data" / "index.json").write_text(_dump(payload), encoding="utf-8")
    print(f"wrote {OUT} ({len(rows)} LEAs)")
    deploy()


def deploy() -> None:
    subprocess.run(
        ["rsync", "-a", "--delete", f"{OUT}/", ELM_TARGET],
        check=True,
    )
    print(f"published {ELM_TARGET}")


def _dump(payload: dict) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def _total(values: dict | None) -> int | float | None:
    if not values:
        return None
    return round(sum(values.values()), 2)


def _years_for(
    aun: str,
    grades: dict,
    schools: dict,
    race: dict,
    gender: dict,
    pssa: dict,
    actual: dict,
    budget: dict,
    budget_detail: dict,
    actual_detail: dict,
    actual_school: dict,
    salaries: dict,
    experience: dict | None = None,
    retention: dict | None = None,
    charter: dict | None = None,
    ranks: dict | None = None,
    act1: dict | None = None,
    act1_base: dict | None = None,
    mills: dict | None = None,
    keystone: dict | None = None,
    charter_adm: dict | None = None,
    home_education: dict | None = None,
    low_income: dict | None = None,
    iep: dict | None = None,
    graduation: dict | None = None,
) -> dict:
    experience = experience or {}
    retention = retention or {}
    charter = charter or {}
    ranks = ranks or {}
    act1 = act1 or {}
    act1_base = act1_base or {}
    mills = mills or {}
    keystone = keystone or {}
    charter_adm = charter_adm or {}
    home_education = home_education or {}
    low_income = low_income or {}
    iep = iep or {}
    graduation = graduation or {}
    years = (
        set(grades.get(aun, {}))
        | set(schools.get(aun, {}))
        | set(race.get(aun, {}))
        | set(gender.get(aun, {}))
        | set(pssa.get(aun, {}))
        | set(keystone.get(aun, {}))
        | set(actual.get(aun, {}))
        | set(budget.get(aun, {}))
        | set(budget_detail.get(aun, {}))
        | set(actual_detail.get(aun, {}))
        | set(actual_school.get(aun, {}))
        | set(salaries.get(aun, {}))
        | set(experience.get(aun, {}))
        | set(retention.get(aun, {}))
        | set(ranks.get(aun, {}))
    )
    actual_years = actual.get(aun, {})
    charter_years = charter.get(aun, {})
    blocks = {}
    for year in years:
        block = {
            "grades": grades.get(aun, {}).get(year, {}),
            "schools": schools.get(aun, {}).get(year, []),
            "race": race.get(aun, {}).get(year, {}),
            "gender": gender.get(aun, {}).get(year, {}),
            "pssa": pssa.get(aun, {}).get(year, {}),
            "keystone": keystone.get(aun, {}).get(year, {}),
            "actual": actual_years.get(year, {}),
            "budget": budget.get(aun, {}).get(year, {}),
            "budgetDetail": budget_detail.get(aun, {}).get(year, {}),
            "actualDetail": actual_detail.get(aun, {}).get(year, {}),
            "actualSchool": actual_school.get(aun, {}).get(year, {}),
            "salaries": salaries.get(aun, {}).get(year, {}),
            "experience": experience.get(aun, {}).get(year, {}),
            "retention": retention.get(aun, {}).get(year),
            "charterTuition": (
                charter_years.get(year, 0.0) if year in actual_years else charter_years.get(year)
            ),
            "countyRanks": ranks.get(aun, {}).get(year, {}),
        }
        rate = act1.get(aun, {}).get(year)
        if rate is not None:
            block["act1"] = rate
        base = act1_base.get(year)
        if base is not None:
            block["act1Base"] = base
        rates = mills.get(aun, {}).get(year)
        if rates:
            block["mills"] = rates
        charter_count = charter_adm.get(aun, {}).get(year)
        if charter_count is not None:
            block["charterAdm"] = charter_count
        home_count = home_education.get(aun, {}).get(year)
        if home_count is not None:
            block["homeEducation"] = home_count
        low = low_income.get(aun, {}).get(year)
        if low is not None:
            block["lowIncome"] = low
        iep_cell = iep.get(aun, {}).get(year)
        if iep_cell is not None:
            block["iep"] = iep_cell
        grad = graduation.get(aun, {}).get(year)
        if grad:
            block["graduation"] = grad
        blocks[year] = block
    return blocks


def _charter_as_of(amounts: dict, year: int) -> float:
    """Object 562 for this year, or the latest earlier year when that AFR is not in yet."""
    if not amounts:
        return 0.0
    if year in amounts and amounts[year] is not None:
        return amounts[year] or 0.0
    earlier = [item for item in amounts if item < year and amounts[item] is not None]
    if not earlier:
        return 0.0
    return amounts[max(earlier)] or 0.0


def _county_ranks(
    profiles: list[dict],
    grades: dict,
    actual: dict,
    budget: dict,
    charter: dict,
    keystone: dict | None = None,
    pssa: dict | None = None,
    graduation: dict | None = None,
) -> dict:
    """Rank each LEA against others in its county for the top-card metrics."""
    keystone = keystone or {}
    pssa = pssa or {}
    graduation = graduation or {}
    by_county: dict[str, list[dict]] = {}
    for profile in profiles:
        by_county.setdefault(profile["county"], []).append(profile)

    years: set[int] = set()
    for nested in (grades, actual, budget, keystone, pssa, graduation):
        for lea_years in nested.values():
            years.update(lea_years)

    ranked: dict[str, dict[int, dict]] = {}
    for peers in by_county.values():
        for year in years:
            buckets = {
                "enrollment": [],
                "actual": [],
                "budget": [],
                "keystone_algebra_i": [],
                "keystone_literature": [],
                "keystone_biology": [],
                "pssa_math": [],
                "pssa_ela": [],
                "graduation": [],
            }
            actual_per_student: list[dict] = []
            budget_per_student: list[dict] = []
            for profile in peers:
                aun = profile["aun"]
                enrolled = _total(grades.get(aun, {}).get(year))
                spent = _total(actual.get(aun, {}).get(year))
                adopted = _total(budget.get(aun, {}).get(year))
                row = {"aun": aun, "name": profile["name"]}
                if enrolled is not None:
                    buckets["enrollment"].append({**row, "value": enrolled})
                if spent is not None:
                    buckets["actual"].append({**row, "value": spent})
                if adopted is not None:
                    buckets["budget"].append({**row, "value": adopted})
                if enrolled:
                    if spent is not None:
                        charter_amount = charter.get(aun, {}).get(year, 0.0) or 0.0
                        actual_per_student.append({
                            **row,
                            "value": _number((spent - charter_amount) / enrolled),
                        })
                    elif adopted is not None:
                        charter_amount = _charter_as_of(charter.get(aun, {}), year)
                        budget_per_student.append({
                            **row,
                            "value": _number((adopted - charter_amount) / enrolled),
                        })
                for subject in ("algebra_i", "literature", "biology"):
                    cell = (
                        keystone.get(aun, {})
                        .get(year, {})
                        .get(subject, {})
                        .get("011", {})
                        .get("All Students")
                    )
                    pct = None if not cell else cell.get("pct")
                    if pct is not None:
                        buckets[f"keystone_{subject}"].append({**row, "value": float(pct)})
                for subject in ("math", "ela"):
                    cell = (
                        pssa.get(aun, {})
                        .get(year, {})
                        .get(subject, {})
                        .get("total", {})
                        .get("All Students")
                    )
                    pct = None if not cell else cell.get("pct")
                    if pct is not None:
                        buckets[f"pssa_{subject}"].append({**row, "value": float(pct)})
                grad = graduation.get(aun, {}).get(year, {}).get("4")
                if grad and grad.get("rate") is not None:
                    buckets["graduation"].append({**row, "value": float(grad["rate"]) * 100})
            # A year with any AFR stays on actuals. Budget per student ranks only
            # when nobody in the county has actuals yet, so the two are never mixed.
            buckets["perStudent"] = actual_per_student or budget_per_student
            for metric, rows in buckets.items():
                if len(rows) < 2:
                    continue
                ordered = sorted(rows, key=lambda item: (-float(item["value"]), item["name"]))
                peer_list = [
                    {"aun": item["aun"], "name": item["name"], "value": item["value"]}
                    for item in ordered
                ]
                total = len(peer_list)
                for index, item in enumerate(ordered, start=1):
                    ranked.setdefault(item["aun"], {}).setdefault(year, {})[metric] = {
                        "rank": index,
                        "of": total,
                        "peers": peer_list,
                    }
    return ranked


def _catalog(connection: duckdb.DuckDBPyConnection) -> dict:
    enrollment_year = _max_year(connection, "enrollment.parquet")
    actual_year = _max_year(connection, "afr_expenditure.parquet")
    budget_year = _max_year(connection, "gfb_expenditure.parquet")
    sources = {
        "enrollment": {}, "afr": {}, "gfb": {}, "edna": None,
        "act1": None, "act1Base": None, "retax": {},
        "pssa": {}, "keystone": {}, "assessment": ASSESSMENT_PAGE,
        "enrollmentPage": ENROLLMENT_PAGE,
        "admPage": ADM_PAGE,
        "charterAdm": {}, "homeEducation": {}, "lowIncome": {}, "iep": None,
        "cohortGrad": {}, "graduationPage": GRADUATION_PAGE,
        "chart": None,
    }
    frame = connection.sql(f"""
        SELECT parser, school_year, source_url, catalog_id
        FROM (
            SELECT parser, school_year, source_url, catalog_id,
                   row_number() OVER (PARTITION BY catalog_id ORDER BY retrieved_at DESC) AS n
            FROM '{REFINED / "document.parquet"}'
        )
        WHERE n = 1 AND parser IN (
            'enrollment', 'afr', 'gfb', 'edna', 'act1', 'act1_base', 'retax', 'pssa', 'keystone',
            'charter_adm', 'homeschool', 'low_income', 'iep', 'cohort_grad', 'chart'
        )
    """).df()
    chart_year = -1
    for row in frame.itertuples(index=False):
        if row.parser == "edna":
            sources["edna"] = row.source_url
        elif row.parser == "act1":
            sources["act1"] = row.source_url
        elif row.parser == "act1_base":
            sources["act1Base"] = row.source_url
        elif row.parser == "iep":
            sources["iep"] = row.source_url
        elif row.parser == "chart" and row.source_url:
            year = -1 if _missing(row.school_year) else int(row.school_year)
            if sources["chart"] is None or year >= chart_year:
                sources["chart"] = row.source_url
                chart_year = year
        elif row.parser == "retax" and row.school_year is not None and not _missing(row.school_year):
            sources["retax"][str(int(row.school_year))] = row.source_url
        elif row.parser == "charter_adm" and row.school_year is not None and not _missing(row.school_year):
            sources["charterAdm"][str(int(row.school_year))] = row.source_url
        elif row.parser == "homeschool" and row.school_year is not None and not _missing(row.school_year):
            sources["homeEducation"][str(int(row.school_year))] = row.source_url
        elif row.parser == "low_income" and row.school_year is not None and not _missing(row.school_year):
            sources["lowIncome"][str(int(row.school_year))] = row.source_url
        elif row.parser == "cohort_grad" and row.school_year is not None and not _missing(row.school_year):
            span = str(row.catalog_id).rsplit("-", 1)[-1]
            if span in {"4", "5", "6"}:
                sources["cohortGrad"].setdefault(str(int(row.school_year)), {})[span] = row.source_url
        elif row.school_year is not None and not _missing(row.school_year):
            sources[row.parser][str(int(row.school_year))] = row.source_url
    functions = {
        str(row.function_code): _short_title(row.function_name)
        for row in connection.sql(f"""
            SELECT function_code, any_value(function_name) AS function_name
            FROM '{REFINED / "account.parquet"}'
            WHERE function_code IS NOT NULL AND function_name IS NOT NULL
            GROUP BY 1
        """).df().itertuples(index=False)
    }
    for code, label in MAJORS:
        functions.setdefault(code, label)
    objects = {code: label for code, label in MAJOR_OBJECTS}
    for row in connection.sql(f"""
        SELECT object_code, any_value(object_name) AS object_name
        FROM '{REFINED / "account.parquet"}'
        WHERE object_code IS NOT NULL AND object_name IS NOT NULL
        GROUP BY 1
    """).df().itertuples(index=False):
        objects.setdefault(str(row.object_code), _short_title(row.object_name))
    return {
        "enrollmentYear": enrollment_year,
        "actualYear": actual_year,
        "budgetYear": budget_year,
        "grades": [{"code": code, "label": label} for code, label in GRADE_ORDER],
        "majors": [{"code": code, "label": label} for code, label in MAJORS],
        "objects": [{"code": code, "label": label} for code, label in MAJOR_OBJECTS],
        "functions": functions,
        "objectNames": objects,
        "categories": [{"id": code, "label": label} for code, label in CATEGORIES],
        "sources": sources,
    }


def _profiles(connection: duckdb.DuckDBPyConnection) -> list[dict]:
    frame = connection.sql(f"""
        SELECT aun, lea_name, category, status, county, iu_aun, in_directory
        FROM '{REFINED / "lea.parquet"}'
        ORDER BY county, lea_name
    """).df()
    names = {str(aun): str(name) for aun, name in zip(frame["aun"], frame["lea_name"])}
    profiles = []
    for row in frame.itertuples(index=False):
        iu = None if _missing(row.iu_aun) else str(row.iu_aun)
        profiles.append({
            "aun": str(row.aun),
            "name": str(row.lea_name),
            "county": str(row.county),
            "category": str(row.category or "unknown"),
            "status": str(row.status or "unknown"),
            "iuAun": iu,
            "iuName": names.get(iu),
            "inDirectory": False if _missing(row.in_directory) else bool(row.in_directory),
        })
    return profiles


def _act1_index(connection: duckdb.DuckDBPyConnection) -> dict[str, dict[int, float]]:
    frame = connection.sql(f"""
        SELECT aun, school_year, adjusted_index
        FROM '{REFINED / "act1_index.parquet"}'
    """).df()
    grouped: dict[str, dict[int, float]] = {}
    for row in frame.itertuples(index=False):
        grouped.setdefault(str(row.aun), {})[int(row.school_year)] = _percent_points(row.adjusted_index)
    return grouped


def _act1_base(connection: duckdb.DuckDBPyConnection) -> dict[int, float]:
    frame = connection.sql(f"""
        SELECT school_year, base_index
        FROM '{REFINED / "act1_base.parquet"}'
    """).df()
    return {
        int(row.school_year): _percent_points(row.base_index)
        for row in frame.itertuples(index=False)
    }


def _percent_points(value: object) -> float:
    return round(float(value) * 100, 1)


def _real_estate_tax(connection: duckdb.DuckDBPyConnection) -> dict[str, dict[int, list[dict]]]:
    frame = connection.sql(f"""
        SELECT aun, school_year, county, locality, mills, college_mills
        FROM '{REFINED / "real_estate_tax.parquet"}'
        ORDER BY school_year, aun, county, locality
    """).df()
    grouped: dict[str, dict[int, list[dict]]] = {}
    for row in frame.itertuples(index=False):
        item = {"county": str(row.county), "mills": round(float(row.mills), 4)}
        if not _missing(row.locality):
            item["place"] = str(row.locality)
        if not _missing(row.college_mills):
            item["college"] = round(float(row.college_mills), 4)
        grouped.setdefault(str(row.aun), {}).setdefault(int(row.school_year), []).append(item)
    return grouped


def _nested(connection: duckdb.DuckDBPyConnection, kind: str) -> dict:
    if kind == "grades":
        frame = connection.sql(f"""
            SELECT aun, school_year, grade_code AS key, sum(enrollment)::BIGINT AS amount
            FROM '{REFINED / "enrollment.parquet"}'
            GROUP BY 1, 2, 3
        """).df()
    elif kind == "actual":
        frame = connection.sql(f"""
            SELECT aun, school_year, substr(function_code, 1, 1) || '000' AS key,
                   round(sum(total_amount), 2) AS amount
            FROM '{REFINED / "afr_expenditure.parquet"}'
            WHERE fund_code = '10'
            GROUP BY 1, 2, 3
        """).df()
    else:
        frame = connection.sql(f"""
            SELECT aun, school_year, substr(function_code, 1, 1) || '000' AS key,
                   round(sum(amount), 2) AS amount
            FROM '{REFINED / "gfb_expenditure.parquet"}'
            WHERE fund_code = '10'
            GROUP BY 1, 2, 3
        """).df()
    grouped: dict[str, dict[int, dict]] = {}
    for row in frame.itertuples(index=False):
        grouped.setdefault(str(row.aun), {}).setdefault(int(row.school_year), {})[str(row.key)] = _number(row.amount)
    return grouped


def _detail(connection: duckdb.DuckDBPyConnection, kind: str) -> dict:
    """Finest published function × object amounts.

    GFB budget stops at function × major object. AFR actuals keep the reported
    subfunction and detail object.
    """
    if kind == "budget":
        frame = connection.sql(f"""
            SELECT aun, school_year, function_code, object_code,
                   round(sum(amount), 2) AS amount
            FROM '{REFINED / "gfb_expenditure.parquet"}'
            WHERE fund_code = '10'
              AND function_code IS NOT NULL
              AND object_code IS NOT NULL
            GROUP BY 1, 2, 3, 4
        """).df()
    else:
        frame = connection.sql(f"""
            SELECT aun, school_year, function_code, object_code,
                   round(coalesce(sum(total_amount), 0), 2) AS amount,
                   round(coalesce(sum(elementary_amount), 0), 2) AS elementary_amount,
                   round(coalesce(sum(secondary_amount), 0), 2) AS secondary_amount,
                   round(coalesce(sum(federal_amount), 0), 2) AS federal_amount
            FROM '{REFINED / "afr_expenditure.parquet"}'
            WHERE fund_code = '10'
              AND function_code IS NOT NULL
              AND object_code IS NOT NULL
            GROUP BY 1, 2, 3, 4
        """).df()
    grouped: dict[str, dict[int, dict[str, dict[str, object]]]] = {}
    for row in frame.itertuples(index=False):
        year = grouped.setdefault(str(row.aun), {}).setdefault(int(row.school_year), {})
        if kind == "budget":
            year.setdefault(str(row.function_code), {})[str(row.object_code)] = _number(row.amount)
            continue
        cell: dict[str, float] = {"t": _number(row.amount)}
        elementary = _optional_number(row.elementary_amount)
        secondary = _optional_number(row.secondary_amount)
        federal = _optional_number(row.federal_amount)
        if elementary:
            cell["e"] = elementary
        if secondary:
            cell["s"] = secondary
        if federal:
            cell["f"] = federal
        year.setdefault(str(row.function_code), {})[str(row.object_code)] = cell
    return grouped


def _school_detail(connection: duckdb.DuckDBPyConnection) -> dict:
    """Building × function × object actuals for years PDE published SLFS."""
    frame = connection.sql(f"""
        SELECT aun, school_year, function_code, object_code, school_number,
               max(school_name) FILTER (WHERE school_name IS NOT NULL AND school_name <> '') AS school_name,
               round(sum(total_amount), 2) AS amount
        FROM '{REFINED / "afr_expenditure_school.parquet"}'
        WHERE fund_code = '10'
          AND function_code IS NOT NULL
          AND object_code IS NOT NULL
          AND school_number IS NOT NULL
        GROUP BY 1, 2, 3, 4, 5
    """).df()
    grouped: dict[str, dict[int, dict]] = {}
    names: dict[str, dict[int, dict[str, str]]] = {}
    for row in frame.itertuples(index=False):
        aun = str(row.aun)
        year = int(row.school_year)
        function = str(row.function_code)
        obj = str(row.object_code)
        school = str(row.school_number)
        bucket = grouped.setdefault(aun, {}).setdefault(year, {})
        bucket.setdefault(function, {}).setdefault(obj, {})[school] = _number(row.amount)
        if not _missing(row.school_name):
            names.setdefault(aun, {}).setdefault(year, {})[school] = str(row.school_name)
    for aun, years in grouped.items():
        for year, tree in years.items():
            tree["_names"] = names.get(aun, {}).get(year, {})
    return grouped


def _salaries() -> tuple[dict, dict, dict]:
    """Full-time professional staff salary + experience stats and same-LEA retention."""
    if not SQLITE.exists():
        print("no data/pde.db; salary panel skipped")
        return {}, {}, {}
    frame = pd.read_sql_query(
        """
        SELECT aun, school_year, public_id, annual_salary, edf_category,
               years_in_lea, years_in_education, degree_code
        FROM professional_staff
        WHERE annual_salary > 0
          AND fte_percent = 100
        """,
        sqlite3.connect(SQLITE),
    )
    if frame.empty:
        return {}, {}, {}
    frame["group"] = frame["edf_category"].map(_salary_group)
    frame = frame.loc[frame["group"].notna()].copy()
    frame["aun"] = frame["aun"].map(str)
    frame["school_year"] = frame["school_year"].astype(int)
    frame["public_id"] = frame["public_id"].map(str)
    next_ids = {
        (aun, year): set(ids)
        for (aun, year), ids in frame.groupby(["aun", "school_year"])["public_id"]
    }
    edges = np.asarray(SALARY_EDGES, dtype=float)
    experience_edges = np.asarray(EXPERIENCE_EDGES, dtype=float)
    grouped: dict[str, dict[int, dict]] = {}
    experience: dict[str, dict[int, dict]] = {}
    retention: dict[str, dict[int, dict]] = {}
    for (aun, year), year_frame in frame.groupby(["aun", "school_year"]):
        stayed_ids = next_ids.get((aun, year + 1))
        if stayed_ids is not None:
            base_ids = set(year_frame["public_id"])
            stayed = len(base_ids & stayed_ids)
            retention.setdefault(aun, {})[int(year)] = {
                "rate": _number(stayed / len(base_ids)) if base_ids else None,
                "base": int(len(base_ids)),
                "stayed": int(stayed),
                "nextYear": int(year + 1),
            }
        for group, subset in year_frame.groupby("group"):
            values = subset["annual_salary"].to_numpy(dtype=float)
            counts, _ = np.histogram(values, bins=edges)
            under = int(np.sum(values < edges[0]))
            over = int(np.sum(values >= edges[-1]))
            hist = [under, *[int(count) for count in counts], over]
            bins = _salary_bins(subset, edges)
            payload = {
                "n": int(len(values)),
                "min": _number(values.min()),
                "mean": _number(values.mean()),
                "median": _number(float(np.median(values))),
                "max": _number(values.max()),
                "hist": hist,
                "bins": bins,
                "leaYears": _optional_mean(subset["years_in_lea"]),
                "eduYears": _optional_mean(subset["years_in_education"]),
                "mastersPct": _masters_pct(subset["degree_code"]),
            }
            if stayed_ids is not None:
                group_ids = set(subset["public_id"])
                stayed = len(group_ids & stayed_ids)
                payload["retention"] = _number(stayed / len(group_ids)) if group_ids else None
            grouped.setdefault(aun, {}).setdefault(int(year), {})[str(group)] = payload
            experience_payload = {
                "lea": _experience_stats(subset, "years_in_lea", "years_in_education", experience_edges),
                "edu": _experience_stats(subset, "years_in_education", "years_in_lea", experience_edges),
            }
            if experience_payload["lea"] or experience_payload["edu"]:
                experience.setdefault(aun, {}).setdefault(int(year), {})[str(group)] = {
                    key: value for key, value in experience_payload.items() if value
                }
    print(f"salary stats for {len(grouped)} LEAs")
    return grouped, experience, retention


def _salary_bins(subset: pd.DataFrame, edges: np.ndarray) -> list[dict | None]:
    indexes = np.digitize(subset["annual_salary"].to_numpy(dtype=float), edges)
    bins: list[dict | None] = [None] * (len(edges) + 1)
    for index in range(len(edges) + 1):
        members = subset.loc[indexes == index]
        if members.empty:
            continue
        bins[index] = {
            "n": int(len(members)),
            "leaYears": _optional_mean(members["years_in_lea"]),
            "eduYears": _optional_mean(members["years_in_education"]),
            "mastersPct": _masters_pct(members["degree_code"]),
        }
    return bins


def _experience_stats(
    subset: pd.DataFrame,
    column: str,
    other_column: str,
    edges: np.ndarray,
) -> dict | None:
    """Histogram and summary for years_in_lea or years_in_education."""
    values = pd.to_numeric(subset[column], errors="coerce")
    usable = subset.loc[values.notna()].copy()
    if usable.empty:
        return None
    years = values.loc[values.notna()].to_numpy(dtype=float)
    counts, _ = np.histogram(years, bins=edges)
    under = int(np.sum(years < edges[0]))
    over = int(np.sum(years >= edges[-1]))
    hist = [under, *[int(count) for count in counts], over]
    return {
        "n": int(len(years)),
        "min": _number(years.min()),
        "mean": _number(years.mean()),
        "median": _number(float(np.median(years))),
        "max": _number(years.max()),
        "hist": hist,
        "bins": _experience_bins(usable, column, other_column, edges),
    }


def _experience_bins(
    subset: pd.DataFrame,
    column: str,
    other_column: str,
    edges: np.ndarray,
) -> list[dict | None]:
    values = pd.to_numeric(subset[column], errors="coerce").to_numpy(dtype=float)
    indexes = np.digitize(values, edges)
    bins: list[dict | None] = [None] * (len(edges) + 1)
    for index in range(len(edges) + 1):
        members = subset.loc[indexes == index]
        if members.empty:
            continue
        other_key = "eduYears" if other_column == "years_in_education" else "leaYears"
        bins[index] = {
            "n": int(len(members)),
            "meanSalary": _optional_mean(members["annual_salary"]),
            other_key: _optional_mean(members[other_column]),
            "mastersPct": _masters_pct(members["degree_code"]),
        }
    return bins


def _optional_mean(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return None
    return _number(float(values.mean()))


def _masters_pct(series: pd.Series) -> float | None:
    codes = series.dropna().astype(str)
    if codes.empty:
        return None
    return _number(100.0 * codes.isin(MASTERS_PLUS).mean())


def _charter_tuition(connection: duckdb.DuckDBPyConnection) -> dict:
    """Tuition paid to PA charter/cyber schools (object 562). Kept out of per-student cost."""
    frame = connection.sql(f"""
        SELECT aun, school_year, round(sum(total_amount), 2) AS amount
        FROM '{REFINED / "afr_expenditure.parquet"}'
        WHERE fund_code = '10' AND object_code = '562'
        GROUP BY 1, 2
    """).df()
    grouped: dict[str, dict[int, float]] = {}
    for row in frame.itertuples(index=False):
        grouped.setdefault(str(row.aun), {})[int(row.school_year)] = _number(row.amount)
    return grouped


def _charter_adm(connection: duckdb.DuckDBPyConnection) -> dict:
    """Resident students of an SD attending charter schools (ADM)."""
    path = REFINED / "charter_adm.parquet"
    if not path.exists():
        return {}
    frame = connection.sql(f"""
        SELECT aun, school_year, adm
        FROM '{path}'
        WHERE adm IS NOT NULL
    """).df()
    grouped: dict[str, dict[int, float]] = {}
    for row in frame.itertuples(index=False):
        grouped.setdefault(str(row.aun), {})[int(row.school_year)] = _number(row.adm)
    return grouped


def _home_education(connection: duckdb.DuckDBPyConnection) -> dict:
    """Home-education student total by resident school district."""
    path = REFINED / "home_education.parquet"
    if not path.exists():
        return {}
    frame = connection.sql(f"""
        SELECT aun, school_year, students
        FROM '{path}'
        WHERE students IS NOT NULL
    """).df()
    grouped: dict[str, dict[int, float]] = {}
    for row in frame.itertuples(index=False):
        grouped.setdefault(str(row.aun), {})[int(row.school_year)] = _number(row.students)
    return grouped


def _low_income(connection: duckdb.DuckDBPyConnection) -> dict:
    """LEA-level economically disadvantaged (low-income) October 1 counts."""
    path = REFINED / "enrollment_low_income.parquet"
    if not path.exists():
        return {}
    frame = connection.sql(f"""
        SELECT aun, school_year, low_income_enrollment, total_enrollment, pct_low_income
        FROM '{path}'
        WHERE low_income_enrollment IS NOT NULL
    """).df()
    grouped: dict[str, dict[int, dict]] = {}
    for row in frame.itertuples(index=False):
        cell = {"n": int(row.low_income_enrollment)}
        if row.total_enrollment is not None and not _missing(row.total_enrollment):
            cell["total"] = int(row.total_enrollment)
        if row.pct_low_income is not None and not _missing(row.pct_low_income):
            cell["pct"] = _number(row.pct_low_income)
        grouped.setdefault(str(row.aun), {})[int(row.school_year)] = cell
    return grouped


def _iep(connection: duckdb.DuckDBPyConnection) -> dict:
    """LEA-level December 1 school-age special education (IEP) counts."""
    path = REFINED / "enrollment_iep.parquet"
    if not path.exists():
        return {}
    frame = connection.sql(f"""
        SELECT aun, school_year, iep_enrollment, total_enrollment, pct_iep
        FROM '{path}'
        WHERE iep_enrollment IS NOT NULL
    """).df()
    grouped: dict[str, dict[int, dict]] = {}
    for row in frame.itertuples(index=False):
        cell = {"n": int(row.iep_enrollment)}
        if row.total_enrollment is not None and not _missing(row.total_enrollment):
            cell["total"] = int(row.total_enrollment)
        if row.pct_iep is not None and not _missing(row.pct_iep):
            cell["pct"] = _number(row.pct_iep)
        grouped.setdefault(str(row.aun), {})[int(row.school_year)] = cell
    return grouped


def _cohort_graduation(connection: duckdb.DuckDBPyConnection) -> dict:
    """LEA cohort rates. `rate` is the published fraction, including a real zero."""
    path = REFINED / "cohort_graduation.parquet"
    if not path.exists():
        return {}
    frame = connection.sql(f"""
        SELECT aun, school_year, span, graduates, cohort, rate
        FROM '{path}'
        WHERE graduates IS NOT NULL AND cohort IS NOT NULL AND rate IS NOT NULL
    """).df()
    grouped: dict[str, dict[int, dict]] = {}
    for row in frame.itertuples(index=False):
        grouped.setdefault(str(row.aun), {}).setdefault(int(row.school_year), {})[str(int(row.span))] = {
            "grads": int(row.graduates),
            "cohort": int(row.cohort),
            "rate": float(row.rate),
        }
    groups_path = REFINED / "cohort_graduation_group.parquet"
    if not groups_path.exists():
        return grouped
    groups = connection.sql(f"""
        SELECT aun, school_year, span, student_group, rate
        FROM '{groups_path}'
        WHERE rate IS NOT NULL
    """).df()
    for row in groups.itertuples(index=False):
        block = grouped.setdefault(str(row.aun), {}).setdefault(int(row.school_year), {})
        (
            block.setdefault("groups", {})
            .setdefault(str(int(row.span)), {})[str(row.student_group)]
        ) = float(row.rate)
    return grouped


def _salary_group(edf_category: object) -> str | None:
    code = "" if edf_category is None else str(edf_category).strip().upper()
    if code in {"ELMTCH", "KGTCH", "PKTCH"}:
        return "elementary"
    if code == "SECTCH":
        return "secondary"
    if code in {"SCHADM", "LEAADM", "CORSUP"}:
        return "administrator"
    if code == "UGTCH":
        return "ungraded"
    if code in SALARY_LABEL_GROUPS:
        return SALARY_LABEL_GROUPS[code]
    if code:
        return "support"
    return None


GENDER_LABELS = {
    "F": "Female",
    "FEMALE": "Female",
    "M": "Male",
    "MALE": "Male",
}
PSSA_GROUPS = {
    "All Students",
    "Economically Disadvantaged",
    "Hispanic (any race)",
    "IEP",
    "ELL",
    "White (not Hispanic)",
    "Black or African American (not Hispanic)",
    "Asian (not Hispanic)",
    "Multi-ethnic (not Hispanic)",
    "Female",
    "Male",
}
PSSA_GRADES = {"total", "003", "004", "005", "006", "007", "008"}


def _enrollment_dim(connection: duckdb.DuckDBPyConnection, filename: str, column: str) -> dict:
    path = REFINED / filename
    if not path.exists():
        return {}
    frame = connection.sql(f"""
        SELECT aun, school_year, {column} AS key, sum(enrollment)::BIGINT AS amount
        FROM '{path}'
        WHERE {column} IS NOT NULL AND {column} <> ''
        GROUP BY 1, 2, 3
    """).df()
    grouped: dict[str, dict[int, dict[str, int]]] = {}
    for row in frame.itertuples(index=False):
        key = str(row.key).strip()
        if column == "gender":
            key = GENDER_LABELS.get(key.upper(), key.title())
        amount = int(row.amount)
        if amount <= 0:
            continue
        bucket = grouped.setdefault(str(row.aun), {}).setdefault(int(row.school_year), {})
        bucket[key] = bucket.get(key, 0) + amount
    return grouped


def _assessment(connection: duckdb.DuckDBPyConnection, assessment: str) -> dict:
    path = REFINED / "assessment_result.parquet"
    if not path.exists():
        return {}
    frame = connection.sql(f"""
        SELECT aun, school_year, subject, grade, student_group,
               number_scored, pct_proficient_and_above
        FROM '{path}'
        WHERE assessment = '{assessment}'
          AND subject IN ('math', 'ela')
          AND grade IN ('total', '003', '004', '005', '006', '007', '008')
          AND student_group IN (
            'All Students', 'Economically Disadvantaged', 'Hispanic (any race)',
            'IEP', 'ELL', 'White (not Hispanic)',
            'Black or African American (not Hispanic)', 'Asian (not Hispanic)',
            'Multi-ethnic (not Hispanic)', 'Female', 'Male'
          )
    """).df()
    grouped: dict[str, dict[int, dict[str, dict[str, dict[str, dict]]]]] = {}
    for row in frame.itertuples(index=False):
        if str(row.grade) not in PSSA_GRADES or str(row.student_group) not in PSSA_GROUPS:
            continue
        cell: dict[str, object] = {}
        if not _missing(row.number_scored):
            cell["n"] = int(row.number_scored)
        if not _missing(row.pct_proficient_and_above):
            cell["pct"] = round(float(row.pct_proficient_and_above), 1)
        if not cell:
            continue
        (
            grouped.setdefault(str(row.aun), {})
            .setdefault(int(row.school_year), {})
            .setdefault(str(row.subject), {})
            .setdefault(str(row.grade), {})[str(row.student_group)]
        ) = cell
    return grouped


def _keystone(connection: duckdb.DuckDBPyConnection) -> dict:
    """Grade 11 Keystone proficiency: Algebra I, Literature, and Biology.

    2022 and 2023 workbooks label multi-ethnic students "Multi-Racial".
    Later files, and the PSSA files, say "Multi-ethnic". Store one name.
    """
    path = REFINED / "assessment_result.parquet"
    if not path.exists():
        return {}
    groups = ", ".join("'" + name.replace("'", "''") + "'" for name in sorted(PSSA_GROUPS | {"Multi-Racial (not Hispanic)"}))
    frame = connection.sql(f"""
        SELECT aun, school_year, subject, grade,
               CASE student_group
                 WHEN 'Multi-Racial (not Hispanic)' THEN 'Multi-ethnic (not Hispanic)'
                 ELSE student_group
               END AS student_group,
               number_scored, pct_proficient_and_above,
               pct_advanced, pct_proficient, pct_basic, pct_below_basic
        FROM '{path}'
        WHERE assessment = 'keystone'
          AND subject IN ('algebra_i', 'biology', 'literature')
          AND grade = '011'
          AND student_group IN ({groups})
    """).df()
    grouped: dict[str, dict[int, dict[str, dict[str, dict[str, dict]]]]] = {}
    for row in frame.itertuples(index=False):
        if str(row.student_group) not in PSSA_GROUPS:
            continue
        cell: dict[str, object] = {}
        if not _missing(row.number_scored):
            cell["n"] = int(row.number_scored)
        if not _missing(row.pct_proficient_and_above):
            cell["pct"] = round(float(row.pct_proficient_and_above), 1)
        if not _missing(row.pct_advanced):
            cell["advanced"] = round(float(row.pct_advanced), 1)
        if not _missing(row.pct_proficient):
            cell["proficient"] = round(float(row.pct_proficient), 1)
        if not _missing(row.pct_basic):
            cell["basic"] = round(float(row.pct_basic), 1)
        if not _missing(row.pct_below_basic):
            cell["below"] = round(float(row.pct_below_basic), 1)
        if not cell:
            continue
        (
            grouped.setdefault(str(row.aun), {})
            .setdefault(int(row.school_year), {})
            .setdefault(str(row.subject), {})
            .setdefault(str(row.grade), {})[str(row.student_group)]
        ) = cell
    return grouped


def _schools(connection: duckdb.DuckDBPyConnection) -> dict:
    frame = connection.sql(f"""
        SELECT aun, school_year, school_number,
               max(school_name) FILTER (WHERE school_name IS NOT NULL AND school_name <> '') AS school_name,
               sum(enrollment)::BIGINT AS enrollment
        FROM '{REFINED / "enrollment.parquet"}'
        GROUP BY 1, 2, 3
    """).df()
    grouped: dict[str, dict[int, list]] = {}
    for row in frame.itertuples(index=False):
        number = "" if _missing(row.school_number) else str(row.school_number)
        name = row.school_name if not _missing(row.school_name) else f"School {number}"
        grouped.setdefault(str(row.aun), {}).setdefault(int(row.school_year), []).append({
            "number": number,
            "name": str(name),
            "enrollment": int(row.enrollment),
        })
    for years in grouped.values():
        for rows in years.values():
            rows.sort(key=lambda school: (-school["enrollment"], school["name"]))
    return grouped


def _max_year(connection: duckdb.DuckDBPyConnection, name: str) -> int:
    value = connection.sql(f"SELECT max(school_year) FROM '{REFINED / name}'").fetchall()[0][0]
    return int(value)


def _number(value: object) -> int | float:
    number = float(value)
    if number != number:  # NaN
        return 0
    if number.is_integer():
        return int(number)
    return round(number, 2)


def _optional_number(value: object) -> float | None:
    if value is None or _missing(value):
        return None
    number = float(value)
    if number != number or number == 0:
        return None
    return _number(number)


def _missing(value: object) -> bool:
    if value is None:
        return True
    text = str(value)
    return text in {"", "None", "nan", "<NA>"}


def _short_title(value: object) -> str:
    text = " ".join(str(value).replace("–", "-").replace("—", "-").split())
    if " - " in text:
        head, tail = text.split(" - ", 1)
        # "SUPPORT SERVICES – STUDENTS" is the chart heading. The words before
        # the dash repeat the 2000 major; the words after are the account.
        if head.casefold() == "support services" and tail.strip():
            text = tail.strip()
        else:
            text = head
    if len(text) > 48:
        text = text[:45].rstrip() + "…"
    return text


if __name__ == "__main__":
    main()
