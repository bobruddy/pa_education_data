from pathlib import Path

import pandas as pd
import pytest

from pa_edu.compare import _account_label, build_compare, comparison_catalog, leaf_codes, object_leaves

DISTRICTS = (
    "124150503",
    "124151902",
    "124152003",
    "124153503",
    "124154003",
    "124156503",
    "124156603",
    "124156703",
    "124157203",
    "124157802",
    "124158503",
    "124159002",
)


def test_leaf_codes_keep_a_family_that_has_no_child() -> None:
    assert leaf_codes({"1100", "1110", "3200"}) == {"1110", "3200"}
    assert leaf_codes({"3200"}) == {"3200"}


def test_object_leaves_drop_a_parent_that_has_a_child() -> None:
    assert object_leaves({"100", "110", "130"}) == {"110", "130"}
    assert object_leaves({"100"}) == {"100"}


def test_account_labels_match_the_sunburst_short_names() -> None:
    assert _account_label("REGULAR PROGRAMS – ELEMENTARY / SECONDARY") == "Regular programs"
    assert _account_label("SUPPORT SERVICES – STUDENTS") == "Students"
    assert _account_label("NONPUBLIC SCHOOL PROGRAMS (For IU") == "Nonpublic school programs"


def view_of(payload: dict, view_id: str) -> dict:
    return next(item for item in payload["views"] if item["id"] == view_id)


def test_compare_removes_charter_tuition_and_does_not_add_the_parent(tmp_path: Path) -> None:
    write_compare(tmp_path)
    payload = build_compare(tmp_path)
    assert payload["id"] == "fund10"
    assert payload["county"] == "Chester"
    assert payload["title"] == comparison_catalog()[0]["title"]
    actual = view_of(payload, "actual")
    assert actual["year"] == 2024
    assert actual["yearLabel"] == "2024–25"
    assert actual["source"]["url"] == "https://example.test/afr-2024.xlsx"
    assert actual["enrollment"]["url"] == "https://example.test/enrollment-2024.xlsx"

    by_aun = {item["aun"]: item for item in actual["districts"]}
    coatesville = by_aun["124151902"]
    assert coatesville["published"] is True
    assert coatesville["enrolled"] == 10
    assert coatesville["levels"]["1100"]["amount"] == 400
    assert coatesville["levels"]["1110"]["amount"] == 400
    assert coatesville["levels"]["1110-100"]["amount"] == 400
    assert "1100-100" not in coatesville["levels"]
    assert coatesville["levels"]["1200"]["amount"] == 50
    assert coatesville["levels"]["1210"]["amount"] == 50
    assert coatesville["levels"]["1210-100"]["amount"] == 50
    assert coatesville["levels"]["1000"]["amount"] == 450
    assert coatesville["levels"]["3200"]["amount"] == 70
    assert coatesville["levels"]["3200-100"]["amount"] == 50
    assert coatesville["levels"]["3200-500"]["amount"] == 20
    assert coatesville["levels"]["3200-510"]["amount"] == 20
    assert "1110-562" not in coatesville["levels"]
    assert coatesville["levels"]["3000"]["amount"] == 70
    assert "1300" not in coatesville["levels"]
    assert coatesville["total"] == 520
    assert coatesville["perStudent"] == 52
    assert sum(coatesville["levels"][code]["amount"] for code in ("1000", "3000")) == 520

    avon = by_aun["124150503"]
    assert avon["total"] == 80
    assert avon["levels"]["1000"]["amount"] == 80
    assert avon["levels"]["3300"]["amount"] == 0
    assert avon["perStudent"] == 20

    assert by_aun["124156503"]["published"] is False
    assert by_aun["124156503"]["enrolled"] == 1977
    assert by_aun["124152003"]["published"] is False
    assert by_aun["124153503"]["published"] is False

    published = [item["aun"] for item in actual["districts"] if item["published"]]
    assert published == ["124151902", "124150503"]
    assert by_aun["124150003"]["name"] == "Avon Grove CS"
    assert by_aun["124150003"]["published"] is False
    assert "124000000" not in by_aun
    assert "124151607" not in by_aun
    assert "123000000" not in by_aun

    assert actual["medians"]["total"] == 36
    assert actual["medians"]["1000"] == 32.5
    assert actual["nodes"]["1000"]["children"] == ["1100", "1200"]
    assert actual["nodes"]["1100"]["children"] == ["1110"]
    assert actual["nodes"]["1110"]["children"] == ["1110-100"]
    assert actual["nodes"]["1110-100"]["children"] == []
    assert actual["nodes"]["3200"]["children"] == ["3200-100", "3200-500"]
    assert actual["nodes"]["3200-500"]["children"] == ["3200-510"]
    assert actual["nodes"]["3200-510"]["label"] == "Student transportation services"
    assert actual["nodes"]["3200-510"]["children"] == []
    assert "2000" not in actual["nodes"]
    assert actual["majors"][0]["color"] == "#0c5c56"

    budget = view_of(payload, "budget")
    assert budget["year"] == 2024
    assert budget["source"]["url"] == "https://example.test/gfb-2024.xlsx"
    budget_coatesville = next(item for item in budget["districts"] if item["aun"] == "124151902")
    assert budget_coatesville["levels"]["1110-100"]["amount"] == 40
    assert budget_coatesville["total"] == 40
    assert "3200" not in budget_coatesville["levels"]

    income = view_of(payload, "income")
    assert income["year"] == 2024
    assert income["source"]["url"] == "https://example.test/afr-revenue-2024.xlsx"
    income_coatesville = next(item for item in income["districts"] if item["aun"] == "124151902")
    assert income_coatesville["levels"]["6111"]["amount"] == 80
    assert income_coatesville["levels"]["6100"]["amount"] == 80
    assert income_coatesville["levels"]["6000"]["amount"] == 80
    assert income_coatesville["total"] == 80
    assert income["nodes"]["6000"]["children"] == ["6100"]
    assert income["nodes"]["6100"]["children"] == ["6110"]
    assert income["nodes"]["6110"]["children"] == ["6111"]
    assert income["nodes"]["6111"]["label"] == "Current real estate taxes"


def test_another_county_is_a_separate_comparison(tmp_path: Path) -> None:
    write_compare(tmp_path)
    with pytest.raises(SystemExit, match="Montgomery has no general-fund Actuals"):
        build_compare(tmp_path, "Montgomery")


def test_object_562_on_a_parent_function_fails(tmp_path: Path) -> None:
    write_compare(tmp_path, charter_on_parent=True)
    with pytest.raises(SystemExit, match="object 562 is posted on parent function 1100"):
        build_compare(tmp_path)


def test_a_function_outside_the_five_majors_fails(tmp_path: Path) -> None:
    write_compare(tmp_path, extra_function="6000")
    with pytest.raises(SystemExit, match="outside the five majors"):
        build_compare(tmp_path)


def test_two_afr_documents_fail(tmp_path: Path) -> None:
    write_compare(tmp_path, second_document=True)
    with pytest.raises(SystemExit, match="more than one document"):
        build_compare(tmp_path)


def test_a_parent_object_is_not_added_on_top_of_its_children(tmp_path: Path) -> None:
    write_compare(tmp_path, parent_object=True)
    actual = view_of(build_compare(tmp_path), "actual")
    coatesville = next(item for item in actual["districts"] if item["aun"] == "124151902")
    assert coatesville["levels"]["3200"]["amount"] == 30
    assert coatesville["levels"]["3200-100"]["amount"] == 10
    assert coatesville["levels"]["3200-110"]["amount"] == 10
    assert actual["nodes"]["3200-100"]["children"] == ["3200-110"]


def write_compare(
    root: Path,
    *,
    charter_on_parent: bool = False,
    parent_object: bool = False,
    extra_function: str | None = None,
    second_document: bool = False,
) -> None:
    rows = [
        # Parent 1100 sits beside its children and must not be added again.
        fact("124151902", "1100", "100", 1000),
        fact("124151902", "1110", "100", 400),
        fact("124151902", "1110", "562", 100),
        fact("124151902", "1210", "100", 50),
        fact("124151902", "1210", "562", 20),
        fact("124151902", "3200", "100", 50),
        fact("124151902", "3200", "510", 20),
        # A prior year does not stand in for this page.
        fact("124151902", "1110", "100", 99999, year=2023, document="afr-2023"),
        # Another fund is not the general fund.
        fact("124151902", "1110", "100", 88888, fund="20"),
        fact("124150503", "1110", "100", 80),
        fact("124150503", "3300", "100", 0),
        # Spending with no students is absence.
        fact("124152003", "1110", "100", 5000),
        # A blank amount is not a posted zero and does not fail the build.
        fact("124151902", "2110", "100", None),
    ]
    if charter_on_parent:
        rows.append(fact("124151902", "1100", "562", 25))
    if parent_object:
        rows.append(fact("124151902", "3200", "110", 10))
    if extra_function:
        rows.append(fact("124150503", extra_function, "100", 10))
    if second_document:
        rows.append(fact("124150503", "2110", "100", 5, document="afr-2024-b"))

    pd.DataFrame(rows).to_parquet(root / "afr_expenditure.parquet", index=False)
    pd.DataFrame([
        {"aun": "124151902", "school_year": 2024, "enrollment": 10, "document_id": "enrollment-2024"},
        {"aun": "124150503", "school_year": 2024, "enrollment": 4, "document_id": "enrollment-2024"},
        {"aun": "124156503", "school_year": 2024, "enrollment": 1977, "document_id": "enrollment-2024"},
        {"aun": "124152003", "school_year": 2024, "enrollment": 0, "document_id": "enrollment-2024"},
    ]).to_parquet(root / "enrollment.parquet", index=False)
    directory = [
        {"aun": aun, "lea_name": f"District {aun[-3:]}", "category": "school_district", "county": "Chester"}
        for aun in DISTRICTS
    ]
    directory.append({
        "aun": "124150003",
        "lea_name": "Avon Grove CS",
        "category": "charter_school",
        "county": "Chester",
    })
    directory.append({
        "aun": "124000000",
        "lea_name": "Chester County IU 24",
        "category": "intermediate_unit",
        "county": "Chester",
    })
    directory.append({
        "aun": "124151607",
        "lea_name": "Chester County Technical College HS",
        "category": "career_and_technical_center",
        "county": "Chester",
    })
    directory.append({
        "aun": "123000000",
        "lea_name": "Other County SD",
        "category": "school_district",
        "county": "Montgomery",
    })
    pd.DataFrame(directory).to_parquet(root / "lea.parquet", index=False)
    pd.DataFrame([
        {"function_code": "1100", "function_name": "REGULAR PROGRAMS – ELEMENTARY / SECONDARY", "object_code": None, "object_name": None},
        {"function_code": "1110", "function_name": "REGULAR PROGRAMS", "object_code": None, "object_name": None},
        {"function_code": "1200", "function_name": "SPECIAL PROGRAMS – ELEMENTARY / SECONDARY", "object_code": None, "object_name": None},
        {"function_code": "1210", "function_name": "SPECIAL PROGRAMS", "object_code": None, "object_name": None},
        {"function_code": "3200", "function_name": "STUDENT ACTIVITIES", "object_code": None, "object_name": None},
        {"function_code": "3300", "function_name": "COMMUNITY SERVICES", "object_code": None, "object_name": None},
        {"function_code": None, "function_name": None, "object_code": "100", "object_name": "PERSONNEL SERVICES – SALARIES"},
        {"function_code": None, "function_name": None, "object_code": "510", "object_name": "STUDENT TRANSPORTATION SERVICES"},
    ]).to_parquet(root / "account.parquet", index=False)
    pd.DataFrame([
        {"aun": "124151902", "school_year": 2024, "fund_code": "10", "function_code": "1110", "object_code": "100", "amount": 40, "document_id": "gfb-2024"},
        # A later budget with no October 1 count does not become the year.
        {"aun": "124151902", "school_year": 2025, "fund_code": "10", "function_code": "1110", "object_code": "100", "amount": 99999, "document_id": "gfb-2025"},
    ]).to_parquet(root / "gfb_expenditure.parquet", index=False)
    pd.DataFrame([
        {
            "aun": "124151902", "school_year": 2024, "fund_code": "10", "account_code": "6111",
            "rollup1_account_code": "6000", "rollup2_account_code": "6100", "rollup3_account_code": "6110",
            "amount": 80, "document_id": "afr-revenue-2024",
        },
        {
            "aun": "124151902", "school_year": 2024, "fund_code": "10", "account_code": "6100",
            "rollup1_account_code": "6000", "rollup2_account_code": None, "rollup3_account_code": None,
            "amount": 999, "document_id": "afr-revenue-2024",
        },
    ]).to_parquet(root / "afr_revenue.parquet", index=False)
    pd.DataFrame([
        {"account_code": "6111", "name": "CURRENT REAL ESTATE TAXES"},
        {"account_code": "6100", "name": "TAXES LEVIED"},
    ]).to_parquet(root / "revenue_account.parquet", index=False)
    pd.DataFrame([
        {"document_id": "afr-2024", "source_url": "https://example.test/afr-2024.xlsx"},
        {"document_id": "afr-2024-b", "source_url": "https://example.test/afr-2024-b.xlsx"},
        {"document_id": "afr-2023", "source_url": "https://example.test/afr-2023.xlsx"},
        {"document_id": "gfb-2024", "source_url": "https://example.test/gfb-2024.xlsx"},
        {"document_id": "gfb-2025", "source_url": "https://example.test/gfb-2025.xlsx"},
        {"document_id": "afr-revenue-2024", "source_url": "https://example.test/afr-revenue-2024.xlsx"},
        {"document_id": "enrollment-2024", "source_url": "https://example.test/enrollment-2024.xlsx"},
    ]).to_parquet(root / "document.parquet", index=False)


def fact(
    aun: str,
    function: str,
    obj: str,
    amount: float,
    *,
    year: int = 2024,
    fund: str = "10",
    document: str = "afr-2024",
) -> dict:
    return {
        "aun": aun,
        "school_year": year,
        "fund_code": fund,
        "function_code": function,
        "object_code": obj,
        "total_amount": amount,
        "document_id": document,
    }
