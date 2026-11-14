"""Download cataloged PDE files and write the refined Parquet tables.

A stable file is parsed again when its bytes or its parser source have changed.
Each document's tables are kept under ``data/refined/_parts/<document_id>/``
and concatenated into the published parquet. An unchanged catalog leaves those
files in place.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import multiprocessing
import os
import shutil
from concurrent.futures import ProcessPoolExecutor
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
    "afr_revenue": [
        "aun", "school_year", "fund_code", "account_code", "program_code",
        "rollup_fund_code", "rollup1_account_code", "rollup2_account_code", "rollup3_account_code",
        "amount_1", "amount_2", "amount_3", "total_amount", "amount", "document_id",
    ],
    "gfb_revenue": [
        "aun", "school_year", "account_code", "amount", "fund_code", "document_id",
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
    "professional_assignment": [
        "school_year", "snapshot_date", "public_id", "last_name", "first_name",
        "middle_name", "suffix", "gender", "race", "annual_salary", "degree_code",
        "degree_description", "years_in_education", "years_in_lea", "status", "aun",
        "lea_name", "lea_type", "lea_type_code", "county_code", "county",
        "school_number", "school_name", "iu_code", "iu_name", "time_status",
        "job_class", "primary_assignment", "assignment_code", "assignment_description",
        "position_code", "position_description", "edf_code", "edf_category",
        "category_description", "fte_percent", "source_layout", "source_file",
    ],
    "school": ["aun", "school_number", "school_name"],
    "grade": ["grade_code", "label", "band", "session"],
    "account": [
        "function_code", "object_code", "function_name", "object_name",
        "major_function", "major_object",
    ],
    "revenue_account": [
        "account_code", "name",
        "rollup1_account_code", "rollup2_account_code", "rollup3_account_code",
    ],
    "chart_description": ["kind", "code", "name", "description"],
}
COLUMNS["afr_expenditure_school"] = [
    "aun", "school_number", "school_name", *COLUMNS["afr_expenditure"][1:],
]
COLUMNS["professional_staff"] = [
    *COLUMNS["professional_assignment"],
    "row_rule",
    "assignment_count",
]

SORT = {
    "document": ["document_id"],
    "lea": ["aun"],
    "lea_year": ["school_year", "aun", "document_id"],
    "gfb_expenditure": ["school_year", "aun", "function_code", "object_code", "program_code"],
    "afr_expenditure": ["school_year", "aun", "fund_code", "function_code", "object_code", "program_code"],
    "afr_revenue": ["school_year", "aun", "fund_code", "account_code", "program_code"],
    "gfb_revenue": ["school_year", "aun", "account_code"],
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
    "professional_assignment": ["school_year", "aun", "public_id", "assignment_code", "school_number"],
    "professional_staff": ["school_year", "aun", "public_id"],
    "school": ["aun", "school_number"],
    "grade": ["grade_code"],
    "account": ["function_code", "object_code"],
    "revenue_account": ["account_code"],
    "chart_description": ["kind", "code"],
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

# Written by python -m pa_edu.personnel. refine must not replace an existing file.
PERSONNEL_TABLES = ("professional_assignment", "professional_staff")
PARTS_DIR = "_parts"
STAMP_NAME = "_inputs.json"
SHARD_VERSION = 1


def main() -> None:
    run()


def run(data_dir: Path | None = None, catalog_path: Path | None = None) -> Path:
    data_dir = data_dir or DATA_DIR
    catalog_path = catalog_path or ROOT / "sources" / "catalog.toml"
    entries = load_catalog(catalog_path)
    index = load_index(data_dir)
    jobs = []
    for entry in entries:
        record = materialize(entry, data_dir, index)
        print(f"{entry.status:6} {entry.id}: {Path(record['path']).name}")
        if entry.status != "stable":
            continue
        if entry.parser not in PARSERS:
            raise RuntimeError(f"{entry.id} has no parser {entry.parser!r}")
        jobs.append(_job(entry, record))
    refined = data_dir / "refined"
    refined.mkdir(parents=True, exist_ok=True)
    stamp = _stamp(jobs, index)
    if _stamp_matches(refined, stamp):
        print(f"kept refined tables ({len(jobs)} documents)")
    else:
        _refresh(refined, jobs, stamp, index)
    _ensure_personnel(refined)
    _duckdb(data_dir / "pde.duckdb", refined)
    print(f"wrote {data_dir / 'pde.duckdb'}")
    return refined


def _job(entry, record: dict) -> dict:
    return {
        "catalog_id": entry.id,
        "document_id": record["document_id"],
        "sha256": record["sha256"],
        "parser": entry.parser,
        "fingerprint": _fingerprint(entry.parser),
        "path": record["path"],
        "record": record,
    }


def _stamp(jobs: list[dict], index: dict) -> dict:
    return {
        "assembly": _assembly_fingerprint(),
        "documents": sorted(
            f"{document_id}:{record['sha256']}"
            for document_id, record in index["documents"].items()
        ),
        "parsed": [
            {
                "catalog_id": job["catalog_id"],
                "document_id": job["document_id"],
                "fingerprint": job["fingerprint"],
                "parser": job["parser"],
                "sha256": job["sha256"],
            }
            for job in jobs
        ],
    }


def _stamp_matches(refined: Path, stamp: dict) -> bool:
    path = refined / STAMP_NAME
    if not path.exists():
        return False
    if json.loads(path.read_text()) != stamp:
        return False
    return all((refined / f"{name}.parquet").exists() for name in _output_tables())


def _output_tables() -> list[str]:
    return [name for name in COLUMNS if name not in PERSONNEL_TABLES]


def _refresh(refined: Path, jobs: list[dict], stamp: dict, index: dict) -> None:
    parts = refined / PARTS_DIR
    parts.mkdir(parents=True, exist_ok=True)
    missing = []
    for job in jobs:
        if _shard_ready(parts, job):
            print(f"         kept {job['catalog_id']}")
            continue
        print(f"         parse {job['catalog_id']}")
        job["dest"] = str(parts / job["document_id"])
        missing.append(job)
    _parse_missing(missing)
    collected, functions, objects, revenues, described = _load_parts(parts, jobs)
    _publish_frames(refined, collected, functions, objects, revenues, described, index)
    _drop_stale_parts(parts, {job["document_id"] for job in jobs})
    (refined / STAMP_NAME).write_text(json.dumps(stamp, indent=2, sort_keys=True) + "\n")


def _parse_missing(jobs: list[dict]) -> None:
    if not jobs:
        return
    workers = min(len(jobs), os.cpu_count() or 1)
    if workers == 1:
        for job in jobs:
            _parse_one(job)
        return
    # spawn: the parent has already imported pandas, and fork can deadlock on its locks.
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=workers, mp_context=context) as pool:
        list(pool.map(_parse_one, jobs))


def _parse_one(job: dict) -> None:
    catalog_id = job["catalog_id"]
    try:
        parsed = PARSERS[job["parser"]](Path(job["path"]), job["record"])
        _write_shard(Path(job["dest"]), job, parsed)
    except Exception as error:
        raise RuntimeError(f"{catalog_id} failed: {error}") from error


def _write_shard(dest: Path, job: dict, parsed: dict) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    temporary = dest.parent / f".{dest.name}.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir()
    tables = []
    for name, frame in parsed.items():
        if frame is None or frame.empty:
            continue
        frame.to_parquet(temporary / f"{name}.parquet", index=False)
        tables.append(name)
    meta = {
        "version": SHARD_VERSION,
        "catalog_id": job["catalog_id"],
        "document_id": job["document_id"],
        "sha256": job["sha256"],
        "parser": job["parser"],
        "fingerprint": job["fingerprint"],
        "tables": tables,
    }
    (temporary / "meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
    if dest.exists():
        shutil.rmtree(dest)
    temporary.rename(dest)


def _shard_ready(parts: Path, job: dict) -> bool:
    directory = parts / job["document_id"]
    meta_path = directory / "meta.json"
    if not meta_path.is_file():
        return False
    meta = json.loads(meta_path.read_text())
    if meta.get("version") != SHARD_VERSION:
        return False
    for key in ("catalog_id", "document_id", "sha256", "parser", "fingerprint"):
        if meta.get(key) != job[key]:
            return False
    tables = meta.get("tables")
    if not isinstance(tables, list):
        return False
    return all(isinstance(name, str) and (directory / f"{name}.parquet").is_file() for name in tables)


def _load_parts(parts: Path, jobs: list[dict]):
    catalog_tables = [name for name in COLUMNS if name not in {"document", *PERSONNEL_TABLES}]
    collected: dict[str, list[pd.DataFrame]] = {name: [] for name in catalog_tables}
    functions: dict[str, str] = {}
    objects: dict[str, str] = {}
    revenues: dict[str, str] = {}
    described: dict[str, dict[str, str]] = {"function": {}, "object": {}, "revenue": {}}
    for job in jobs:
        directory = parts / job["document_id"]
        meta = json.loads((directory / "meta.json").read_text())
        frames = {
            name: pd.read_parquet(directory / f"{name}.parquet")
            for name in meta["tables"]
        }
        if job["parser"] == "chart":
            functions, objects, revenues, described = _chart_fields(frames)
            continue
        for table, frame in frames.items():
            if table not in collected:
                raise RuntimeError(f"{job['catalog_id']} returned unknown table {table}")
            if frame.empty:
                continue
            collected[table].append(frame)
    return collected, functions, objects, revenues, described


def _chart_frame(parsed: dict, name: str, column: str) -> pd.DataFrame:
    frame = parsed.get(name)
    if frame is None:
        return empty_frame([column, "name", "description"])
    return frame


def _chart_fields(parsed: dict):
    function = _chart_frame(parsed, "function", "function_code")
    obj = _chart_frame(parsed, "object", "object_code")
    revenue = _chart_frame(parsed, "revenue", "account_code")
    functions = _chart_names(function, "function_code")
    objects = _chart_names(obj, "object_code")
    revenues = _chart_names(revenue, "account_code")
    described = {
        "function": _chart_descriptions(function, "function_code"),
        "object": _chart_descriptions(obj, "object_code"),
        "revenue": _chart_descriptions(revenue, "account_code"),
    }
    print(
        f"         chart titles: {len(functions)} functions, "
        f"{len(objects)} objects, {len(revenues)} revenue; "
        f"descriptions: {len(described['function'])} functions, "
        f"{len(described['object'])} objects, {len(described['revenue'])} revenue"
    )
    return functions, objects, revenues, described


def _publish_frames(
    refined: Path,
    collected: dict[str, list[pd.DataFrame]],
    functions: dict[str, str],
    objects: dict[str, str],
    revenues: dict[str, str],
    described: dict[str, dict[str, str]],
    index: dict,
) -> None:
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
    frames["revenue_account"] = _revenue_account(frames, revenues)
    frames["chart_description"] = _chart_description_frame(
        {"function": functions, "object": objects, "revenue": revenues},
        described,
    )
    frames["document"] = _documents(index)
    for name, frame in frames.items():
        frame = _align(frame, COLUMNS[name], SORT[name])
        frame.to_parquet(refined / f"{name}.parquet", index=False)
        print(f"wrote {name} {len(frame):,}")


def _drop_stale_parts(parts: Path, keep: set[str]) -> None:
    for child in parts.iterdir():
        if child.name in keep:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _fingerprint(parser_name: str) -> str:
    module = inspect.getmodule(PARSERS[parser_name])
    if module is None:
        raise RuntimeError(f"{parser_name} has no module to fingerprint")
    digest = hashlib.sha256()
    root = ROOT.resolve()
    for path in sorted(_pa_files(module, set()), key=lambda item: item.as_posix()):
        digest.update(path.resolve().relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _pa_files(module, seen: set[str]) -> set[Path]:
    """Parser source plus the pa_edu modules it calls.

    ``from pa_edu.codes import as_code`` does not leave the module itself in
    the parser's namespace, so follow those functions back to their files.
    """
    if module is None:
        return set()
    name = getattr(module, "__name__", "")
    if not name.startswith("pa_edu") or name in seen:
        return set()
    seen.add(name)
    found: set[Path] = set()
    file = getattr(module, "__file__", None)
    if file and file.endswith(".py"):
        found.add(Path(file).resolve())
    for value in vars(module).values():
        if inspect.ismodule(value):
            found.update(_pa_files(value, seen))
            continue
        if not (inspect.isfunction(value) or inspect.isclass(value)):
            continue
        found.update(_pa_files(inspect.getmodule(value), seen))
    return found


def _assembly_fingerprint() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


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


def _chart_names(frame: pd.DataFrame, column: str) -> dict[str, str]:
    names = {}
    for code, name in zip(frame[column], frame["name"], strict=True):
        if pd.isna(name):
            continue
        text = str(name).strip()
        if text and text not in {"None", "nan", "<NA>"}:
            names[str(code)] = text
    return names


def _chart_descriptions(frame: pd.DataFrame, column: str) -> dict[str, str]:
    described = {}
    if "description" not in frame.columns:
        return described
    for code, description in zip(frame[column], frame["description"], strict=True):
        if pd.isna(description):
            continue
        text = str(description).strip()
        if text and text not in {"None", "nan", "<NA>"}:
            described[str(code)] = text
    return described


def _chart_description_frame(
    names: dict[str, dict[str, str]],
    described: dict[str, dict[str, str]],
) -> pd.DataFrame:
    """One row per chart code that has a heading, a paragraph, or both.

    A missing heading or a missing paragraph stays null. Neither is copied
    from the other.
    """
    rows = []
    for kind in ("function", "object", "revenue"):
        titled = names.get(kind, {})
        prose = described.get(kind, {})
        for code in set(titled) | set(prose):
            rows.append({
                "kind": kind,
                "code": code,
                "name": titled.get(code) or pd.NA,
                "description": prose.get(code) or pd.NA,
            })
    if not rows:
        return empty_frame(COLUMNS["chart_description"])
    return pd.DataFrame(rows, columns=COLUMNS["chart_description"])


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


def _revenue_account(frames: dict[str, pd.DataFrame], titles: dict[str, str]) -> pd.DataFrame:
    chains: dict[str, tuple] = {}
    revenue = frames["afr_revenue"]
    if not revenue.empty:
        fund10 = revenue.loc[revenue["fund_code"].astype(str) == "10"]
        source = fund10 if not fund10.empty else revenue
        rollups = ["rollup1_account_code", "rollup2_account_code", "rollup3_account_code"]
        for account, group in source.groupby("account_code", dropna=False):
            distinct = group.loc[:, rollups].drop_duplicates()
            if len(distinct) > 1:
                raise RuntimeError(f"revenue account {account} has more than one rollup chain")
            row = distinct.iloc[0]
            chains[str(account)] = tuple(row[column] for column in rollups)
    for code in titles:
        chains.setdefault(str(code), (pd.NA, pd.NA, pd.NA))
    budget = frames["gfb_revenue"]
    if not budget.empty:
        for code in budget["account_code"].dropna().unique():
            chains.setdefault(str(code), (pd.NA, pd.NA, pd.NA))
    if not chains:
        return empty_frame(COLUMNS["revenue_account"])
    rows = []
    for code in sorted(chains):
        first, second, third = chains[code]
        rows.append({
            "account_code": code,
            "name": titles.get(code, pd.NA),
            "rollup1_account_code": first,
            "rollup2_account_code": second,
            "rollup3_account_code": third,
        })
    return pd.DataFrame(rows)


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


def _ensure_personnel(refined: Path) -> None:
    """Leave staff parquet from pa_edu.personnel in place.

    A missing file gets an empty frame so the DuckDB views can bind. The next
    personnel run replaces it.
    """
    for name in PERSONNEL_TABLES:
        path = refined / f"{name}.parquet"
        if path.exists():
            print(f"kept {name}")
            continue
        empty_frame(COLUMNS[name]).to_parquet(path, index=False)
        print(f"wrote {name} 0")


def _duckdb(database: Path, refined: Path) -> None:
    sql = (ROOT / "sql" / "model.sql").read_text()
    sql = sql.replace("data/refined", refined.as_posix())
    portal = (ROOT / "sql" / "portal.sql").read_text()
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(database))
    try:
        connection.execute(sql)
        connection.execute(portal)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
