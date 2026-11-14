import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd

from pa_edu.publish import (
    EXPERIENCE_EDGES,
    _county_ranks,
    _experience_stats,
    _percent_points,
    _salaries,
    _salary_group,
    _short_title,
    _write_json,
    _years_for,
    directory_row,
    _revenue_chain,
    lea_document,
)


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
    assert retention["1"][2023] == {"rate": 0.5, "base": 2, "stayed": 1, "nextYear": 2024}
    assert 2024 not in retention["1"]
    assert experience["1"][2023]["elementary"]["lea"]["n"] == 2


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


def test_write_json_stores_gzip_for_nginx(tmp_path: Path) -> None:
    target = tmp_path / "101260303.json"
    target.write_text("stale", encoding="utf-8")
    _write_json(target, {"aun": "101260303", "years": {}})
    assert not target.exists()
    stored = json.loads(gzip.decompress((tmp_path / "101260303.json.gz").read_bytes()))
    assert stored == {"aun": "101260303", "years": {}}


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
