"""Write the static LEA browser for https://pdenumbers.org.

`python -m pa_edu.publish` reads `data/refined/*.parquet` and writes `pde_site/`.
LEA JSON is stored gzipped (`index.json.gz`, `lea/<aun>.json.gz`). nginx
`gzip_static` serves those for the `.json` URLs. Jenkins builds that directory
into an image, pushes it, and replaces the container on docker09. The download
portal is `pde_site/download/`. Its DuckDB views read the Parquet already
published at https://pdenumbers.org. `build.json` records the git commit and
when publish finished. The footer shows those times in US/Eastern.
"""

from __future__ import annotations

import gzip
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import requests

from pa_edu.common import DATA_DIR, ROOT
from pa_edu.portal import DUCKDB_NAME, PUBLIC_TABLE_ROOT, build_portal, load_views, write_duckdb

OUT = ROOT / "pde_site"
WEB = Path(__file__).resolve().parent / "web"
REPO_URL = "https://github.com/bobruddy/pa_education_data"
REFINED = DATA_DIR / "refined"
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
AFR_PAGE = (
    "https://www.pa.gov/agencies/education/programs-and-services/schools/"
    "grants-and-funding/school-finances/financial-data/"
    "summary-of-annual-financial-report-data/afr-data-summary-level"
)
GFB_PAGE = (
    "https://www.pa.gov/agencies/education/programs-and-services/schools/"
    "grants-and-funding/school-finances/financial-data/general-fund-budget-gfb-data"
)
ACT1_PAGE = (
    "https://www.pa.gov/agencies/education/programs-and-services/schools/"
    "grants-and-funding/property-tax-relief/act-1-index"
)
IEP_PAGE = "https://penndata.hbg.psu.edu/Additional-Reports"
SALARY_GROUPS = [
    ("elementary", "Elementary teachers"),
    ("secondary", "Secondary teachers"),
    ("administrator", "Administrators"),
    ("support", "Professional support"),
    ("ungraded", "Ungraded teachers"),
]
# Classroom educators: teachers only. Administrators and professional support stay out.
CLASSROOM_GROUPS = ("elementary", "secondary", "ungraded")
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
REVENUE_MAJORS = [
    ("6000", "Local"),
    ("7000", "State"),
    ("8000", "Federal"),
    ("9000", "Other financing sources"),
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
                "incomeActual",
                "incomeBudget",
                "budgetDetail",
                "actualDetail",
                "actualSchool",
                "salaries",
                "experience",
                "retention",
                "charterTuition",
                "object562",
                "debtService",
                "countyRanks",
                "act1",
                "act1Base",
                "mills",
                "keystone",
                "pssa",
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
    global REFINED
    REFINED = resolve_refined()
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
    income_actual = _income_actual(connection)
    income_budget = _income_budget(connection)
    salaries, experience, retention = _salaries()
    lea_administrators = _lea_administrators()
    charter = _charter_tuition(connection)
    charter_adm = _charter_adm(connection)
    home_education = _home_education(connection)
    district_population = _district_population(connection)
    low_income = _low_income(connection)
    iep = _iep(connection)
    graduation = _cohort_graduation(connection)
    act1 = _act1_index(connection)
    act1_base = _act1_base(connection)
    mills = _real_estate_tax(connection)
    debt_service = _debt_service(connection)
    ranks = _county_ranks(
        profiles, grades, actual, budget, charter, keystone, pssa, graduation,
        salaries, retention, lea_administrators, debt_service, district_population,
    )
    enrollment_year = catalog["enrollmentYear"]
    actual_year = catalog["actualYear"]
    budget_year = catalog["budgetYear"]
    catalog["salaryYear"] = max((year for years in salaries.values() for year in years), default=None)
    catalog["salaryGroups"] = [{"id": code, "label": label} for code, label in SALARY_GROUPS]
    catalog["classroomGroups"] = list(CLASSROOM_GROUPS)
    catalog["salaryEdges"] = SALARY_EDGES
    catalog["experienceEdges"] = EXPERIENCE_EDGES
    catalog["experienceModes"] = [{"id": code, "label": label} for code, label in EXPERIENCE_MODES]
    catalog["sources"]["personnel"] = PERSONNEL_PAGE

    if OUT.exists():
        shutil.rmtree(OUT)
    data_dir = OUT / "data" / "lea"
    data_dir.mkdir(parents=True)
    for name in ("index.html", "app.css", "app.js", "stamp.js"):
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
                income_actual,
                income_budget,
                lea_administrators,
                debt_service,
                district_population,
                category=profile["category"],
            ),
        )
        _write_json(data_dir / f"{aun}.json", document)
        snapshot = document["years"]
        rows.append(directory_row(
            profile,
            _total(snapshot.get(str(enrollment_year), {}).get("grades")),
            _total(snapshot.get(str(actual_year), {}).get("actual")),
            _total(snapshot.get(str(budget_year), {}).get("budget")),
        ))
    payload = {**catalog, "leas": rows}
    _write_json(OUT / "data" / "index.json", payload)
    build_portal(OUT / "download", REFINED)
    print(f"wrote {OUT} ({len(rows)} LEAs)")
    manifest = json.loads((OUT / "download" / "manifest.json").read_text(encoding="utf-8"))
    write_duckdb(
        OUT / "download" / DUCKDB_NAME,
        PUBLIC_TABLE_ROOT,
        [item["name"] for item in manifest["tables"]],
        schema_from=OUT / "download" / "tables",
    )
    print(f"wrote {OUT / 'download' / DUCKDB_NAME}")
    stamp = write_build_stamp(OUT)
    print(f"build {stamp['commitShort']} generated {stamp['generatedAt']}")


def resolve_refined() -> Path:
    """Local refined tables, or a copy read from the data service with httpfs.

    ``PDE_REFINED_URL`` is the service root, without a trailing slash, such as
    ``http://192.168.10.116:8091/refined``. Unset, publish reads ``data/refined``.
    """
    url = os.environ.get("PDE_REFINED_URL", "").strip().rstrip("/")
    if not url:
        return DATA_DIR / "refined"
    response = requests.get(f"{url}/", timeout=120)
    response.raise_for_status()
    names = response.json()["tables"]
    stage = Path(tempfile.mkdtemp(prefix="pde-refined-"))
    connection = duckdb.connect()
    try:
        connection.execute("INSTALL httpfs; LOAD httpfs;")
        for name in names:
            if not isinstance(name, str) or "/" in name or not name.endswith(".parquet"):
                raise RuntimeError(f"refined listing has unexpected name {name!r}")
            temporary = stage / f".{name}.tmp"
            source = f"{url}/{name}"
            connection.execute(
                f"COPY (SELECT * FROM read_parquet({_sql_quote(source)})) "
                f"TO {_sql_quote(temporary.as_posix())} (FORMAT PARQUET)"
            )
            os.replace(temporary, stage / name)
    finally:
        connection.close()
    print(f"read {len(names)} refined tables from {url}")
    return stage


def _sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def read_git_build(now: datetime | None = None) -> dict[str, str]:
    """Commit identity plus the UTC time this publish finished."""
    commit = _git("rev-parse", "HEAD")
    committed_at = _git("log", "-1", "--format=%aI")
    if now is None:
        generated = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        generated = now.replace(tzinfo=timezone.utc)
    else:
        generated = now.astimezone(timezone.utc)
    return {
        "commit": commit,
        "commitShort": commit[:7],
        "commitUrl": f"{REPO_URL}/commit/{commit}",
        "committedAt": committed_at,
        "generatedAt": generated.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def write_build_stamp(out: Path, stamp: dict[str, str] | None = None) -> dict[str, str]:
    payload = read_git_build() if stamp is None else stamp
    _write_json(out / "build.json", payload)
    return payload


def _git(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = (exc.stderr or "").strip() if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        raise SystemExit(f"git {' '.join(args)} failed: {detail or exc}") from exc
    value = result.stdout.strip()
    if not value:
        raise SystemExit(f"git {' '.join(args)} returned nothing")
    return value


# Level 1. nginx gzip_static serves the body; the higher levels dominated publish.
JSON_GZIP_LEVEL = 1


def _write_json(path: Path, payload: dict) -> None:
    """Store JSON as ``path`` plus ``.gz`` for nginx ``gzip_static``.

    The browser still requests ``path``. nginx responds with
    ``Content-Encoding: gzip`` and the browser inflates it.
    """
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    path.with_name(path.name + ".gz").write_bytes(
        gzip.compress(body, compresslevel=JSON_GZIP_LEVEL, mtime=0)
    )
    path.unlink(missing_ok=True)


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
    income_actual: dict | None = None,
    income_budget: dict | None = None,
    lea_administrators: dict | None = None,
    debt_service: dict | None = None,
    district_population: dict | None = None,
    category: str | None = None,
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
    income_actual = income_actual or {}
    income_budget = income_budget or {}
    lea_administrators = lea_administrators or {}
    debt_service = debt_service or {}
    district_population = district_population or {}
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
            # Per-student cost treats a published AFR with no object 562 as zero.
            # object562 is only the rows PDE actually published, including a real zero.
            "charterTuition": (
                charter_years.get(year, 0.0) if year in actual_years else charter_years.get(year)
            ),
            "countyRanks": ranks.get(aun, {}).get(year, {}),
        }
        published_562 = charter_years.get(year)
        if published_562 is not None:
            block["object562"] = published_562
        # AFR function 5110. A missing function stays off the block; a reported
        # zero stays zero. It does not open a year by itself.
        service = debt_service.get(aun, {}).get(year)
        if service is not None:
            block["debtService"] = service
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
        # Census SAIPE rides on a year that already exists, and only for a
        # school district. A missing count stays off the block; a reported
        # zero stays zero. It does not open a year by itself.
        if category == "school_district":
            saipe = district_population.get(aun, {}).get(year) or {}
            ages = _whole_count(saipe.get("population_5_17"))
            if ages is not None:
                block["population517"] = ages
            poverty = _whole_count(saipe.get("children_5_17_in_poverty"))
            if poverty is not None:
                block["children517InPoverty"] = poverty
        low = low_income.get(aun, {}).get(year)
        if low is not None:
            block["lowIncome"] = low
        iep_cell = iep.get(aun, {}).get(year)
        if iep_cell is not None:
            block["iep"] = iep_cell
        grad = graduation.get(aun, {}).get(year)
        if grad:
            block["graduation"] = grad
        # Revenue rides on a year that already exists. It does not open a year.
        actual_income = income_actual.get(aun, {}).get(year)
        if actual_income:
            block["incomeActual"] = actual_income
        budget_income = income_budget.get(aun, {}).get(year)
        if budget_income:
            block["incomeBudget"] = budget_income
        # Full-time LEAADM headcount, plus the jobs and the sum of reported
        # pay when the staff file has them. A missing count stays absent.
        admins = _lea_admin_block(lea_administrators.get(aun, {}).get(year))
        if admins:
            block["leaAdministrators"] = admins
        blocks[year] = block
    return blocks


def _charter_as_of(amounts: dict, year: int) -> float:
    """Object 562 for this year, or the latest earlier year when that AFR is not in yet."""
    published = _published_charter(amounts, year)
    if published is None:
        return 0.0
    return published[0] or 0.0


def _published_charter(amounts: dict, year: int) -> tuple[float, int] | None:
    """Object 562 and the school year it was published.

    Same-year rows win, including a reported zero. A missing object is absence,
    so the search continues to the latest earlier year that did publish one.
    Nothing published is None, not zero.
    """
    if not amounts:
        return None
    if year in amounts and amounts[year] is not None:
        return float(amounts[year]), year
    earlier = [item for item in amounts if item < year and amounts[item] is not None]
    if not earlier:
        return None
    found = max(earlier)
    return float(amounts[found]), found


def _classroom_n(groups: dict | None) -> int | None:
    """Full-time elementary, secondary, and ungraded teachers. Admins and support stay out."""
    if not groups:
        return None
    total = 0
    found = False
    for name in CLASSROOM_GROUPS:
        stats = groups.get(name)
        if not isinstance(stats, dict) or stats.get("n") is None:
            continue
        found = True
        total += int(stats["n"])
    return total if found else None


def _group_median(groups: dict | None, name: str) -> float | None:
    stats = (groups or {}).get(name) or {}
    if not stats.get("n") or stats.get("median") is None:
        return None
    return float(stats["median"])


def _ages517_share(enrolled: object, population: object) -> float | None:
    """October 1 enrollment as a percent of Census ages 5–17.

    Missing enrollment or population is absence. A zero population is not a rate.
    A reported zero enrollment over a positive population is 0%. The percent is
    not capped: district enrollment can exceed resident ages 5–17.
    """
    if enrolled is None or population is None or _missing(enrolled) or _missing(population):
        return None
    students = float(enrolled)
    residents = float(population)
    if students != students or residents != residents or residents <= 0:
        return None
    return round(students / residents * 100, 4)


def _latest_population_5_17(years: dict | None, year: int) -> int | None:
    """Latest published ages 5–17 count at or before ``year``.

    A later Census file stays with its own year. A reported zero is the latest
    count and is not replaced by an older one.
    """
    if not years:
        return None
    found = [
        item
        for item in years
        if item <= year and (years[item] or {}).get("population_5_17") is not None
    ]
    if not found:
        return None
    return (years[max(found)] or {}).get("population_5_17")


def _county_ranks(
    profiles: list[dict],
    grades: dict,
    actual: dict,
    budget: dict,
    charter: dict,
    keystone: dict | None = None,
    pssa: dict | None = None,
    graduation: dict | None = None,
    salaries: dict | None = None,
    retention: dict | None = None,
    lea_administrators: dict | None = None,
    debt_service: dict | None = None,
    district_population: dict | None = None,
) -> dict:
    """Rank each LEA against others in its county for the top-card metrics."""
    keystone = keystone or {}
    pssa = pssa or {}
    graduation = graduation or {}
    salaries = salaries or {}
    retention = retention or {}
    lea_administrators = lea_administrators or {}
    debt_service = debt_service or {}
    district_population = district_population or {}
    by_county: dict[str, list[dict]] = {}
    for profile in profiles:
        by_county.setdefault(profile["county"], []).append(profile)

    years: set[int] = set()
    for nested in (grades, actual, budget, keystone, pssa, graduation, salaries, retention, debt_service):
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
                "studentsPerTeacher": [],
                "classroomRetention": [],
                "elementaryMedian": [],
                "secondaryMedian": [],
                "ungradedMedian": [],
                "leaAdmPerThousand": [],
                "charterShare": [],
                "debtPerStudent": [],
                "instructionPerStudent": [],
                "ages517Share": [],
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
                staff = salaries.get(aun, {}).get(year) or {}
                teachers = _classroom_n(staff)
                if enrolled and teachers:
                    buckets["studentsPerTeacher"].append({
                        **row,
                        "value": round(enrolled / teachers, 4),
                    })
                for metric, group in (
                    ("elementaryMedian", "elementary"),
                    ("secondaryMedian", "secondary"),
                    ("ungradedMedian", "ungraded"),
                ):
                    median = _group_median(staff, group)
                    if median is not None:
                        buckets[metric].append({**row, "value": median})
                classroom = (retention.get(aun, {}).get(year) or {}).get("classroom") or {}
                if classroom.get("rate") is not None and classroom.get("base"):
                    buckets["classroomRetention"].append({
                        **row,
                        "value": round(float(classroom["rate"]) * 100, 4),
                    })
                if profile.get("category") != "intermediate_unit":
                    per_thousand = _lea_admins_per_thousand(
                        _lea_admin_headcount(lea_administrators.get(aun, {}).get(year)),
                        enrolled,
                    )
                    if per_thousand is not None:
                        buckets["leaAdmPerThousand"].append({**row, "value": per_thousand})
                # School districts only. October 1 enrollment over the latest Census
                # ages 5–17 count published through this year. A missing count or a
                # zero population is left out, not ranked as zero.
                if profile.get("category") == "school_district":
                    population = _latest_population_5_17(district_population.get(aun), year)
                    share = _ages517_share(enrolled, population)
                    if share is not None:
                        buckets["ages517Share"].append({**row, "value": share})
                # Charter share is same-year object 562 over that year's general-fund
                # actual. School districts only. A budget year is not ranked,
                # and a missing 562 is left out rather than filled from an earlier year.
                if profile.get("category") == "school_district" and spent is not None and spent != 0:
                    amount = charter.get(aun, {}).get(year)
                    if amount is not None:
                        buckets["charterShare"].append({
                            **row,
                            "value": round(float(amount) / spent * 100, 4),
                        })
                if enrolled:
                    service = debt_service.get(aun, {}).get(year)
                    if service is not None:
                        buckets["debtPerStudent"].append({
                            **row,
                            "value": _number(float(service) / enrolled),
                        })
                    instruction = (budget.get(aun, {}).get(year) or {}).get("1000")
                    if instruction is not None:
                        buckets["instructionPerStudent"].append({
                            **row,
                            "value": _number(float(instruction) / enrolled),
                        })
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
        "pssa": {}, "pssaSchool": {}, "keystone": {}, "assessment": ASSESSMENT_PAGE,
        "enrollmentPage": ENROLLMENT_PAGE,
        "admPage": ADM_PAGE,
        "charterAdm": {}, "homeEducation": {}, "lowIncome": {}, "iep": None,
        "iepPage": IEP_PAGE,
        "afrPage": AFR_PAGE, "gfbPage": GFB_PAGE, "act1Page": ACT1_PAGE,
        "saipe": {}, "saipePage": {},
        "cohortGrad": {}, "graduationPage": GRADUATION_PAGE,
        "personnelWorkbooks": {},
        "chart": None,
    }
    frame = connection.sql(f"""
        SELECT parser, school_year, source_url, page_url, catalog_id
        FROM (
            SELECT parser, school_year, source_url, page_url, catalog_id,
                   row_number() OVER (PARTITION BY catalog_id ORDER BY retrieved_at DESC) AS n
            FROM '{REFINED / "document.parquet"}'
        )
        WHERE n = 1 AND parser IN (
            'enrollment', 'afr', 'gfb', 'edna', 'act1', 'act1_base', 'retax', 'pssa', 'pssa_school', 'keystone',
            'charter_adm', 'homeschool', 'low_income', 'iep', 'cohort_grad', 'chart', 'personnel',
            'saipe'
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
        elif row.parser == "saipe" and row.school_year is not None and not _missing(row.school_year):
            year = str(int(row.school_year))
            sources["saipe"][year] = row.source_url
            if not _missing(row.page_url):
                sources["saipePage"][year] = row.page_url
        elif row.parser == "cohort_grad" and row.school_year is not None and not _missing(row.school_year):
            span = str(row.catalog_id).rsplit("-", 1)[-1]
            if span in {"4", "5", "6"}:
                sources["cohortGrad"].setdefault(str(int(row.school_year)), {})[span] = row.source_url
        elif (
            row.parser == "personnel"
            and not _missing(row.school_year)
            and not _missing(row.source_url)
        ):
            sources["personnelWorkbooks"][str(int(row.school_year))] = row.source_url
        elif row.parser == "pssa_school" and row.school_year is not None and not _missing(row.school_year):
            sources["pssaSchool"][str(int(row.school_year))] = row.source_url
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
        "revenueMajors": [{"code": code, "label": label} for code, label in REVENUE_MAJORS],
        "revenueNames": _revenue_names(connection),
        **_chart_descriptions(connection),
        "categories": [{"id": code, "label": label} for code, label in CATEGORIES],
        "sources": sources,
    }


def _chart_descriptions(connection: duckdb.DuckDBPyConnection) -> dict[str, dict[str, str]]:
    """Chart headings and prose, each keyed by code.

    A code with no heading is left out of the heading map. A code with no
    paragraph is left out of the description map.
    """
    keys = {
        "function": ("functionDescriptions", "functionHeadings"),
        "object": ("objectDescriptions", "objectHeadings"),
        "revenue": ("revenueDescriptions", "revenueHeadings"),
    }
    grouped = {name: {} for pair in keys.values() for name in pair}
    path = REFINED / "chart_description.parquet"
    if not path.exists():
        return grouped
    frame = connection.sql(f"SELECT * FROM '{path}'").df()
    has_name = "name" in frame.columns
    for row in frame.itertuples(index=False):
        pair = keys.get(str(row.kind))
        if pair is None:
            raise RuntimeError(f"chart description kind {row.kind!r} is not function, object, or revenue")
        descriptions, headings = pair
        if not _missing(row.description):
            grouped[descriptions][str(row.code)] = str(row.description)
        if has_name and not _missing(getattr(row, "name", None)):
            grouped[headings][str(row.code)] = str(row.name)
    return grouped


def _revenue_names(connection: duckdb.DuckDBPyConnection) -> dict[str, str]:
    frame = connection.sql(f"""
        SELECT account_code, name
        FROM '{REFINED / "revenue_account.parquet"}'
        WHERE name IS NOT NULL
    """).df()
    return {
        str(row.account_code): _short_title(row.name)
        for row in frame.itertuples(index=False)
        if not _missing(row.name)
    }


def _revenue_chain(*codes: object) -> list[str]:
    chain = []
    for value in codes:
        if _missing(value):
            continue
        text = str(value)
        if text not in chain:
            chain.append(text)
    return chain


def _income_cell(amount: object, *rollups: object) -> dict:
    cell: dict = {"a": _number(amount)}
    chain = _revenue_chain(*rollups)
    if chain:
        cell["p"] = chain
    return cell


def _income_actual(connection: duckdb.DuckDBPyConnection) -> dict:
    frame = connection.sql(f"""
        SELECT aun, school_year, account_code,
               round(sum(amount), 2) AS amount,
               any_value(rollup1_account_code) AS rollup1_account_code,
               any_value(rollup2_account_code) AS rollup2_account_code,
               any_value(rollup3_account_code) AS rollup3_account_code
        FROM '{REFINED / "afr_revenue.parquet"}'
        WHERE fund_code = '10'
        GROUP BY 1, 2, 3
        HAVING round(sum(amount), 2) != 0
    """).df()
    grouped: dict[str, dict[int, dict]] = {}
    for row in frame.itertuples(index=False):
        grouped.setdefault(str(row.aun), {}).setdefault(int(row.school_year), {})[str(row.account_code)] = (
            _income_cell(
                row.amount,
                row.rollup1_account_code,
                row.rollup2_account_code,
                row.rollup3_account_code,
            )
        )
    return grouped


def _income_budget(connection: duckdb.DuckDBPyConnection) -> dict:
    frame = connection.sql(f"""
        SELECT budget.aun, budget.school_year, budget.account_code,
               round(sum(budget.amount), 2) AS amount,
               any_value(names.rollup1_account_code) AS rollup1_account_code,
               any_value(names.rollup2_account_code) AS rollup2_account_code,
               any_value(names.rollup3_account_code) AS rollup3_account_code
        FROM '{REFINED / "gfb_revenue.parquet"}' AS budget
        LEFT JOIN '{REFINED / "revenue_account.parquet"}' AS names
          ON budget.account_code = names.account_code
        GROUP BY 1, 2, 3
        HAVING round(sum(budget.amount), 2) != 0
    """).df()
    grouped: dict[str, dict[int, dict]] = {}
    for row in frame.itertuples(index=False):
        grouped.setdefault(str(row.aun), {}).setdefault(int(row.school_year), {})[str(row.account_code)] = (
            _income_cell(
                row.amount,
                row.rollup1_account_code,
                row.rollup2_account_code,
                row.rollup3_account_code,
            )
        )
    return grouped


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
    """Full-time professional staff salary + experience stats and same-LEA retention.

    Aggregates in DuckDB over ``professional_staff.parquet`` so publish stays
    seconds, not minutes of Python groupby loops.

    ``retention`` counts every full-time professional. ``retention[..]["classroom"]``
    is elementary, secondary, and ungraded teachers only — the share of that
    group still employed at this LEA the next year, in any professional role.
    """
    path = REFINED / "professional_staff.parquet"
    if not path.exists():
        print("no professional_staff.parquet; salary panel skipped")
        return {}, {}, {}
    connection = duckdb.connect()
    try:
        connection.execute(
            f"""
            CREATE TEMP TABLE staff AS
            SELECT
              CAST(aun AS VARCHAR) AS aun,
              CAST(school_year AS INTEGER) AS school_year,
              CAST(public_id AS VARCHAR) AS public_id,
              CAST(annual_salary AS DOUBLE) AS annual_salary,
              CAST(years_in_lea AS DOUBLE) AS years_in_lea,
              CAST(years_in_education AS DOUBLE) AS years_in_education,
              CASE
                WHEN degree_code IS NULL THEN NULL
                ELSE CAST(degree_code AS VARCHAR)
              END AS degree_code,
              {_salary_group_sql("edf_category")} AS grp,
              {_salary_bin_sql("annual_salary")} AS salary_bin,
              {_experience_bin_sql("years_in_lea")} AS lea_bin,
              {_experience_bin_sql("years_in_education")} AS edu_bin
            FROM read_parquet('{_sql_path(path)}')
            WHERE annual_salary > 0
              AND fte_percent = 100
            """
        )
        connection.execute("DELETE FROM staff WHERE grp IS NULL")
        if connection.execute("SELECT count(*) FROM staff").fetchone()[0] == 0:
            return {}, {}, {}

        masters = _masters_sql("degree_code")
        summaries = connection.execute(
            f"""
            SELECT aun, school_year, grp,
                   count(*)::BIGINT AS n,
                   min(annual_salary) AS min_salary,
                   avg(annual_salary) AS mean_salary,
                   median(annual_salary) AS median_salary,
                   max(annual_salary) AS max_salary,
                   avg(years_in_lea) AS lea_years,
                   avg(years_in_education) AS edu_years,
                   {masters} AS masters_pct
            FROM staff
            GROUP BY 1, 2, 3
            """
        ).df()
        salary_bins = connection.execute(
            f"""
            SELECT aun, school_year, grp, salary_bin AS bin,
                   count(*)::BIGINT AS n,
                   avg(years_in_lea) AS lea_years,
                   avg(years_in_education) AS edu_years,
                   {masters} AS masters_pct
            FROM staff
            GROUP BY 1, 2, 3, 4
            """
        ).df()
        lea_summary = connection.execute(
            f"""
            SELECT aun, school_year, grp,
                   count(*)::BIGINT AS n,
                   min(years_in_lea) AS min_years,
                   avg(years_in_lea) AS mean_years,
                   median(years_in_lea) AS median_years,
                   max(years_in_lea) AS max_years
            FROM staff
            WHERE years_in_lea IS NOT NULL
            GROUP BY 1, 2, 3
            """
        ).df()
        lea_bins = connection.execute(
            f"""
            SELECT aun, school_year, grp, lea_bin AS bin,
                   count(*)::BIGINT AS n,
                   avg(annual_salary) AS mean_salary,
                   avg(years_in_education) AS other_years,
                   {masters} AS masters_pct
            FROM staff
            WHERE years_in_lea IS NOT NULL AND lea_bin IS NOT NULL
            GROUP BY 1, 2, 3, 4
            """
        ).df()
        edu_summary = connection.execute(
            f"""
            SELECT aun, school_year, grp,
                   count(*)::BIGINT AS n,
                   min(years_in_education) AS min_years,
                   avg(years_in_education) AS mean_years,
                   median(years_in_education) AS median_years,
                   max(years_in_education) AS max_years
            FROM staff
            WHERE years_in_education IS NOT NULL
            GROUP BY 1, 2, 3
            """
        ).df()
        edu_bins = connection.execute(
            f"""
            SELECT aun, school_year, grp, edu_bin AS bin,
                   count(*)::BIGINT AS n,
                   avg(annual_salary) AS mean_salary,
                   avg(years_in_lea) AS other_years,
                   {masters} AS masters_pct
            FROM staff
            WHERE years_in_education IS NOT NULL AND edu_bin IS NOT NULL
            GROUP BY 1, 2, 3, 4
            """
        ).df()
        retention_all = connection.execute(
            """
            SELECT b.aun, b.school_year,
                   count(DISTINCT b.public_id)::BIGINT AS base,
                   count(DISTINCT CASE WHEN n.public_id IS NOT NULL THEN b.public_id END)::BIGINT AS stayed
            FROM staff b
            INNER JOIN (SELECT DISTINCT aun, school_year FROM staff) y
              ON b.aun = y.aun AND y.school_year = b.school_year + 1
            LEFT JOIN staff n
              ON b.aun = n.aun
             AND b.public_id = n.public_id
             AND n.school_year = b.school_year + 1
            GROUP BY 1, 2
            """
        ).df()
        retention_group = connection.execute(
            """
            SELECT b.aun, b.school_year, b.grp,
                   count(DISTINCT b.public_id)::BIGINT AS base,
                   count(DISTINCT CASE WHEN n.public_id IS NOT NULL THEN b.public_id END)::BIGINT AS stayed
            FROM staff b
            INNER JOIN (SELECT DISTINCT aun, school_year FROM staff) y
              ON b.aun = y.aun AND y.school_year = b.school_year + 1
            LEFT JOIN staff n
              ON b.aun = n.aun
             AND b.public_id = n.public_id
             AND n.school_year = b.school_year + 1
            GROUP BY 1, 2, 3
            """
        ).df()
        classroom_list = ", ".join(repr(group) for group in CLASSROOM_GROUPS)
        retention_classroom = connection.execute(
            f"""
            SELECT b.aun, b.school_year,
                   count(DISTINCT b.public_id)::BIGINT AS base,
                   count(DISTINCT CASE WHEN n.public_id IS NOT NULL THEN b.public_id END)::BIGINT AS stayed
            FROM staff b
            INNER JOIN (SELECT DISTINCT aun, school_year FROM staff) y
              ON b.aun = y.aun AND y.school_year = b.school_year + 1
            LEFT JOIN staff n
              ON b.aun = n.aun
             AND b.public_id = n.public_id
             AND n.school_year = b.school_year + 1
            WHERE b.grp IN ({classroom_list})
            GROUP BY 1, 2
            """
        ).df()
    finally:
        connection.close()

    salary_bin_map = _bin_lookup(salary_bins, len(SALARY_EDGES) + 1, kind="salary")
    lea_bin_map = _bin_lookup(lea_bins, len(EXPERIENCE_EDGES) + 1, kind="experience")
    edu_bin_map = _bin_lookup(edu_bins, len(EXPERIENCE_EDGES) + 1, kind="experience")
    group_retention = {
        (str(row.aun), int(row.school_year), str(row.grp)): row
        for row in retention_group.itertuples(index=False)
    }
    classroom_retention = {
        (str(row.aun), int(row.school_year)): row
        for row in retention_classroom.itertuples(index=False)
    }
    lea_by_key = {
        (str(row.aun), int(row.school_year), str(row.grp)): row
        for row in lea_summary.itertuples(index=False)
    }
    edu_by_key = {
        (str(row.aun), int(row.school_year), str(row.grp)): row
        for row in edu_summary.itertuples(index=False)
    }

    grouped: dict[str, dict[int, dict]] = {}
    experience: dict[str, dict[int, dict]] = {}
    for row in summaries.itertuples(index=False):
        aun = str(row.aun)
        year = int(row.school_year)
        group = str(row.grp)
        key = (aun, year, group)
        hist, bins = salary_bin_map.get(key, ([0] * (len(SALARY_EDGES) + 1), [None] * (len(SALARY_EDGES) + 1)))
        payload = {
            "n": int(row.n),
            "min": _number(row.min_salary),
            "mean": _number(row.mean_salary),
            "median": _number(row.median_salary),
            "max": _number(row.max_salary),
            "hist": hist,
            "bins": bins,
            "leaYears": _nullable_number(row.lea_years),
            "eduYears": _nullable_number(row.edu_years),
            "mastersPct": _nullable_number(row.masters_pct),
        }
        retained = group_retention.get(key)
        if retained is not None and int(retained.base):
            payload["retention"] = _number(int(retained.stayed) / int(retained.base))
        grouped.setdefault(aun, {}).setdefault(year, {})[group] = payload

        experience_payload = {}
        lea_row = lea_by_key.get(key)
        if lea_row is not None:
            lea_hist, lea_bin_list = lea_bin_map.get(
                key, ([0] * (len(EXPERIENCE_EDGES) + 1), [None] * (len(EXPERIENCE_EDGES) + 1))
            )
            experience_payload["lea"] = {
                "n": int(lea_row.n),
                "min": _number(lea_row.min_years),
                "mean": _number(lea_row.mean_years),
                "median": _number(lea_row.median_years),
                "max": _number(lea_row.max_years),
                "hist": lea_hist,
                "bins": _experience_bin_payloads(lea_bin_list, other_key="eduYears"),
            }
        edu_row = edu_by_key.get(key)
        if edu_row is not None:
            edu_hist, edu_bin_list = edu_bin_map.get(
                key, ([0] * (len(EXPERIENCE_EDGES) + 1), [None] * (len(EXPERIENCE_EDGES) + 1))
            )
            experience_payload["edu"] = {
                "n": int(edu_row.n),
                "min": _number(edu_row.min_years),
                "mean": _number(edu_row.mean_years),
                "median": _number(edu_row.median_years),
                "max": _number(edu_row.max_years),
                "hist": edu_hist,
                "bins": _experience_bin_payloads(edu_bin_list, other_key="leaYears"),
            }
        if experience_payload:
            experience.setdefault(aun, {}).setdefault(year, {})[group] = experience_payload

    retention: dict[str, dict[int, dict]] = {}
    for row in retention_all.itertuples(index=False):
        base = int(row.base)
        if not base:
            continue
        aun = str(row.aun)
        year = int(row.school_year)
        payload = {
            "rate": _number(int(row.stayed) / base),
            "base": base,
            "stayed": int(row.stayed),
            "nextYear": year + 1,
        }
        classroom = classroom_retention.get((aun, year))
        if classroom is not None and int(classroom.base):
            classroom_base = int(classroom.base)
            payload["classroom"] = {
                "rate": _number(int(classroom.stayed) / classroom_base),
                "base": classroom_base,
                "stayed": int(classroom.stayed),
                "nextYear": year + 1,
            }
        retention.setdefault(aun, {})[year] = payload

    print(f"salary stats for {len(grouped)} LEAs")
    return grouped, experience, retention


# EdFacts LEAADM, plus the label on older personnel files. SCHADM and CORSUP
# stay in the administrator salary group and are not part of this count.
LEA_ADMIN_CATEGORIES = ("LEAADM", "LEA ADMINISTRATORS")


def _lea_administrators() -> dict:
    """Full-time person rows whose primary assignment is LEAADM.

    Reads ``professional_staff`` (one row per person, LEA, and year), not
    assignment rows. Intermediate units are left out. A year with no LEAADM
    row is absent, not zero.

    When the file has assignment columns, each year is the headcount, the
    jobs, and the sum of reported salaries. A salary is never attached to a
    job. Without those columns the value stays the headcount alone.
    """
    path = REFINED / "professional_staff.parquet"
    if not path.exists():
        return {}
    connection = duckdb.connect()
    try:
        columns = {
            str(row[0])
            for row in connection.execute(
                f"DESCRIBE SELECT * FROM read_parquet('{_sql_path(path)}')"
            ).fetchall()
        }
        needed = {"aun", "school_year", "fte_percent", "edf_category"}
        if not needed <= columns:
            return {}
        iu_filter = ""
        if "lea_type_code" in columns:
            iu_filter = """
              AND upper(trim(CAST(lea_type_code AS VARCHAR))) IS DISTINCT FROM 'IU'
            """
        has_roles = {"assignment_code", "assignment_description"} <= columns
        if has_roles:
            frame = connection.execute(
                f"""
                SELECT CAST(aun AS VARCHAR) AS aun,
                       CAST(school_year AS INTEGER) AS school_year,
                       trim(CAST(assignment_code AS VARCHAR)) AS assignment_code,
                       trim(CAST(assignment_description AS VARCHAR)) AS assignment_description,
                       count(*)::BIGINT AS n,
                       {_lea_admin_salary_sql("annual_salary") if "annual_salary" in columns else "0::BIGINT AS reported, NULL AS salary"}
                FROM read_parquet('{_sql_path(path)}')
                WHERE fte_percent = 100
                  AND {_lea_admin_category_sql("edf_category")}
                  {iu_filter}
                GROUP BY 1, 2, 3, 4
                """
            ).df()
        else:
            frame = connection.execute(
                f"""
                SELECT CAST(aun AS VARCHAR) AS aun,
                       CAST(school_year AS INTEGER) AS school_year,
                       count(*)::BIGINT AS n
                FROM read_parquet('{_sql_path(path)}')
                WHERE fte_percent = 100
                  AND {_lea_admin_category_sql("edf_category")}
                  {iu_filter}
                GROUP BY 1, 2
                """
            ).df()
    finally:
        connection.close()
    if has_roles:
        grouped = _lea_admin_roles(frame)
    else:
        grouped = {}
        for row in frame.itertuples(index=False):
            headcount = int(row.n)
            if headcount <= 0:
                continue
            grouped.setdefault(str(row.aun), {})[int(row.school_year)] = headcount
    if grouped:
        print(f"LEA administrators for {len(grouped)} LEAs")
    return grouped


def _lea_admin_salary_sql(column: str) -> str:
    """Reported pay only. A null or NaN salary is omitted from the sum."""
    reported = f"{column} IS NOT NULL AND isnan({column}) = false"
    return f"""
       count(CASE WHEN {reported} THEN 1 END)::BIGINT AS reported,
       sum(CASE WHEN {reported} THEN {column} END) AS salary
    """


def _lea_admin_roles(frame: pd.DataFrame) -> dict:
    """One payload per LEA and year: headcount, jobs, and the group's pay."""
    buckets: dict[tuple[str, int], list[dict]] = {}
    for row in frame.itertuples(index=False):
        headcount = int(row.n)
        if headcount <= 0:
            continue
        code = "" if _missing(row.assignment_code) else str(row.assignment_code).strip()
        if code.endswith(".0") and code[:-2].isdigit():
            code = code[:-2]
        label = "" if _missing(row.assignment_description) else str(row.assignment_description).strip()
        if not label:
            label = code or "Assignment not published"
        reported = int(row.reported or 0)
        salary = None if reported <= 0 or _missing(row.salary) else float(row.salary)
        buckets.setdefault((str(row.aun), int(row.school_year)), []).append({
            "code": code,
            "label": label,
            "n": headcount,
            "reported": reported,
            "salary": salary,
        })
    grouped: dict[str, dict[int, dict]] = {}
    for (aun, year), roles in buckets.items():
        roles.sort(key=lambda role: (-role["n"], role["label"].casefold(), role["code"]))
        payload: dict = {
            "n": sum(role["n"] for role in roles),
            "roles": [
                {"code": role["code"], "label": role["label"], "n": role["n"]}
                for role in roles
            ],
        }
        paid = [role["salary"] for role in roles if role["salary"] is not None]
        if paid:
            payload["salary"] = _number(sum(paid))
        unreported = sum(role["n"] - role["reported"] for role in roles)
        if unreported > 0:
            payload["unreported"] = unreported
        grouped.setdefault(aun, {})[year] = payload
    return grouped


def _lea_admin_headcount(value: object) -> int | None:
    """Headcount from an int or from the role payload. Zero is absence."""
    if isinstance(value, dict):
        value = value.get("n")
    if value is None or _missing(value):
        return None
    headcount = int(value)
    return headcount if headcount > 0 else None


def _lea_admin_block(value: object) -> dict | None:
    """JSON for one year. Jobs carry a count, never a salary."""
    headcount = _lea_admin_headcount(value)
    if headcount is None:
        return None
    if not isinstance(value, dict):
        return {"n": headcount}
    block: dict = {"n": headcount}
    roles = [
        {"code": str(role["code"]), "label": str(role["label"]), "n": int(role["n"])}
        for role in (value.get("roles") or [])
        if int(role.get("n") or 0) > 0
    ]
    if roles:
        block["roles"] = roles
    salary = value.get("salary")
    if salary is not None and not _missing(salary):
        block["salary"] = _number(salary)
    unreported = int(value.get("unreported") or 0)
    if unreported > 0:
        block["unreported"] = unreported
    return block


def _lea_admin_category_sql(column: str) -> str:
    codes = ", ".join(repr(code) for code in LEA_ADMIN_CATEGORIES)
    return f"upper(trim(CAST({column} AS VARCHAR))) IN ({codes})"


def _lea_admins_per_thousand(count: object, enrollment: object) -> float | None:
    """Full-time LEAADM headcount per 1,000 October 1 students.

    A missing count or enrollment is absence. Zero is not a rate.
    ``count`` may be the headcount or the role payload.
    """
    headcount = _lea_admin_headcount(count)
    if headcount is None or enrollment is None or _missing(enrollment):
        return None
    students = float(enrollment)
    if students <= 0:
        return None
    return round(headcount / students * 1000, 4)


def _sql_path(path: Path) -> str:
    return str(path).replace("'", "''")


def _salary_group_sql(column: str) -> str:
    """SQL expression matching ``_salary_group``."""
    return f"""
    CASE
      WHEN {column} IS NULL OR trim(CAST({column} AS VARCHAR)) = '' THEN NULL
      WHEN upper(trim(CAST({column} AS VARCHAR))) IN (
        'ELMTCH', 'KGTCH', 'PKTCH',
        'ELEMENTARY TEACHERS', 'KINDERGARTEN TEACHERS', 'PRE-KINDERGARTEN TEACHERS'
      ) THEN 'elementary'
      WHEN upper(trim(CAST({column} AS VARCHAR))) IN ('SECTCH', 'SECONDARY TEACHERS') THEN 'secondary'
      WHEN upper(trim(CAST({column} AS VARCHAR))) IN (
        'SCHADM', 'LEAADM', 'CORSUP', 'SCHOOL ADMINISTRATORS', 'LEA ADMINISTRATORS'
      ) THEN 'administrator'
      WHEN upper(trim(CAST({column} AS VARCHAR))) IN ('UGTCH', 'UNGRADED TEACHERS') THEN 'ungraded'
      ELSE 'support'
    END
    """


def _salary_bin_sql(column: str) -> str:
    start = SALARY_BIN_START
    stop = SALARY_BIN_STOP
    width = SALARY_BIN_WIDTH
    over = len(SALARY_EDGES)
    return f"""
    CASE
      WHEN {column} < {start} THEN 0
      WHEN {column} >= {stop} THEN {over}
      ELSE CAST(floor(({column} - {start}) / {width}) AS INTEGER) + 1
    END
    """


def _experience_bin_sql(column: str) -> str:
    over = len(EXPERIENCE_EDGES)
    return f"""
    CASE
      WHEN {column} IS NULL THEN NULL
      WHEN {column} < 1 THEN 0
      WHEN {column} >= 40 THEN {over}
      ELSE CAST(floor({column}) AS INTEGER)
    END
    """


def _masters_sql(column: str) -> str:
    codes = ", ".join(f"'{code}'" for code in sorted(MASTERS_PLUS))
    return f"""
    CASE
      WHEN count({column}) = 0 THEN NULL
      ELSE 100.0 * sum(CASE WHEN {column} IN ({codes}) THEN 1 ELSE 0 END)
           / count({column})
    END
    """


def _nullable_number(value: object) -> float | None:
    if value is None or _missing(value):
        return None
    number = float(value)
    if number != number:
        return None
    return _number(number)


def _bin_lookup(
    frame: pd.DataFrame,
    size: int,
    *,
    kind: str = "salary",
) -> dict[tuple[str, int, str], tuple[list[int], list[dict | None]]]:
    """Map (aun, year, group) → (hist counts, sparse bin payloads)."""
    grouped: dict[tuple[str, int, str], tuple[list[int], list[dict | None]]] = {}
    if frame.empty:
        return grouped
    for row in frame.itertuples(index=False):
        key = (str(row.aun), int(row.school_year), str(row.grp))
        hist, bins = grouped.get(key) or ([0] * size, [None] * size)
        index = int(row.bin)
        if index < 0 or index >= size:
            continue
        hist[index] = int(row.n)
        if kind == "salary":
            payload: dict[str, object] = {
                "n": int(row.n),
                "leaYears": _nullable_number(row.lea_years),
                "eduYears": _nullable_number(row.edu_years),
                "mastersPct": _nullable_number(row.masters_pct),
            }
        else:
            payload = {
                "n": int(row.n),
                "meanSalary": _nullable_number(row.mean_salary),
                "otherYears": _nullable_number(row.other_years),
                "mastersPct": _nullable_number(row.masters_pct),
            }
        bins[index] = payload
        grouped[key] = (hist, bins)
    return grouped


def _experience_bin_payloads(
    bins: list[dict | None],
    *,
    other_key: str,
) -> list[dict | None]:
    out: list[dict | None] = [None] * len(bins)
    for index, payload in enumerate(bins):
        if not payload:
            continue
        out[index] = {
            "n": payload["n"],
            "meanSalary": payload.get("meanSalary"),
            other_key: payload.get("otherYears"),
            "mastersPct": payload.get("mastersPct"),
        }
    return out


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


def _debt_service(connection: duckdb.DuckDBPyConnection) -> dict:
    """General-fund AFR function 5110, debt service.

    Budget function 5100 mixes debt service with other financing uses, so it
    stays out. A reported zero is kept. A year with no 5110 row is absent.
    """
    frame = connection.sql(f"""
        SELECT aun, school_year, round(sum(total_amount), 2) AS amount
        FROM '{REFINED / "afr_expenditure.parquet"}'
        WHERE fund_code = '10' AND function_code = '5110'
        GROUP BY 1, 2
    """).df()
    grouped: dict[str, dict[int, float]] = {}
    for row in frame.itertuples(index=False):
        grouped.setdefault(str(row.aun), {})[int(row.school_year)] = _number(row.amount)
    return grouped


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


def _district_population(connection: duckdb.DuckDBPyConnection) -> dict:
    """Census SAIPE ages 5–17 and related children in poverty, by district and year."""
    path = REFINED / "district_population.parquet"
    if not path.exists():
        return {}
    frame = connection.sql(f"""
        SELECT aun, school_year, population_5_17, children_5_17_in_poverty
        FROM '{path}'
    """).df()
    grouped: dict[str, dict[int, dict]] = {}
    for row in frame.itertuples(index=False):
        cell = {}
        ages = _whole_count(row.population_5_17)
        poverty = _whole_count(row.children_5_17_in_poverty)
        if ages is not None:
            cell["population_5_17"] = ages
        if poverty is not None:
            cell["children_5_17_in_poverty"] = poverty
        if cell:
            grouped.setdefault(str(row.aun), {})[int(row.school_year)] = cell
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


def _bind_assessment_lea(connection: duckdb.DuckDBPyConnection) -> str | None:
    """Point DuckDB at `assessment_lea`, or the district file when the school file is absent.

    The view keeps a school district on the district workbook and copies one
    school row for any other LEA. District buildings stay in the school table.
    """
    result = REFINED / "assessment_result.parquet"
    if not result.exists():
        return None
    school = REFINED / "assessment_result_school.parquet"
    lea = REFINED / "lea.parquet"
    if not school.exists() or not lea.exists():
        return f"read_parquet('{_sql_path(result)}')"
    for name, path in (
        ("assessment_result", result),
        ("assessment_result_school", school),
        ("lea", lea),
    ):
        connection.execute(
            f"CREATE OR REPLACE VIEW {name} AS "
            f"SELECT * FROM read_parquet('{_sql_path(path)}')"
        )
    statement = next(view.sql for view in load_views() if view.name == "assessment_lea")
    connection.execute(statement)
    return "assessment_lea"


def _assessment(connection: duckdb.DuckDBPyConnection, assessment: str) -> dict:
    """PSSA rows for an LEA page. Keystone stays on `_keystone`.

    `pct_proficient_and_above` is the only headline percent. A year the
    workbook leaves null stays null here, including when advanced and
    proficient are filled in. The scored count is still kept.
    """
    if assessment != "pssa":
        raise ValueError(f"{assessment} is not a PSSA publish")
    source = _bind_assessment_lea(connection)
    if source is None:
        return {}
    frame = connection.sql(f"""
        SELECT aun, school_year, subject, grade, student_group,
               number_scored, pct_proficient_and_above
        FROM {source}
        WHERE assessment = 'pssa'
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


def _whole_count(value: object) -> int | None:
    """A published count, including zero. Null stays absent."""
    if value is None or _missing(value):
        return None
    number = float(value)
    if number != number:
        return None
    return int(number)


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
