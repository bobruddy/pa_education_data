import gzip
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from pa_edu.publish import (
    EXPERIENCE_EDGES,
    SALARY_EDGES,
    JSON_GZIP_LEVEL,
    _ages517_share,
    _assessment,
    _keystone,
    _keystone_schools_only,
    _latest_population_5_17,
    _catalog,
    _county_ranks,
    _debt_service,
    _experience_stats,
    _lea_administrators,
    _lea_admins_per_thousand,
    _percent_points,
    _published_charter,
    _salaries,
    _salary_group,
    _short_title,
    _write_json,
    _years_for,
    directory_row,
    read_git_build,
    _revenue_chain,
    lea_document,
    write_build_stamp,
)


def test_catalog_links_each_personnel_workbook(tmp_path: Path, monkeypatch) -> None:
    refined = tmp_path / "refined"
    refined.mkdir()
    pd.DataFrame({"school_year": [2024]}).to_parquet(refined / "enrollment.parquet", index=False)
    pd.DataFrame({"school_year": [2023]}).to_parquet(refined / "afr_expenditure.parquet", index=False)
    pd.DataFrame({"school_year": [2025]}).to_parquet(refined / "gfb_expenditure.parquet", index=False)
    pd.DataFrame({
        "function_code": pd.Series(dtype="object"),
        "function_name": pd.Series(dtype="object"),
        "object_code": pd.Series(dtype="object"),
        "object_name": pd.Series(dtype="object"),
    }).to_parquet(refined / "account.parquet", index=False)
    pd.DataFrame({
        "account_code": pd.Series(dtype="object"),
        "name": pd.Series(dtype="object"),
    }).to_parquet(refined / "revenue_account.parquet", index=False)
    pd.DataFrame([
        {
            "parser": "personnel",
            "school_year": 2024,
            "source_url": "https://example.test/staff-2024.xlsx",
            "page_url": None,
            "catalog_id": "personnel-2024",
            "retrieved_at": "2026-01-02T00:00:00",
        },
        {
            "parser": "personnel",
            "school_year": 2024,
            "source_url": "https://example.test/staff-2024-old.xlsx",
            "page_url": None,
            "catalog_id": "personnel-2024",
            "retrieved_at": "2025-01-01T00:00:00",
        },
        {
            "parser": "personnel",
            "school_year": 2025,
            "source_url": "https://example.test/staff-2025.xlsx",
            "page_url": None,
            "catalog_id": "personnel-2025",
            "retrieved_at": "2026-02-01T00:00:00",
        },
        {
            "parser": "personnel",
            "school_year": None,
            "source_url": "https://example.test/staff-blank.xlsx",
            "page_url": None,
            "catalog_id": "personnel-blank",
            "retrieved_at": "2026-01-01T00:00:00",
        },
        {
            "parser": "enrollment",
            "school_year": 2024,
            "source_url": "https://example.test/enrollment-2024.xlsx",
            "page_url": "https://example.test/enrollment",
            "catalog_id": "enrollment-2024",
            "retrieved_at": "2026-01-01T00:00:00",
        },
        {
            "parser": "saipe",
            "school_year": 2023,
            "source_url": "https://example.test/sd23-pa.txt",
            "page_url": "https://www.census.gov/data/datasets/2023/demo/saipe/2023-school-districts.html",
            "catalog_id": "saipe-2023",
            "retrieved_at": "2026-01-01T00:00:00",
        },
        {
            "parser": "pssa",
            "school_year": 2024,
            "source_url": "https://example.test/pssa-district-2024.xlsx",
            "page_url": None,
            "catalog_id": "pssa-district-2024",
            "retrieved_at": "2026-01-01T00:00:00",
        },
        {
            "parser": "pssa_school",
            "school_year": 2024,
            "source_url": "https://example.test/pssa-school-2024.xlsx",
            "page_url": None,
            "catalog_id": "pssa-school-2024",
            "retrieved_at": "2026-01-01T00:00:00",
        },
        {
            "parser": "keystone",
            "school_year": 2024,
            "source_url": "https://example.test/keystone-district-2024.xlsx",
            "page_url": None,
            "catalog_id": "keystone-district-2024",
            "retrieved_at": "2026-01-01T00:00:00",
        },
        {
            "parser": "keystone_school",
            "school_year": 2024,
            "source_url": "https://example.test/keystone-school-2024.xlsx",
            "page_url": None,
            "catalog_id": "keystone-school-2024",
            "retrieved_at": "2026-01-01T00:00:00",
        },
    ]).to_parquet(refined / "document.parquet", index=False)
    monkeypatch.setattr("pa_edu.publish.REFINED", refined)
    sources = _catalog(duckdb.connect())["sources"]
    assert sources["personnelWorkbooks"] == {
        "2024": "https://example.test/staff-2024.xlsx",
        "2025": "https://example.test/staff-2025.xlsx",
    }
    assert sources["enrollment"]["2024"] == "https://example.test/enrollment-2024.xlsx"
    assert sources["pssa"]["2024"] == "https://example.test/pssa-district-2024.xlsx"
    assert sources["pssaSchool"]["2024"] == "https://example.test/pssa-school-2024.xlsx"
    assert sources["keystone"]["2024"] == "https://example.test/keystone-district-2024.xlsx"
    assert sources["keystoneSchool"]["2024"] == "https://example.test/keystone-school-2024.xlsx"
    assert sources["saipe"]["2023"] == "https://example.test/sd23-pa.txt"
    assert sources["saipePage"]["2023"] == (
        "https://www.census.gov/data/datasets/2023/demo/saipe/2023-school-districts.html"
    )
    assert sources["afrPage"].endswith("afr-data-summary-level")
    assert sources["gfbPage"].endswith("general-fund-budget-gfb-data")
    assert sources["act1Page"].endswith("act-1-index")
    assert sources["iepPage"] == "https://penndata.hbg.psu.edu/Additional-Reports"


def test_support_service_titles_keep_the_chart_suffix() -> None:
    assert _short_title("SUPPORT SERVICES – STUDENTS") == "STUDENTS"
    assert _short_title("SUPPORT SERVICES – INSTRUCTIONAL STAFF") == "INSTRUCTIONAL STAFF"
    assert _short_title("SUPPORT SERVICES – ADMINISTRATION") == "ADMINISTRATION"
    assert _short_title("SUPPORT SERVICES – PUPIL HEALTH") == "PUPIL HEALTH"
    assert _short_title("SUPPORT SERVICES – BUSINESS") == "BUSINESS"
    assert _short_title("SUPPORT SERVICES – CENTRAL") == "CENTRAL"
    assert _short_title("REGULAR PROGRAMS – ELEMENTARY / SECONDARY") == "REGULAR PROGRAMS"
    assert _short_title("STUDENT TRANSPORTATION SERVICES") == "STUDENT TRANSPORTATION SERVICES"


def test_empty_years_are_left_out() -> None:
    document = lea_document(
        {"aun": "1", "name": "One"},
        {
            2024: {
                "grades": {"012": 10},
                "schools": [],
                "actual": {},
                "budget": {},
                "budgetDetail": {"1100": {"100": 5}},
                "actualDetail": {"1110": {"120": {"t": 9, "e": 4}}},
                "actualSchool": {},
            },
            2023: {
                "grades": {},
                "schools": [],
                "actual": {},
                "budget": {},
                "budgetDetail": {},
                "actualDetail": {},
                "actualSchool": {},
            },
        },
    )
    assert list(document["years"]) == ["2024"]
    assert document["years"]["2024"]["actualDetail"]["1110"]["120"]["t"] == 9


def test_salary_groups_follow_edf_codes() -> None:
    assert _salary_group("ELMTCH") == "elementary"
    assert _salary_group("KGTCH") == "elementary"
    assert _salary_group("SECTCH") == "secondary"
    assert _salary_group("SCHADM") == "administrator"
    assert _salary_group("LEAADM") == "administrator"
    assert _salary_group("UGTCH") == "ungraded"
    assert _salary_group("GUI") == "support"
    assert _salary_group("Elementary Teachers") == "elementary"
    assert _salary_group("Secondary Teachers") == "secondary"
    assert _salary_group(None) is None


def test_salaries_come_from_professional_staff_parquet(tmp_path: Path, monkeypatch) -> None:
    refined = tmp_path / "refined"
    refined.mkdir()
    pd.DataFrame({
        "aun": ["1", "1", "1", "1", "1"],
        "school_year": [2023, 2023, 2023, 2023, 2024],
        "public_id": ["a", "b", "z", "c", "a"],
        "annual_salary": [50_000.0, 70_000.0, 0.0, 10.0, 51_000.0],
        "fte_percent": [100.0, 100.0, 100.0, 50.0, 100.0],
        "edf_category": ["ELMTCH", "ELMTCH", "ELMTCH", "ELMTCH", "ELMTCH"],
        "years_in_lea": [3.0, 1.0, 9.0, 9.0, 4.0],
        "years_in_education": [5.0, 2.0, 9.0, 9.0, 6.0],
        "degree_code": ["1054", "1051", "1054", "1054", "1054"],
    }).to_parquet(refined / "professional_staff.parquet", index=False)
    monkeypatch.setattr("pa_edu.publish.REFINED", refined)
    salaries, experience, retention = _salaries()
    stats = salaries["1"][2023]["elementary"]
    assert stats["n"] == 2
    assert stats["mean"] == 60_000
    assert stats["mastersPct"] == 50
    assert stats["retention"] == 0.5
    assert len(stats["hist"]) == len(SALARY_EDGES) + 1
    assert sum(stats["hist"]) == 2
    assert retention["1"][2023] == {
        "rate": 0.5,
        "base": 2,
        "stayed": 1,
        "nextYear": 2024,
        "classroom": {"rate": 0.5, "base": 2, "stayed": 1, "nextYear": 2024},
    }
    assert 2024 not in retention["1"]
    assert experience["1"][2023]["elementary"]["lea"]["n"] == 2


def test_classroom_retention_excludes_administrators_and_support(tmp_path: Path, monkeypatch) -> None:
    """Classroom retention is distinct teachers, not the LEA-wide professional rate.

    A teacher who returns as an administrator still counts as stayed. The same
    person in two classroom groups counts once. Administrators and professional
    support are not in the base.
    """
    refined = tmp_path / "refined"
    refined.mkdir()
    rows = [
        # id, year, salary, fte, category
        ("t1", 2023, 60_000.0, 100.0, "ELMTCH"),
        ("t1", 2024, 90_000.0, 100.0, "SCHADM"),
        ("t2", 2023, 60_000.0, 100.0, "SECTCH"),
        ("t3", 2023, 55_000.0, 100.0, "UGTCH"),
        ("t3", 2024, 56_000.0, 100.0, "UGTCH"),
        ("t4", 2023, 50_000.0, 100.0, "ELMTCH"),
        ("t4", 2023, 52_000.0, 100.0, "SECTCH"),
        ("t4", 2024, 53_000.0, 100.0, "ELMTCH"),
        ("a1", 2023, 120_000.0, 100.0, "LEAADM"),
        ("a1", 2024, 121_000.0, 100.0, "LEAADM"),
        ("s1", 2023, 70_000.0, 100.0, "GUI"),
        ("s1", 2024, 71_000.0, 100.0, "GUI"),
        ("p1", 2023, 40_000.0, 50.0, "ELMTCH"),
        ("z1", 2023, 0.0, 100.0, "ELMTCH"),
    ]
    pd.DataFrame({
        "aun": ["1"] * len(rows),
        "school_year": [row[1] for row in rows],
        "public_id": [row[0] for row in rows],
        "annual_salary": [row[2] for row in rows],
        "fte_percent": [row[3] for row in rows],
        "edf_category": [row[4] for row in rows],
        "years_in_lea": [1.0] * len(rows),
        "years_in_education": [2.0] * len(rows),
        "degree_code": ["1051"] * len(rows),
    }).to_parquet(refined / "professional_staff.parquet", index=False)
    monkeypatch.setattr("pa_edu.publish.REFINED", refined)
    salaries, _experience, retention = _salaries()
    assert salaries["1"][2023]["elementary"]["n"] == 2  # t1, t4
    assert salaries["1"][2023]["secondary"]["n"] == 2  # t2, t4
    assert salaries["1"][2023]["ungraded"]["n"] == 1
    assert salaries["1"][2023]["administrator"]["n"] == 1
    assert salaries["1"][2023]["support"]["n"] == 1
    assert retention["1"][2023]["base"] == 6
    assert retention["1"][2023]["stayed"] == 5
    assert retention["1"][2023]["rate"] == 0.83
    assert retention["1"][2023]["classroom"] == {
        "rate": 0.75,
        "base": 4,
        "stayed": 3,
        "nextYear": 2024,
    }
    assert salaries["1"][2023]["elementary"]["retention"] == 1
    assert 2024 not in retention["1"]
    years = _years_for(
        "1", {}, {}, {}, {}, {}, {}, {}, {}, {}, {},
        salaries,
        retention=retention,
    )
    assert years[2023]["retention"]["classroom"]["base"] == 4


def test_salaries_duckdb_path_handles_many_rows(tmp_path: Path, monkeypatch) -> None:
    """Regression guard: aggregation stays vectorized (seconds, not minutes)."""
    import time

    refined = tmp_path / "refined"
    refined.mkdir()
    rows = 80_000
    years = np.asarray([2022 + (index % 3) for index in range(rows)])
    frame = pd.DataFrame({
        "aun": [str(index % 200) for index in range(rows)],
        "school_year": years,
        "public_id": [str(index) for index in range(rows)],
        "annual_salary": np.linspace(20_000, 210_000, rows),
        "fte_percent": np.full(rows, 100.0),
        "edf_category": np.where(np.arange(rows) % 2 == 0, "ELMTCH", "SECTCH"),
        "years_in_lea": np.linspace(0, 45, rows),
        "years_in_education": np.linspace(0, 45, rows),
        "degree_code": np.where(np.arange(rows) % 3 == 0, "1054", "1051"),
    })
    frame.to_parquet(refined / "professional_staff.parquet", index=False)
    monkeypatch.setattr("pa_edu.publish.REFINED", refined)
    started = time.perf_counter()
    salaries, experience, retention = _salaries()
    elapsed = time.perf_counter() - started
    assert elapsed < 8.0, f"_salaries took {elapsed:.1f}s on {rows} rows"
    assert len(salaries) == 200
    assert experience
    assert retention


def test_experience_hist_bins_integer_years() -> None:
    frame = pd.DataFrame({
        "years_in_lea": [0, 1, 1, 5, 40, 42, None],
        "years_in_education": [2, 3, 4, 10, 25, 30, 8],
        "annual_salary": [40_000, 45_000, 50_000, 60_000, 80_000, 90_000, 55_000],
        "degree_code": ["1054", "1054", "1051", "1055", "1054", "1051", "1054"],
    })
    edges = np.asarray(EXPERIENCE_EDGES, dtype=float)
    stats = _experience_stats(frame, "years_in_lea", "years_in_education", edges)
    assert stats is not None
    assert stats["n"] == 6
    assert stats["min"] == 0
    assert stats["max"] == 42
    assert len(stats["hist"]) == len(EXPERIENCE_EDGES) + 1
    assert stats["hist"][0] == 1  # under 1 year
    assert stats["hist"][1] == 2  # 1 year
    assert stats["hist"][5] == 1  # 5 years
    assert stats["hist"][-1] == 2  # 40+
    assert stats["bins"][1]["n"] == 2
    assert stats["bins"][1]["meanSalary"] == 47_500
    assert stats["bins"][1]["eduYears"] == 3.5

    document = lea_document(
        {"aun": "1", "name": "One"},
        {2024: {"experience": {"elementary": {"lea": stats}}}},
    )
    assert document["years"]["2024"]["experience"]["elementary"]["lea"]["n"] == 6


def test_county_ranks_order_highest_first() -> None:
    profiles = [
        {"aun": "1", "name": "Alpha", "county": "Fayette", "category": "school_district"},
        {"aun": "2", "name": "Beta", "county": "Fayette", "category": "school_district"},
        {"aun": "3", "name": "Other", "county": "Greene", "category": "school_district"},
    ]
    grades = {"1": {2024: {"012": 100}}, "2": {2024: {"012": 300}}, "3": {2024: {"012": 900}}}
    actual = {"1": {2024: {"1000": 50}}, "2": {2024: {"1000": 200}}}
    budget = {"1": {2024: {"1000": 60}}, "2": {2024: {"1000": 180}}}
    keystone = {
        "1": {2024: {"algebra_i": {"011": {"All Students": {"n": 100, "pct": 50.0}}}}},
        "2": {2024: {"algebra_i": {"011": {"All Students": {"n": 120, "pct": 70.0}}}}},
    }
    pssa = {
        "1": {2024: {"math": {"total": {"All Students": {"n": 80, "pct": 40.0}}}}},
        "2": {2024: {"math": {"total": {"All Students": {"n": 90, "pct": 65.0}}}}},
    }
    ranks = _county_ranks(profiles, grades, actual, budget, {}, keystone, pssa)
    assert ranks["2"][2024]["enrollment"]["rank"] == 1
    assert ranks["1"][2024]["enrollment"]["rank"] == 2
    assert ranks["1"][2024]["enrollment"]["of"] == 2
    assert [peer["aun"] for peer in ranks["1"][2024]["enrollment"]["peers"]] == ["2", "1"]
    assert ranks["2"][2024]["perStudent"]["rank"] == 1
    assert ranks["2"][2024]["keystone_algebra_i"]["rank"] == 1
    assert ranks["1"][2024]["keystone_algebra_i"]["rank"] == 2
    assert ranks["2"][2024]["pssa_math"]["rank"] == 1
    assert ranks["1"][2024]["pssa_math"]["rank"] == 2
    assert "3" not in ranks or 2024 not in ranks.get("3", {}) or "actual" not in ranks.get("3", {}).get(2024, {})


def test_staff_ranks_use_classroom_teachers_and_enrollment() -> None:
    profiles = [
        {"aun": "1", "name": "Alpha", "county": "Fayette", "category": "school_district"},
        {"aun": "2", "name": "Beta", "county": "Fayette", "category": "school_district"},
        {"aun": "3", "name": "Admins", "county": "Fayette", "category": "school_district"},
    ]
    grades = {
        "1": {2024: {"012": 300}},
        "2": {2024: {"012": 200}},
        "3": {2024: {"012": 100}},
    }
    salaries = {
        "1": {2024: {
            "elementary": {"n": 10, "median": 70_000},
            "secondary": {"n": 10, "median": 80_000},
            "ungraded": {"n": 4, "median": 75_000},
            "administrator": {"n": 40, "median": 120_000},
        }},
        "2": {2024: {
            "elementary": {"n": 10, "median": 60_000},
            "secondary": {"n": 10, "median": 90_000},
            "ungraded": {"n": 2, "median": 65_000},
        }},
        "3": {2024: {"administrator": {"n": 5, "median": 100_000}}},
    }
    retention = {
        "1": {2024: {"classroom": {"rate": 0.9, "base": 20, "stayed": 18, "nextYear": 2025}}},
        "2": {2024: {"classroom": {"rate": 0.5, "base": 20, "stayed": 10, "nextYear": 2025}}},
    }
    ranks = _county_ranks(
        profiles, grades, {}, {}, {},
        salaries=salaries, retention=retention,
    )
    ratio = ranks["1"][2024]["studentsPerTeacher"]
    assert ratio["rank"] == 1
    assert ratio["of"] == 2
    assert [peer["value"] for peer in ratio["peers"]] == [12.5, 9.0909]
    assert "studentsPerTeacher" not in ranks["3"][2024]
    assert ranks["1"][2024]["elementaryMedian"]["rank"] == 1
    assert ranks["2"][2024]["secondaryMedian"]["rank"] == 1
    assert ranks["1"][2024]["ungradedMedian"]["rank"] == 1
    assert ranks["2"][2024]["ungradedMedian"]["rank"] == 2
    assert ranks["1"][2024]["classroomRetention"]["rank"] == 1
    assert ranks["1"][2024]["classroomRetention"]["peers"][0]["value"] == 90.0


def test_per_student_rank_uses_budget_when_actuals_are_absent() -> None:
    profiles = [
        {"aun": "1", "name": "Alpha", "county": "Fayette", "category": "school_district"},
        {"aun": "2", "name": "Beta", "county": "Fayette", "category": "school_district"},
    ]
    grades = {"1": {2025: {"012": 100}}, "2": {2025: {"012": 200}}}
    budget = {"1": {2025: {"1000": 1000}}, "2": {2025: {"1000": 1000}}}
    charter = {"1": {2025: 100.0}, "2": {2025: 50.0}}
    ranks = _county_ranks(profiles, grades, {}, budget, charter)
    peers = {peer["aun"]: peer["value"] for peer in ranks["1"][2025]["perStudent"]["peers"]}
    assert peers["1"] == 9
    assert peers["2"] == 4.75
    assert ranks["1"][2025]["perStudent"]["rank"] == 1
    assert ranks["2"][2025]["perStudent"]["rank"] == 2


def test_budget_per_student_uses_the_latest_prior_charter_tuition() -> None:
    profiles = [
        {"aun": "1", "name": "Alpha", "county": "Fayette", "category": "school_district"},
        {"aun": "2", "name": "Beta", "county": "Fayette", "category": "school_district"},
    ]
    grades = {"1": {2025: {"012": 100}}, "2": {2025: {"012": 100}}}
    budget = {"1": {2025: {"1000": 1000}}, "2": {2025: {"1000": 1000}}}
    charter = {"1": {2024: 100.0, 2023: 50.0}, "2": {2024: 200.0}}
    ranks = _county_ranks(profiles, grades, {}, budget, charter)
    peers = {peer["aun"]: peer["value"] for peer in ranks["1"][2025]["perStudent"]["peers"]}
    assert peers["1"] == 9
    assert peers["2"] == 8


def test_per_student_rank_does_not_mix_budget_with_actuals() -> None:
    profiles = [
        {"aun": "1", "name": "Alpha", "county": "Fayette", "category": "school_district"},
        {"aun": "2", "name": "Beta", "county": "Fayette", "category": "school_district"},
        {"aun": "3", "name": "Gamma", "county": "Fayette", "category": "school_district"},
    ]
    grades = {
        "1": {2024: {"012": 100}},
        "2": {2024: {"012": 100}},
        "3": {2024: {"012": 100}},
    }
    actual = {"1": {2024: {"1000": 500}}, "2": {2024: {"1000": 200}}}
    budget = {
        "1": {2024: {"1000": 9000}},
        "2": {2024: {"1000": 9000}},
        "3": {2024: {"1000": 9000}},
    }
    charter = {"1": {2024: 100.0}}
    ranks = _county_ranks(profiles, grades, actual, budget, charter)
    peers = {peer["aun"]: peer["value"] for peer in ranks["1"][2024]["perStudent"]["peers"]}
    assert peers == {"1": 4, "2": 2}
    assert ranks["1"][2024]["perStudent"]["of"] == 2
    assert "perStudent" not in ranks["3"][2024]


def test_act1_rides_along_on_a_year_that_already_exists() -> None:
    years = _years_for(
        "101260303",
        {},
        {},
        {},
        {"101260303": {2024: {"1000": 5}, 2017: {"1000": 1}}},
        {},
        {},
        {},
        {},
        {},
        {},
        {},
        act1={"101260303": {2024: 7.8, 2027: 5.3}},
        act1_base={2024: 5.3},
    )
    assert years[2024]["act1"] == 7.8
    assert years[2024]["act1Base"] == 5.3
    assert "act1" not in years[2017]
    assert 2027 not in years
    assert _percent_points(0.078) == 7.8
    document = lea_document({"aun": "101260303"}, {2024: {"act1": 7.8}})
    assert document["years"]["2024"]["act1"] == 7.8


def test_revenue_chain_keeps_filled_rollups_in_order() -> None:
    assert _revenue_chain("6000", None, "") == ["6000"]
    assert _revenue_chain("6000", "6100", "6110") == ["6000", "6100", "6110"]


def test_income_rides_along_on_a_year_that_already_exists() -> None:
    income_actual = {
        "124150503": {
            2024: {"6111": {"a": 10, "p": ["6000", "6100", "6110"]}},
            2027: {"6111": {"a": 1}},
        }
    }
    income_budget = {
        "124150503": {
            2024: {"6111": {"a": 8, "p": ["6000", "6100", "6110"]}},
            2026: {"6111": {"a": 3}},
        }
    }
    years = _years_for(
        "124150503",
        {},
        {},
        {},
        {},
        {},
        {"124150503": {2024: {"1000": 5}}},
        {"124150503": {2024: {"1000": 4}, 2026: {"1000": 1}}},
        {},
        {},
        {},
        {},
        income_actual=income_actual,
        income_budget=income_budget,
    )
    assert years[2024]["incomeActual"]["6111"]["a"] == 10
    assert years[2024]["incomeBudget"]["6111"]["a"] == 8
    assert years[2026]["incomeBudget"]["6111"]["a"] == 3
    assert "incomeActual" not in years[2026]
    assert 2027 not in years
    document = lea_document({"aun": "124150503"}, {2024: {"incomeActual": {"6111": {"a": 10}}}})
    assert document["years"]["2024"]["incomeActual"]["6111"]["a"] == 10


def test_mills_ride_along_on_a_budget_year() -> None:
    years = _years_for(
        "124150503",
        {},
        {},
        {},
        {"124150503": {2025: {"1000": 1}}},
        {},
        {},
        {},
        {},
        {},
        {},
        {},
        mills={"124150503": {
            2025: [{"county": "Chester", "mills": 36}],
            2027: [{"county": "Chester", "mills": 37}],
        }},
    )
    assert years[2025]["mills"][0]["mills"] == 36
    assert 2027 not in years


def test_charter_and_homeschool_ride_along_on_enrollment_years() -> None:
    years = _years_for(
        "124150503",
        {"124150503": {2024: {"012": 5000}, 2023: {"012": 5100}}},
        {},
        {},
        {},
        {},
        {},
        {},
        {},
        {},
        {},
        {},
        charter_adm={"124150503": {2024: 116.7, 2027: 200.0}},
        home_education={"124150503": {2024: 120.0, 2027: 130.0}},
    )
    assert years[2024]["charterAdm"] == 116.7
    assert years[2024]["homeEducation"] == 120.0
    assert "charterAdm" not in years[2023]
    assert 2027 not in years
    document = lea_document(
        {"aun": "124150503"},
        {2024: {"grades": {"012": 1}, "charterAdm": 116.7, "homeEducation": 120.0}},
    )
    assert document["years"]["2024"]["charterAdm"] == 116.7


def test_saipe_rides_along_on_school_district_years() -> None:
    population = {
        "124150503": {
            2024: {"population_5_17": 1824, "children_5_17_in_poverty": 115},
            2022: {"population_5_17": 0},
            2027: {"population_5_17": 9, "children_5_17_in_poverty": 1},
        }
    }
    grades = {"124150503": {
        2024: {"012": 5000},
        2023: {"012": 5100},
        2022: {"012": 1},
    }}
    years = _years_for(
        "124150503",
        grades,
        {},
        {},
        {},
        {},
        {},
        {},
        {},
        {},
        {},
        {},
        district_population=population,
        category="school_district",
    )
    assert years[2024]["population517"] == 1824
    assert years[2024]["children517InPoverty"] == 115
    assert "population517" not in years[2023]
    assert "children517InPoverty" not in years[2023]
    assert years[2022]["population517"] == 0
    assert "children517InPoverty" not in years[2022]
    assert 2027 not in years
    document = lea_document(
        {"aun": "124150503", "category": "school_district"},
        {2024: {"grades": {"012": 1}, "population517": 1824, "children517InPoverty": 115}},
    )
    assert document["years"]["2024"]["population517"] == 1824
    assert document["years"]["2024"]["children517InPoverty"] == 115

    other = _years_for(
        "124150503",
        grades,
        {},
        {},
        {},
        {},
        {},
        {},
        {},
        {},
        {},
        {},
        district_population=population,
        category="charter_school",
    )
    assert "population517" not in other[2024]
    assert "children517InPoverty" not in other[2024]
    assert 2027 not in other


def test_ages517_share_ranks_school_districts_highest_first() -> None:
    profiles = [
        {"aun": "1", "name": "Alpha", "county": "Fayette", "category": "school_district"},
        {"aun": "2", "name": "Beta", "county": "Fayette", "category": "school_district"},
        {"aun": "3", "name": "Zero enrolled", "county": "Fayette", "category": "school_district"},
        {"aun": "4", "name": "No census", "county": "Fayette", "category": "school_district"},
        {"aun": "5", "name": "Zero population", "county": "Fayette", "category": "school_district"},
        {"aun": "6", "name": "Charter", "county": "Fayette", "category": "charter_school"},
        {"aun": "7", "name": "Other county", "county": "Greene", "category": "school_district"},
    ]
    grades = {
        "1": {2025: {"012": 1100}, 2024: {"012": 1000}, 2023: {"012": 800}},
        "2": {2025: {"012": 950}, 2024: {"012": 900}},
        "3": {2024: {"012": 0}},
        "4": {2024: {"012": 400}},
        "5": {2024: {"012": 100}},
        "6": {2024: {"012": 100}},
        "7": {2024: {"012": 500}},
    }
    population = {
        "1": {
            2026: {"population_5_17": 100},
            2024: {"population_5_17": 2000},
            2023: {"population_5_17": 2000},
        },
        "2": {2024: {"population_5_17": 1000}},
        "3": {2024: {"population_5_17": 1000}},
        "5": {2024: {"population_5_17": 0}, 2023: {"population_5_17": 500}},
        "6": {2024: {"population_5_17": 100}},
        "7": {2024: {"population_5_17": 500}},
    }
    ranks = _county_ranks(profiles, grades, {}, {}, {}, district_population=population)
    peers = {peer["aun"]: peer["value"] for peer in ranks["1"][2024]["ages517Share"]["peers"]}
    assert peers == {"2": 90.0, "1": 50.0, "3": 0.0}
    assert ranks["2"][2024]["ages517Share"]["rank"] == 1
    assert ranks["1"][2024]["ages517Share"]["rank"] == 2
    assert ranks["3"][2024]["ages517Share"]["rank"] == 3
    assert ranks["1"][2024]["ages517Share"]["of"] == 3
    assert "ages517Share" not in ranks["4"][2024]
    assert "ages517Share" not in ranks["5"][2024]
    assert "ages517Share" not in ranks.get("6", {}).get(2024, {})
    assert "ages517Share" not in ranks.get("7", {}).get(2024, {})
    # One district in 2023 is not a county rank.
    assert "ages517Share" not in ranks.get("1", {}).get(2023, {})
    # 2025 enrollment uses the 2024 Census count. The 2026 count is later, so it stays put.
    later = {peer["aun"]: peer["value"] for peer in ranks["1"][2025]["ages517Share"]["peers"]}
    assert later == {"2": 95.0, "1": 55.0}
    assert _latest_population_5_17(population["1"], 2025) == 2000
    assert _latest_population_5_17(population["5"], 2024) == 0
    assert _latest_population_5_17(population.get("4"), 2024) is None
    assert _ages517_share(1500, 1000) == 150.0
    assert _ages517_share(0, 1000) == 0.0
    assert _ages517_share(100, 0) is None
    assert _ages517_share(None, 1000) is None
    assert _ages517_share(100, None) is None


def test_graduation_rides_along_on_an_existing_year() -> None:
    years = _years_for(
        "124150002",
        {"124150002": {2024: {"012": 100}}},
        {},
        {},
        {},
        {},
        {},
        {},
        {},
        {},
        {},
        {},
        graduation={
            "124150002": {
                2024: {"4": {"grads": 180, "cohort": 301, "rate": 0.598}},
                2027: {"4": {"grads": 1, "cohort": 2, "rate": 0.5}},
            }
        },
    )
    assert years[2024]["graduation"]["4"]["grads"] == 180
    assert 2027 not in years


def test_graduation_rank_uses_the_four_year_rate() -> None:
    profiles = [
        {"aun": "1", "name": "Low", "county": "Adams"},
        {"aun": "2", "name": "High", "county": "Adams"},
    ]
    ranks = _county_ranks(
        profiles,
        {},
        {},
        {},
        {},
        graduation={
            "1": {2024: {"4": {"rate": 0.5}}},
            "2": {2024: {"4": {"rate": 0.9}}},
        },
    )
    assert ranks["2"][2024]["graduation"]["rank"] == 1
    assert ranks["1"][2024]["graduation"]["rank"] == 2
    assert ranks["2"][2024]["graduation"]["peers"][0]["value"] == 90


def _pssa_result(aun: str, year: int, subject: str, grade: str, scored: int, proficient) -> dict:
    return {
        "aun": aun,
        "school_year": year,
        "assessment": "pssa",
        "subject": subject,
        "grade": grade,
        "student_group": "All Students",
        "number_scored": scored,
        "pct_advanced": 10.0,
        "pct_proficient": 30.0,
        "pct_basic": 20.0,
        "pct_below_basic": 40.0,
        "pct_proficient_and_above": proficient,
        "lea_name": "Name",
        "county": "Chester",
        "document_id": "district-doc",
    }


def test_pssa_publishes_one_school_lea_and_keeps_the_district_workbook(tmp_path: Path, monkeypatch) -> None:
    """A charter is its school row. A district building is not the district total.

    A charter year with no combined percent uses advanced plus proficient.
    A district year with no combined percent stays empty. A school cell with
    one level percent missing stays empty.
    """
    refined = tmp_path / "refined"
    refined.mkdir()
    district = _pssa_result("112011103", 2024, "math", "total", 80, 40.0)
    district_grade = _pssa_result("112011103", 2024, "math", "003", 20, 35.0)
    district_blank = _pssa_result("112011103", 2021, "math", "008", 90, None)
    stray_charter = _pssa_result("124150002", 2024, "math", "total", 9, 1.0)
    phila = _pssa_result("126000001", 2024, "math", "total", 100, 30.0)
    phila_ela = _pssa_result("126000001", 2024, "ela", "total", 100, 50.0)
    chester = _pssa_result("110000001", 2024, "math", "total", 40, 10.0)
    pd.DataFrame([district, district_grade, district_blank, stray_charter, phila, phila_ela, chester]).to_parquet(
        refined / "assessment_result.parquet", index=False,
    )
    early = _pssa_result("124150002", 2021, "math", "total", 44, None)
    early["pct_advanced"] = 10.4
    early["pct_proficient"] = 25.9
    early_grade = _pssa_result("124150002", 2021, "math", "005", 8, None)
    early_grade["pct_advanced"] = None
    early_grade["pct_proficient"] = None
    partial = _pssa_result("126000002", 2021, "math", "total", 20, None)
    partial["pct_proficient"] = None
    school_rows = [
        {**_pssa_result("112011103", 2024, "math", "total", 15, 99.0), "school_number": "1", "school_name": "Building"},
        {**_pssa_result("124150002", 2024, "math", "total", 50, 70.0), "school_number": "7691", "school_name": "Cyber"},
        {**_pssa_result("124150002", 2024, "math", "003", 12, 55.0), "school_number": "7691", "school_name": "Cyber"},
        {**_pssa_result("124150002", 2024, "ela", "total", 48, 60.0), "school_number": "7691", "school_name": "Cyber"},
        {**early, "school_number": "7691", "school_name": "Cyber", "document_id": "school-2021"},
        {**early_grade, "school_number": "7691", "school_name": "Cyber", "document_id": "school-2021"},
        {**_pssa_result("124150002", 2024, "science", "total", 40, 80.0), "school_number": "7691", "school_name": "Cyber"},
        {**_pssa_result("124150002", 2024, "math", "011", 30, 90.0), "school_number": "7691", "school_name": "Cyber"},
        {**_pssa_result("123456789", 2024, "math", "total", 10, 10.0), "school_number": "1", "school_name": "One"},
        {**_pssa_result("123456789", 2024, "math", "total", 10, 90.0), "school_number": "2", "school_name": "Two"},
        {**_pssa_result("102020001", 2024, "math", "011", 20, 50.0), "school_number": "9", "school_name": "High"},
        {**partial, "school_number": "3", "school_name": "Early"},
        {
            **_pssa_result("124150002", 2024, "algebra_i", "011", 40, 22.0),
            "assessment": "keystone",
            "school_number": "7691",
            "school_name": "Cyber",
        },
    ]
    pd.DataFrame(school_rows).to_parquet(refined / "assessment_result_school.parquet", index=False)
    pd.DataFrame([
        {"aun": "112011103", "category": "school_district"},
        {"aun": "126000001", "category": "school_district"},
        {"aun": "110000001", "category": "school_district"},
        {"aun": "124150002", "category": "charter_school"},
        {"aun": "123456789", "category": "charter_school"},
        {"aun": "102020001", "category": "charter_school"},
        {"aun": "126000002", "category": "charter_school"},
    ]).to_parquet(refined / "lea.parquet", index=False)
    monkeypatch.setattr("pa_edu.publish.REFINED", refined)

    pssa = _assessment(duckdb.connect(), "pssa")
    district_total = pssa["112011103"][2024]["math"]["total"]["All Students"]
    assert district_total == {"n": 80, "pct": 40.0}
    assert pssa["112011103"][2024]["math"]["003"]["All Students"]["pct"] == 35.0
    assert pssa["112011103"][2021]["math"]["008"]["All Students"] == {"n": 90}
    charter = pssa["124150002"][2024]["math"]["total"]["All Students"]
    assert charter == {"n": 50, "pct": 70.0}
    assert pssa["124150002"][2024]["math"]["003"]["All Students"]["pct"] == 55.0
    assert pssa["124150002"][2024]["ela"]["total"]["All Students"]["pct"] == 60.0
    early_cell = pssa["124150002"][2021]["math"]["total"]["All Students"]
    assert early_cell == {"n": 44, "pct": 36.3}
    assert pssa["124150002"][2021]["math"]["005"]["All Students"] == {"n": 8}
    assert "science" not in pssa["124150002"][2024]
    assert "011" not in pssa["124150002"][2024]["math"]
    assert "123456789" not in pssa
    assert "102020001" not in pssa
    assert pssa["126000002"][2021]["math"]["total"]["All Students"] == {"n": 20}

    years = _years_for(
        "124150002", {}, {}, {}, {}, pssa, {}, {}, {}, {}, {}, {},
    )
    document = lea_document(
        {"aun": "124150002", "name": "Cyber", "county": "Philadelphia", "category": "charter_school"},
        years,
    )
    assert document["years"]["2021"]["pssa"]["math"]["total"]["All Students"] == {"n": 44, "pct": 36.3}
    assert document["years"]["2024"]["pssa"]["math"]["003"]["All Students"]["pct"] == 55.0

    profiles = [
        {"aun": "112011103", "name": "Alpha", "county": "Fayette", "category": "school_district"},
        {"aun": "126000001", "name": "Phila", "county": "Philadelphia", "category": "school_district"},
        {"aun": "110000001", "name": "Chester", "county": "Chester", "category": "school_district"},
        {"aun": "124150002", "name": "Cyber", "county": "Philadelphia", "category": "charter_school"},
        {"aun": "123456789", "name": "Two", "county": "Philadelphia", "category": "charter_school"},
        {"aun": "102020001", "name": "High", "county": "Philadelphia", "category": "charter_school"},
        {"aun": "126000002", "name": "Early", "county": "Philadelphia", "category": "charter_school"},
    ]
    ranks = _county_ranks(profiles, {}, {}, {}, {}, pssa=pssa)
    peers = [peer["aun"] for peer in ranks["124150002"][2024]["pssa_math"]["peers"]]
    assert peers == ["124150002", "126000001"]
    assert ranks["124150002"][2024]["pssa_math"]["rank"] == 1
    assert ranks["126000001"][2024]["pssa_math"]["rank"] == 2
    assert "pssa_math" not in ranks.get("124150002", {}).get(2021, {})
    assert "126000002" not in ranks or 2021 not in ranks.get("126000002", {})
    assert "pssa_ela" in ranks["124150002"][2024]


def _keystone_result(
    aun: str,
    year: int,
    subject: str,
    scored: int,
    proficient,
    *,
    advanced: float = 1.0,
    proficient_level: float = 2.0,
    group: str = "All Students",
    document_id: str = "district-key",
) -> dict:
    return {
        "aun": aun,
        "school_year": year,
        "assessment": "keystone",
        "subject": subject,
        "grade": "011",
        "student_group": group,
        "number_scored": scored,
        "pct_advanced": advanced,
        "pct_proficient": proficient_level,
        "pct_basic": 3.0,
        "pct_below_basic": 4.0,
        "pct_proficient_and_above": proficient,
        "lea_name": "Name",
        "county": "Chester",
        "document_id": document_id,
    }


def _keystone_school(row: dict, number: str, name: str) -> dict:
    return {**row, "school_number": number, "school_name": name}


def test_keystone_publishes_one_school_lea_and_skips_a_sum(tmp_path: Path, monkeypatch) -> None:
    """A charter or one-school technical school is its school row.

    A district building is not the district total. Two schools are not added.
    A charter year with no combined percent uses advanced plus proficient.
    A district year with no combined percent stays empty.
    """
    refined = tmp_path / "refined"
    refined.mkdir()
    district_rows = [
        _keystone_result("112011103", 2024, "algebra_i", 80, 20.0),
        _keystone_result("112011103", 2024, "literature", 80, 60.0),
        _keystone_result("112011103", 2024, "biology", 80, 45.0),
        _keystone_result(
            "112011103", 2022, "algebra_i", 100, None, advanced=10.0, proficient_level=30.0,
        ),
        _keystone_result("102020001", 2024, "algebra_i", 9, 1.0, document_id="stray"),
        _keystone_result("126515001", 2024, "algebra_i", 90, 30.0),
        _keystone_result("126515001", 2024, "literature", 90, 70.0),
        _keystone_result("126515001", 2024, "biology", 90, 55.0),
    ]
    pd.DataFrame(district_rows).to_parquet(
        refined / "assessment_result.parquet", index=False,
    )
    school_rows = [
        _keystone_school(
            _keystone_result("112011103", 2024, "algebra_i", 15, 99.0, document_id="school-key"),
            "1367", "Avon Grove HS",
        ),
        _keystone_school(
            _keystone_result(
                "112011103", 2022, "algebra_i", 241, None,
                advanced=4.1, proficient_level=56.4, document_id="school-2022",
            ),
            "1367", "Avon Grove HS",
        ),
        _keystone_school(
            _keystone_result("102020001", 2024, "algebra_i", 40, 22.8, document_id="school-key"),
            "7727", "City CHS",
        ),
        _keystone_school(
            _keystone_result("102020001", 2024, "literature", 41, 80.0, document_id="school-key"),
            "7727", "City CHS",
        ),
        _keystone_school(
            _keystone_result("102020001", 2024, "biology", 39, 40.0, document_id="school-key"),
            "7727", "City CHS",
        ),
        _keystone_school(
            _keystone_result(
                "102020001", 2024, "algebra_i", 12, 18.0,
                group="Multi-Racial (not Hispanic)", document_id="school-key",
            ),
            "7727", "City CHS",
        ),
        _keystone_school(
            _keystone_result(
                "102020001", 2022, "algebra_i", 30, None,
                advanced=10.0, proficient_level=30.0, document_id="school-2022",
            ),
            "7727", "City CHS",
        ),
        _keystone_school(
            _keystone_result("115210001", 2024, "algebra_i", 25, 15.0, document_id="school-key"),
            "8001", "One Campus CTC",
        ),
        _keystone_school(
            _keystone_result("115210001", 2024, "literature", 25, 70.0, document_id="school-key"),
            "8001", "One Campus CTC",
        ),
        _keystone_school(
            _keystone_result("115210001", 2024, "biology", 25, 50.0, document_id="school-key"),
            "8001", "One Campus CTC",
        ),
        _keystone_school(
            _keystone_result("115210001", 2022, "algebra_i", 20, 10.0, document_id="school-2022"),
            "8001", "One Campus CTC",
        ),
        _keystone_school(
            _keystone_result("114060557", 2024, "algebra_i", 10, 1.0, document_id="school-key"),
            "6304", "Berks CTC East",
        ),
        _keystone_school(
            _keystone_result("114060557", 2024, "algebra_i", 10, 2.0, document_id="school-key"),
            "7068", "Berks CTC West",
        ),
        _keystone_school(
            _keystone_result("123456789", 2023, "algebra_i", 11, 11.0, document_id="school-2023"),
            "1", "Only Campus",
        ),
        _keystone_school(
            _keystone_result("123456789", 2024, "algebra_i", 11, 3.0, document_id="school-key"),
            "1", "East",
        ),
        _keystone_school(
            _keystone_result("123456789", 2024, "algebra_i", 11, 4.0, document_id="school-key"),
            "2", "West",
        ),
        _keystone_school(
            _keystone_result("126000001", 2024, "algebra_i", 50, 5.0, document_id="school-key"),
            "9", "District Building",
        ),
    ]
    pd.DataFrame(school_rows).to_parquet(refined / "assessment_result_school.parquet", index=False)
    pd.DataFrame([
        {"aun": "112011103", "category": "school_district"},
        {"aun": "126515001", "category": "school_district"},
        {"aun": "102020001", "category": "charter_school"},
        {"aun": "115210001", "category": "career_and_technical_center"},
        {"aun": "114060557", "category": "career_and_technical_center"},
        {"aun": "123456789", "category": "charter_school"},
        {"aun": "126000001", "category": "school_district"},
        {"aun": "110000001", "category": "school_district"},
        {"aun": "999000001", "category": "charter_school"},
    ]).to_parquet(refined / "lea.parquet", index=False)
    monkeypatch.setattr("pa_edu.publish.REFINED", refined)
    connection = duckdb.connect()

    keystone = _keystone(connection)
    district_cell = keystone["112011103"][2024]["algebra_i"]["011"]["All Students"]
    assert district_cell["pct"] == 20.0
    assert district_cell["n"] == 80
    early = keystone["112011103"][2022]["algebra_i"]["011"]["All Students"]
    assert early == {"n": 100, "advanced": 10.0, "proficient": 30.0, "basic": 3.0, "below": 4.0}
    assert "pct" not in early
    building = connection.execute("""
        SELECT school_year, pct_proficient_and_above
        FROM assessment_result_school
        WHERE aun = '112011103' AND subject = 'algebra_i'
        ORDER BY school_year
    """).fetchall()
    assert building == [(2022, 60.5), (2024, 99.0)]

    charter = keystone["102020001"][2024]["algebra_i"]["011"]["All Students"]
    assert charter["pct"] == 22.8
    assert charter["n"] == 40
    assert keystone["102020001"][2024]["literature"]["011"]["All Students"]["pct"] == 80.0
    assert keystone["102020001"][2024]["biology"]["011"]["All Students"]["pct"] == 40.0
    assert keystone["102020001"][2024]["algebra_i"]["011"]["Multi-ethnic (not Hispanic)"]["pct"] == 18.0
    charter_early = keystone["102020001"][2022]["algebra_i"]["011"]["All Students"]
    assert charter_early["pct"] == 40.0
    assert charter_early["n"] == 30
    assert charter_early["advanced"] == 10.0
    assert charter_early["proficient"] == 30.0

    assert keystone["115210001"][2024]["algebra_i"]["011"]["All Students"]["pct"] == 15.0
    assert "114060557" not in keystone
    assert 2024 not in keystone["123456789"]
    assert keystone["123456789"][2023]["algebra_i"]["011"]["All Students"]["pct"] == 11.0
    assert "126000001" not in keystone
    assert "999000001" not in keystone

    schools_only = _keystone_schools_only(connection)
    assert schools_only == {"114060557"}
    flagged = lea_document(
        {"aun": "114060557", "name": "Berks CTC", "county": "Berks", "category": "career_and_technical_center"},
        _years_for("114060557", {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, keystone=keystone),
        keystone_schools_only=True,
    )
    assert flagged["keystoneSchoolsOnly"] is True
    assert flagged["years"] == {}
    plain = lea_document(
        {"aun": "102020001", "name": "City CHS", "county": "Chester", "category": "charter_school"},
        _years_for("102020001", {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, keystone=keystone),
    )
    assert "keystoneSchoolsOnly" not in plain
    assert plain["years"]["2024"]["keystone"]["algebra_i"]["011"]["All Students"]["pct"] == 22.8
    assert plain["years"]["2022"]["keystone"]["algebra_i"]["011"]["All Students"]["pct"] == 40.0

    profiles = [
        {"aun": "112011103", "name": "Avon Grove", "county": "Chester", "category": "school_district"},
        {"aun": "126515001", "name": "Philadelphia", "county": "Philadelphia", "category": "school_district"},
        {"aun": "102020001", "name": "City CHS", "county": "Philadelphia", "category": "charter_school"},
        {"aun": "115210001", "name": "One Campus", "county": "Chester", "category": "career_and_technical_center"},
        {"aun": "114060557", "name": "Berks CTC", "county": "Chester", "category": "career_and_technical_center"},
        {"aun": "110000001", "name": "Greene", "county": "Greene", "category": "school_district"},
    ]
    ranks = _county_ranks(profiles, {}, {}, {}, {}, keystone=keystone)
    # The charter's directory county is Philadelphia, the administrative office.
    philly = ranks["102020001"][2024]["keystone_algebra_i"]
    assert [peer["aun"] for peer in philly["peers"]] == ["126515001", "102020001"]
    assert philly["rank"] == 2
    assert [peer["aun"] for peer in ranks["102020001"][2024]["keystone_literature"]["peers"]] == [
        "102020001", "126515001",
    ]
    assert [peer["aun"] for peer in ranks["102020001"][2024]["keystone_biology"]["peers"]] == [
        "126515001", "102020001",
    ]
    chester = ranks["112011103"][2024]["keystone_algebra_i"]
    assert [peer["aun"] for peer in chester["peers"]] == ["112011103", "115210001"]
    assert [peer["aun"] for peer in ranks["115210001"][2024]["keystone_literature"]["peers"]] == [
        "115210001", "112011103",
    ]
    assert [peer["aun"] for peer in ranks["115210001"][2024]["keystone_biology"]["peers"]] == [
        "115210001", "112011103",
    ]
    assert "102020001" not in {peer["aun"] for peer in chester["peers"]}
    assert "114060557" not in ranks or "keystone_algebra_i" not in ranks.get("114060557", {}).get(2024, {})
    assert "110000001" not in {peer["aun"] for peer in chester["peers"]}
    for aun in ("112011103", "102020001", "115210001", "126515001"):
        assert "keystone_algebra_i" not in ranks.get(aun, {}).get(2022, {})


def test_keystone_without_a_school_file_stays_on_the_district_workbook(tmp_path: Path, monkeypatch) -> None:
    refined = tmp_path / "refined"
    refined.mkdir()
    pd.DataFrame([
        _keystone_result("112011103", 2024, "algebra_i", 80, 20.0),
    ]).to_parquet(refined / "assessment_result.parquet", index=False)
    monkeypatch.setattr("pa_edu.publish.REFINED", refined)
    connection = duckdb.connect()
    keystone = _keystone(connection)
    assert keystone["112011103"][2024]["algebra_i"]["011"]["All Students"]["pct"] == 20.0
    assert _keystone_schools_only(connection) == set()


def test_keystone_year_is_kept_on_its_own() -> None:
    years = _years_for(
        "124150503",
        {},
        {},
        {},
        {},
        {},
        {},
        {},
        {},
        {},
        {},
        {},
        {},
        {},
        {},
        keystone={
            "124150503": {
                2024: {
                    "algebra_i": {"011": {"All Students": {"n": 410, "pct": 64.9}}},
                    "literature": {"011": {"All Students": {"n": 413, "pct": 81.6}}},
                    "biology": {"011": {"All Students": {"n": 411, "pct": 67.6}}},
                }
            }
        },
    )
    assert years[2024]["keystone"]["literature"]["011"]["All Students"]["pct"] == 81.6
    document = lea_document({"aun": "124150503", "name": "Avon Grove"}, years)
    algebra = document["years"]["2024"]["keystone"]["algebra_i"]["011"]["All Students"]
    assert algebra["n"] == 410
    assert algebra["pct"] == 64.9


def test_read_git_build_stamps_head_and_utc() -> None:
    import subprocess

    root = Path(__file__).resolve().parents[1]
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    committed = subprocess.check_output(["git", "log", "-1", "--format=%aI"], cwd=root, text=True).strip()
    stamp = read_git_build(datetime(2026, 11, 14, 10, 4, 5, tzinfo=timezone(timedelta(hours=-5))))
    assert stamp["commit"] == head
    assert stamp["commitShort"] == head[:7]
    assert stamp["commitUrl"] == f"https://github.com/bobruddy/pa_education_data/commit/{head}"
    assert stamp["committedAt"] == committed
    assert stamp["generatedAt"] == "2026-11-14T15:04:05Z"


def test_write_build_stamp_is_gzipped_json(tmp_path: Path) -> None:
    stamp = {
        "commit": "a" * 40,
        "commitShort": "aaaaaaa",
        "commitUrl": "https://github.com/bobruddy/pa_education_data/commit/" + "a" * 40,
        "committedAt": "2026-11-14T15:04:05-05:00",
        "generatedAt": "2026-11-14T20:04:05Z",
    }
    write_build_stamp(tmp_path, stamp)
    assert not (tmp_path / "build.json").exists()
    stored = json.loads(gzip.decompress((tmp_path / "build.json.gz").read_bytes()))
    assert stored == stamp


def test_write_json_stores_gzip_for_nginx(tmp_path: Path) -> None:
    target = tmp_path / "101260303.json"
    target.write_text("stale", encoding="utf-8")
    _write_json(target, {"aun": "101260303", "years": {}})
    assert not target.exists()
    compressed = (tmp_path / "101260303.json.gz").read_bytes()
    stored = json.loads(gzip.decompress(compressed))
    assert stored == {"aun": "101260303", "years": {}}
    assert JSON_GZIP_LEVEL == 1
    assert compressed[8] == 4


def test_directory_row_keeps_a_missing_actual() -> None:
    row = directory_row(
        {"aun": "101260303", "name": "Albert Gallatin", "county": "Fayette", "category": "school_district", "status": "open"},
        3000,
        None,
        100.5,
    )
    assert row["enrollment"] == 3000
    assert row["actual"] is None
    assert row["budget"] == 100.5


def test_lea_administrators_per_thousand_counts_full_time_leaadm_only(tmp_path: Path, monkeypatch) -> None:
    """Hand count: full-time LEAADM person rows ÷ October 1 enrollment, per 1,000.

    Principals (SCHADM), instructional supervisors (CORSUP), and part-time
    LEAADM stay out. Intermediate units are omitted. A missing count is not
    stored as zero, and the count does not open a year by itself.
    """
    refined = tmp_path / "refined"
    refined.mkdir()
    rows = [
        # aun, year, person, fte, category, lea type, salary
        ("1", 2023, "a", 100.0, "LEAADM", "SD", 120_000.0),
        ("1", 2023, "b", 100.0, " leaadm ", "SD", 0.0),
        ("1", 2023, "c", 100.0, "LEA Administrators", "SD", None),
        ("1", 2023, "p", 100.0, "SCHADM", "SD", 110_000.0),
        ("1", 2023, "s", 100.0, "CORSUP", "SD", 95_000.0),
        ("1", 2023, "t", 80.0, "LEAADM", "SD", 60_000.0),
        ("1", 2023, "e", 100.0, "ELMTCH", "SD", 70_000.0),
        ("1", 2024, "a", 100.0, "LEAADM", "SD", 121_000.0),
        ("2", 2023, "c1", 100.0, "LEAADM", "CS", 90_000.0),
        ("2", 2023, "c2", 100.0, "LEAADM", "CS", 91_000.0),
        ("2", 2023, "c3", 100.0, "LEAADM", "CS", 92_000.0),
        ("2", 2023, "c4", 100.0, "LEAADM", "CS", 93_000.0),
        ("9", 2023, "i1", 100.0, "LEAADM", "IU", 130_000.0),
        ("9", 2023, "i2", 100.0, "LEA ADMINISTRATORS", "IU", 131_000.0),
        ("3", 2023, "n", 100.0, "SCHADM", "SD", 100_000.0),
    ]
    pd.DataFrame({
        "aun": [row[0] for row in rows],
        "school_year": [row[1] for row in rows],
        "public_id": [row[2] for row in rows],
        "fte_percent": [row[3] for row in rows],
        "edf_category": [row[4] for row in rows],
        "lea_type_code": [row[5] for row in rows],
        "annual_salary": [row[6] for row in rows],
    }).to_parquet(refined / "professional_staff.parquet", index=False)
    monkeypatch.setattr("pa_edu.publish.REFINED", refined)

    counts = _lea_administrators()
    assert counts == {"1": {2023: 3, 2024: 1}, "2": {2023: 4}}
    assert "9" not in counts
    assert _lea_admins_per_thousand(3, 2500) == 1.2
    assert _lea_admins_per_thousand(4, 1000) == 4
    assert _lea_admins_per_thousand(0, 2500) is None
    assert _lea_admins_per_thousand(3, 0) is None
    assert _lea_admins_per_thousand(None, 2500) is None

    grades = {
        "1": {2023: {"012": 2000, "009": 500}, 2024: {"012": 2000}},
        "2": {2023: {"012": 1000}},
        "3": {2023: {"012": 800}},
        "9": {2023: {"012": 100}},
    }
    years = _years_for(
        "1",
        grades,
        {},
        {},
        {},
        {},
        {},
        {},
        {},
        {},
        {},
        {},
        lea_administrators={"1": {2023: 3, 2024: 0, 2029: 8}},
    )
    assert years[2023]["leaAdministrators"] == {"n": 3}
    assert "leaAdministrators" not in years[2024]
    assert 2029 not in years

    profiles = [
        {"aun": "1", "name": "Alpha", "county": "Fayette", "category": "school_district"},
        {"aun": "2", "name": "Beta Charter", "county": "Fayette", "category": "charter_school"},
        {"aun": "3", "name": "Gamma", "county": "Fayette", "category": "school_district"},
        {"aun": "9", "name": "IU 1", "county": "Fayette", "category": "intermediate_unit"},
    ]
    ranks = _county_ranks(
        profiles,
        grades,
        {},
        {},
        {},
        lea_administrators={**counts, "9": {2023: 10}},
    )
    peers = {peer["aun"]: peer["value"] for peer in ranks["1"][2023]["leaAdmPerThousand"]["peers"]}
    assert peers == {"2": 4, "1": 1.2}
    assert ranks["2"][2023]["leaAdmPerThousand"]["rank"] == 1
    assert ranks["1"][2023]["leaAdmPerThousand"]["rank"] == 2
    assert ranks["1"][2023]["leaAdmPerThousand"]["of"] == 2
    assert "leaAdmPerThousand" not in ranks.get("3", {}).get(2023, {})
    assert "leaAdmPerThousand" not in ranks.get("9", {}).get(2023, {})


def test_lea_administrator_roles_sum_pay_and_hide_each_salary(tmp_path: Path, monkeypatch) -> None:
    """Jobs are headcounts. The only dollar figure is the group's reported pay.

    A blank description uses the assignment code. The same code with two
    descriptions stays two jobs. A reported zero stays in the sum. A missing
    salary is left out of it. Part-time staff, principals, and intermediate
    units stay out of the count.
    """
    refined = tmp_path / "refined"
    refined.mkdir()
    rows = [
        # aun, year, person, fte, category, lea type, salary, code, description
        ("1", 2023, "asst-a", 100.0, "LEAADM", "SD", 140_000.0, "1155", "Assistant Superintendent"),
        ("1", 2023, "asst-b", 100.0, " leaadm ", "SD", None, " 1155 ", " Assistant Superintendent "),
        ("1", 2023, "sup", 100.0, "LEAADM", "SD", 180_000.0, "1150", "Superintendent"),
        ("1", 2023, "biz", 100.0, "LEAADM", "SD", 0.0, "9910", "Business Manager"),
        ("1", 2023, "blank", 100.0, "LEA Administrators", "SD", 50_000.0, "1805", None),
        ("1", 2023, "part", 80.0, "LEAADM", "SD", 90_000.0, "1150", "Superintendent"),
        ("1", 2023, "principal", 100.0, "SCHADM", "SD", 110_000.0, "1100", "Elementary Principal"),
        ("1", 2024, "only", 100.0, "LEAADM", "SD", None, "1150", "Superintendent"),
        ("9", 2023, "iu", 100.0, "LEAADM", "IU", 130_000.0, "1160", "Intermediate Unit Executive Director"),
    ]
    pd.DataFrame({
        "aun": [row[0] for row in rows],
        "school_year": [row[1] for row in rows],
        "public_id": [row[2] for row in rows],
        "fte_percent": [row[3] for row in rows],
        "edf_category": [row[4] for row in rows],
        "lea_type_code": [row[5] for row in rows],
        "annual_salary": [row[6] for row in rows],
        "assignment_code": [row[7] for row in rows],
        "assignment_description": [row[8] for row in rows],
    }).to_parquet(refined / "professional_staff.parquet", index=False)
    monkeypatch.setattr("pa_edu.publish.REFINED", refined)

    counts = _lea_administrators()
    assert "9" not in counts
    assert counts["1"][2024] == {
        "n": 1,
        "roles": [{"code": "1150", "label": "Superintendent", "n": 1}],
        "unreported": 1,
    }
    group = counts["1"][2023]
    assert group["n"] == 5
    assert group["salary"] == 370_000
    assert group["unreported"] == 1
    assert group["roles"] == [
        {"code": "1155", "label": "Assistant Superintendent", "n": 2},
        {"code": "1805", "label": "1805", "n": 1},
        {"code": "9910", "label": "Business Manager", "n": 1},
        {"code": "1150", "label": "Superintendent", "n": 1},
    ]
    assert all("salary" not in role for role in group["roles"])
    assert _lea_admins_per_thousand(group, 2500) == 2

    years = _years_for(
        "1",
        {"1": {2023: {"012": 100}, 2024: {"012": 100}}},
        {},
        {},
        {},
        {},
        {},
        {},
        {},
        {},
        {},
        {},
        lea_administrators=counts,
    )
    assert years[2023]["leaAdministrators"] == group
    assert "salary" not in years[2023]["leaAdministrators"]["roles"][0]


def test_published_charter_keeps_a_zero_and_skips_a_missing_year() -> None:
    assert _published_charter({2023: 10.0, 2021: 4.0}, 2025) == (10.0, 2023)
    assert _published_charter({2024: 0.0, 2023: 10.0}, 2024) == (0.0, 2024)
    assert _published_charter({2026: 10.0}, 2025) is None
    assert _published_charter({}, 2025) is None


def test_object_562_and_debt_service_stay_absent_when_unpublished() -> None:
    years = _years_for(
        "1",
        {"1": {2023: {"012": 10}, 2024: {"012": 10}, 2025: {"012": 10}}},
        {},
        {},
        {},
        {},
        {"1": {2023: {"1000": 5}, 2024: {"1000": 6}}},
        {"1": {2024: {"1000": 7}, 2025: {"1000": 8}}},
        {},
        {},
        {},
        {},
        charter={"1": {2024: 2.5}},
        debt_service={"1": {2023: 0, 2024: 40, 2029: 9}},
    )
    assert years[2024]["object562"] == 2.5
    assert years[2024]["charterTuition"] == 2.5
    assert "object562" not in years[2023]
    assert years[2023]["charterTuition"] == 0.0
    assert years[2023]["debtService"] == 0
    assert years[2024]["debtService"] == 40
    assert "debtService" not in years[2025]
    assert 2029 not in years


def test_charter_share_rank_uses_same_year_actuals_only() -> None:
    profiles = [
        {"aun": "1", "name": "Alpha", "county": "Fayette", "category": "school_district"},
        {"aun": "2", "name": "Beta", "county": "Fayette", "category": "school_district"},
        {"aun": "3", "name": "Charter", "county": "Fayette", "category": "charter_school"},
        {"aun": "4", "name": "No tuition", "county": "Fayette", "category": "school_district"},
    ]
    actual = {
        "1": {2024: {"1000": 800, "2000": 200}},
        "2": {2024: {"1000": 750, "2000": 250}},
        "3": {2024: {"1000": 1000}},
        "4": {2024: {"1000": 1000}},
    }
    budget = {
        "1": {2025: {"1000": 9000}},
        "2": {2025: {"1000": 9000}},
    }
    charter = {"1": {2024: 100.0}, "2": {2024: 250.0, 2023: 1.0}, "3": {2024: 500.0}}
    ranks = _county_ranks(profiles, {}, actual, budget, charter)
    peers = {peer["aun"]: peer["value"] for peer in ranks["1"][2024]["charterShare"]["peers"]}
    assert peers == {"2": 25.0, "1": 10.0}
    assert ranks["2"][2024]["charterShare"]["rank"] == 1
    assert ranks["1"][2024]["charterShare"]["of"] == 2
    assert "charterShare" not in ranks.get("3", {}).get(2024, {})
    assert "charterShare" not in ranks.get("4", {}).get(2024, {})
    assert "charterShare" not in ranks.get("1", {}).get(2025, {})


def test_debt_and_instruction_ranks_do_not_mix_budget_with_actual() -> None:
    profiles = [
        {"aun": "1", "name": "Alpha", "county": "Fayette", "category": "school_district"},
        {"aun": "2", "name": "Beta", "county": "Fayette", "category": "school_district"},
        {"aun": "3", "name": "Gamma", "county": "Fayette", "category": "charter_school"},
        {"aun": "4", "name": "Zero instruction", "county": "Fayette", "category": "school_district"},
    ]
    grades = {
        "1": {2024: {"012": 100}},
        "2": {2024: {"012": 100}},
        "3": {2024: {"012": 100}},
        "4": {2024: {"012": 100}},
    }
    budget = {
        "1": {2024: {"1000": 10_000, "5000": 9_000}},
        "2": {2024: {"1000": 5_000, "5000": 9_000}},
        "3": {2024: {"5000": 50_000}},
        "4": {2024: {"1000": 0}},
    }
    actual = {
        "1": {2024: {"1000": 1}},
        "3": {2024: {"1000": 99_999}},
    }
    ranks = _county_ranks(
        profiles,
        grades,
        actual,
        budget,
        {},
        debt_service={"1": {2024: 500}, "2": {2024: 200}},
    )
    debt = {peer["aun"]: peer["value"] for peer in ranks["1"][2024]["debtPerStudent"]["peers"]}
    assert debt == {"1": 5, "2": 2}
    assert ranks["1"][2024]["debtPerStudent"]["rank"] == 1
    assert "debtPerStudent" not in ranks.get("3", {}).get(2024, {})
    instruction = {peer["aun"]: peer["value"] for peer in ranks["1"][2024]["instructionPerStudent"]["peers"]}
    assert instruction == {"1": 100, "2": 50, "4": 0}
    assert ranks["2"][2024]["instructionPerStudent"]["rank"] == 2
    assert "instructionPerStudent" not in ranks.get("3", {}).get(2024, {})


def test_debt_service_sums_afr_function_5110_only(tmp_path: Path, monkeypatch) -> None:
    refined = tmp_path / "refined"
    refined.mkdir()
    pd.DataFrame({
        "aun": ["1", "1", "1", "1", "2"],
        "school_year": [2024, 2024, 2024, 2024, 2024],
        "fund_code": ["10", "10", "10", "20", "10"],
        "function_code": ["5110", "5110", "5120", "5110", "5110"],
        "total_amount": [10.0, 5.5, 100.0, 80.0, 0.0],
    }).to_parquet(refined / "afr_expenditure.parquet", index=False)
    monkeypatch.setattr("pa_edu.publish.REFINED", refined)
    assert _debt_service(duckdb.connect()) == {"1": {2024: 15.5}, "2": {2024: 0}}


def test_lea_administrator_count_runs_without_a_lea_type_column(tmp_path: Path, monkeypatch) -> None:
    refined = tmp_path / "refined"
    refined.mkdir()
    pd.DataFrame({
        "aun": ["1"],
        "school_year": [2023],
        "public_id": ["a"],
        "fte_percent": [100.0],
        "edf_category": ["LEAADM"],
    }).to_parquet(refined / "professional_staff.parquet", index=False)
    monkeypatch.setattr("pa_edu.publish.REFINED", refined)
    assert _lea_administrators() == {"1": {2023: 1}}
