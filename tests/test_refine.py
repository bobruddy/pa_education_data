"""Parser and rebuild tests. They use tiny workbooks, not PDE."""

import json
from pathlib import Path

import duckdb
import pandas as pd
import pytest
from openpyxl import Workbook

from pa_edu.check import (
    GRAIN,
    _assessment_lea_frame,
    _assessment_school_cell,
    _assessment_school_lea,
    _grain,
)
from pa_edu.parse_act1 import base_from_text, parse_act1
from pa_edu.parse_charter_adm import parse_charter_adm
from pa_edu.parse_cohort_grad import parse_cohort_grad
from pa_edu.parse_homeschool import parse_homeschool
from pa_edu.parse_iep import parse_iep
from pa_edu.parse_low_income import parse_low_income
from pa_edu.parse_retax import parse_retax
from pa_edu.parse_assessment import parse_keystone, parse_keystone_school, parse_pssa, parse_pssa_school
from pa_edu.parse_chart import descriptions_from_text, titles_from_text
from pa_edu.parse_gfb import parse_gfb
from pa_edu.refine import run
from pa_edu.storage import load_index, store_bytes
from pa_edu.catalog import CatalogEntry


def _save(path: Path, sheets: dict[str, list[list]]) -> None:
    book = Workbook()
    first = True
    for name, rows in sheets.items():
        sheet = book.active if first else book.create_sheet(name)
        first = False
        sheet.title = name
        for row in rows:
            sheet.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    book.save(path)


def _gfb_book(path: Path, amount: int = 5) -> None:
    _save(
        path,
        {
            "Exp": [
                ["InstCat", "AUN", "InstName", "CountyName", "1100-100", "1100-200", "Notes", ""],
                [1, 101260303.0, "Albert Gallatin Area SD", "Fayette", amount, 0, "ignore", None],
                [2, 101000000, "Intermediate Unit 1", "Washington", 9, 1, None, None],
            ],
            "IUExp_Prog": [
                ["InstCat", "AUN", "InstName", "CountyName", "1100-100-1", "1100-100-2"],
                [2, 101000000, "Intermediate Unit 1", "Washington", 4, 5],
            ],
            "Rev_BegFB": [
                ["InstCat", "AUN", "InstName", "CountyName", "6111", "6112", "0810"],
                [1, 101260303.0, "Albert Gallatin Area SD", "Fayette", 12, 0, 99],
            ],
        },
    )


def _afr_book(path: Path) -> None:
    header = [
        "InstCat", "AUN", "InstName", "CountyName", "FundCode", "RollupFundCode",
        "AccountCode", "Rollup1AccountCode", "Rollup2AccountCode", "Rollup3AccountCode",
        "ObjectCode", "Rollup1ObjectCode", "Rollup2ObjectCode", "ProgramCode",
        "ElementaryAmount", "SecondaryAmount", "FederalAmount", "TotalAmount", "Extra",
    ]
    _save(
        path,
        {
            "EXP": [
                header,
                [1, 101260303, "Albert Gallatin Area SD", "Fayette", 10, None, 1110, 1000, 1100, None, 120, 100, None, None, 3, 2, 0, 5, None],
                [1, 101260303, "Albert Gallatin Area SD", "Fayette", 23, None, 1110, 1000, 1100, None, 120, 100, None, None, 0, 0, 7, 7, None],
            ],
            "SLFS_EXP_1": [
                ["SchoolName", "BranchNumber", *header],
                ["Albert", "1234", 1, 101260303, "Albert Gallatin Area SD", "Fayette", 10, None, 1110, 1000, 1100, None, 120, 100, None, None, 3, 2, 0, 5, None],
            ],
            "SLFS_EXP_2": [
                ["SchoolName", "BranchNumber", *header],
                ["Other", "9999", 1, 101260303, "Albert Gallatin Area SD", "Fayette", 23, None, 1110, 1000, 1100, None, 120, 100, None, None, 0, 0, 7, 7, None],
            ],
            "REV": [
                [
                    "InstCat", "AUN", "InstName", "CountyName", "FundCode", "RollupFundCode",
                    "AccountCode", "Rollup1AccountCode", "Rollup2AccountCode", "Rollup3AccountCode",
                    "ProgramCode", "Amount1", "Amount2", "Amount3", "TotalAmount",
                ],
                [1, 101260303, "Albert Gallatin Area SD", "Fayette", 10, None, 6111, 6000, 6100, 6110, None, 8, None, None, 8],
            ],
        },
    )


def _enrollment_book(path: Path) -> None:
    junk = ["title"]
    header = ["AUN", "LEA Name", "LEA Type", "County", "School Number", "School Name", "012", "EUG", "Total"]
    rows = [
        junk, junk, junk, junk, header,
        [101260303, "Albert Gallatin Area SD", "SD", "Fayette", 1234, "Elem", 10, 3, 13],
        [None, None, None, None, 9999, "Albert Gallatin Area SD", 2, 0, 2],
        [101260303, "Albert Gallatin Area SD Total", "SD", "Fayette", 9999, "Total", 12, 3, 15],
    ]
    gender_header = [*header[:6], "Student Gender Code", "012", "EUG", "Total"]
    gender_rows = [
        junk, junk, junk, junk, gender_header,
        [101260303, "Albert Gallatin Area SD", "SD", "Fayette", 1234, "Elem", "Female", 4, 1, 5],
        [101260303, "Albert Gallatin Area SD", "SD", "Fayette", 1234, "Elem", "Male", 6, 2, 8],
        [101260303, "Albert Gallatin Area SD", "SD", "Fayette", 9999, "Albert Gallatin Area SD", "Female", 2, 0, 2],
    ]
    race_header = ["AUN", "LEA Name", "LEA Type", "County", "Race", "012", "EUG", "Total"]
    race_rows = [
        junk, junk, junk, junk, race_header,
        [101260303, "Albert Gallatin Area SD", "SD", "Fayette", "White", 12, 3, 15],
    ]
    lea_rows = [
        junk, junk, junk, junk,
        ["AUN", "LEA Name", "LEA Type", "County", "012", "EUG", "Total"],
        [101260303, "Albert Gallatin Area SD", "SD", "Fayette", 12, 3, 15],
    ]
    _save(
        path,
        {
            "LEA and School": rows,
            "LEA, School and Gender": gender_rows,
            "LEA and Race": race_rows,
            "LEA": lea_rows,
        },
    )


def _catalog(path: Path, **rows: Path) -> None:
    lines = []
    for name, file in rows.items():
        status = "review" if name == "review" else "stable"
        parser = {"gfb": "gfb", "afr": "afr", "enrollment": "enrollment", "review": "gfb"}[name]
        year = {"gfb": 2019, "afr": 2024, "enrollment": 2024}.get(name)
        lines.append("[[document]]")
        lines.append(f'id = "{name}"')
        lines.append('source_id = "test"')
        lines.append(f'source_url = "{file.as_uri()}"')
        lines.append(f'page_url = "{file.as_uri()}"')
        lines.append(f'parser = "{parser}"')
        lines.append(f'status = "{status}"')
        if year is not None and name != "review":
            lines.append(f"school_year = {year}")
        lines.append("")
    path.write_text("\n".join(lines))


def test_gfb_keeps_zeros_and_splits_program(tmp_path: Path) -> None:
    book = tmp_path / "gfb.xlsx"
    _gfb_book(book)
    parsed = parse_gfb(book, {"school_year": 2019, "document_id": "gfb-test"})
    frame = parsed["gfb_expenditure"]
    assert set(frame["school_year"]) == {2019}
    district = frame.loc[frame["aun"] == "101260303"]
    assert set(zip(district["function_code"], district["object_code"], district["program_code"], district["amount"])) == {
        ("1100", "100", "", 5.0),
        ("1100", "200", "", 0.0),
    }
    unit = frame.loc[frame["aun"] == "101000000"]
    assert sorted(unit["program_code"]) == ["1", "2"]
    assert unit["amount"].sum() == 9
    assert "Notes" not in set(frame["function_code"])


def test_gfb_revenue_keeps_a_zero_and_skips_fund_balance(tmp_path: Path) -> None:
    book = tmp_path / "gfb.xlsx"
    _gfb_book(book)
    frame = parse_gfb(book, {"school_year": 2019, "document_id": "gfb-test"})["gfb_revenue"]
    assert set(frame["school_year"]) == {2019}
    assert set(frame["account_code"]) == {"6111", "6112"}
    district = frame.loc[frame["aun"] == "101260303"].set_index("account_code")
    assert district.loc["6111", "amount"] == 12
    assert district.loc["6112", "amount"] == 0
    assert set(frame["fund_code"]) == {"10"}
    assert set(frame["document_id"]) == {"gfb-test"}


def test_gfb_revenue_rejects_an_unknown_column(tmp_path: Path) -> None:
    book = tmp_path / "gfb.xlsx"
    _save(
        book,
        {
            "Exp": [
                ["InstCat", "AUN", "InstName", "CountyName", "1100-100"],
                [1, 101260303, "Albert Gallatin Area SD", "Fayette", 1],
            ],
            "Rev_BegFB": [
                ["InstCat", "AUN", "InstName", "CountyName", "6111", "Notes"],
                [1, 101260303, "Albert Gallatin Area SD", "Fayette", 1, 2],
            ],
        },
    )
    try:
        parse_gfb(book, {"school_year": 2019, "document_id": "gfb-test"})
    except ValueError as error:
        assert "Notes" in str(error)
    else:
        raise AssertionError("unknown revenue column was melted")


def test_afr_revenue_uses_the_filled_total_or_amount1(tmp_path: Path) -> None:
    from pa_edu.parse_afr import parse_afr

    book = tmp_path / "afr.xlsx"
    header = [
        "InstCat", "AUN", "InstName", "CountyName", "FundCode", "RollupFundCode",
        "AccountCode", "Rollup1AccountCode", "Rollup2AccountCode", "Rollup3AccountCode",
        "ProgramCode", "Amount1", "Amount2", "Amount3", "TotalAmount",
    ]
    _save(
        book,
        {
            "EXP": [[
                "InstCat", "AUN", "InstName", "CountyName", "FundCode", "RollupFundCode",
                "AccountCode", "Rollup1AccountCode", "Rollup2AccountCode", "Rollup3AccountCode",
                "ObjectCode", "Rollup1ObjectCode", "Rollup2ObjectCode", "ProgramCode",
                "ElementaryAmount", "SecondaryAmount", "FederalAmount", "TotalAmount",
            ]],
            "REV": [
                header,
                [1, 124150503.0, "Avon Grove SD", "Chester", 10, None, 6111, 6000, 6100, 6110, None, 12, 3, 1, 10],
                [1, 124150503.0, "Avon Grove SD", "Chester", 10, None, 6500, 6000, None, None, None, 5, None, None, None],
                [1, 124150503.0, "Avon Grove SD", "Chester", 10, None, 6120, 6000, None, None, None, 0, None, None, None],
                [1, 124150503.0, "Avon Grove SD", "Chester", 23, None, 6111, 6000, 6100, 6110, 9, 4, None, None, 4],
                [1, 124150503.0, "Avon Grove SD", "Chester", 10, None, 6990, 6000, None, None, None, None, None, None, None],
            ],
        },
    )
    frame = parse_afr(book, {"school_year": 2024, "document_id": "afr-test"})["afr_revenue"]
    assert set(frame["school_year"]) == {2024}
    assert frame["aun"].tolist() == ["124150503"] * 4
    tax = frame.loc[(frame["fund_code"] == "10") & (frame["account_code"] == "6111")].iloc[0]
    assert tax["amount"] == 10
    assert tax["amount"] != 12 + 10
    assert list(tax[["rollup1_account_code", "rollup2_account_code", "rollup3_account_code"]]) == ["6000", "6100", "6110"]
    earnings = frame.loc[frame["account_code"] == "6500"].iloc[0]
    assert earnings["amount"] == 5
    assert pd.isna(earnings["total_amount"])
    zero = frame.loc[frame["account_code"] == "6120"].iloc[0]
    assert zero["amount"] == 0
    other = frame.loc[frame["fund_code"] == "23"].iloc[0]
    assert other["program_code"] == "9"
    assert other["amount"] == 4
    assert "6990" not in set(frame["account_code"])


def test_enrollment_school_numbers_drop_leading_zeros(tmp_path: Path) -> None:
    book = tmp_path / "enrollment.xlsx"
    junk = ["title"]
    header = ["AUN", "LEA Name", "LEA Type", "County", "School Number", "School Name", "012", "Total"]
    gender_header = [*header[:6], "Student Gender Code", "012", "Total"]
    _save(
        book,
        {
            "LEA and School": [
                junk, junk, junk, junk, header,
                [101260303, "Albert Gallatin Area SD", "SD", "Fayette", 0, "Office", 5, 5],
                [101260303, "Albert Gallatin Area SD", "SD", "Fayette", 326, "Elem", 10, 10],
            ],
            "LEA, School and Gender": [
                junk, junk, junk, junk, gender_header,
                [101260303, "Albert Gallatin Area SD", "SD", "Fayette", "0000", "Office", "Female", 5, 5],
                [101260303, "Albert Gallatin Area SD", "SD", "Fayette", "0326", "Elem", "Male", 10, 10],
            ],
        },
    )
    from pa_edu.extract import ensure_extract, use_extract
    from pa_edu.parse_enrollment import parse_enrollment

    data = tmp_path / "data"
    index = load_index(data)
    entry = CatalogEntry(
        id="enrollment-2024",
        source_id="enrollment",
        source_url=book.as_uri(),
        page_url=book.as_uri(),
        parser="enrollment",
        status="stable",
        school_year=2024,
    )
    record = store_bytes(entry, book.read_bytes(), data, index, book.name)
    record = ensure_extract(data, index, record)
    document = {"school_year": 2024, "document_id": record["document_id"]}
    with use_extract(book, record["extract_path"]):
        parsed = parse_enrollment(book, document)
    assert set(parsed["enrollment"]["school_number"]) == {"0", "326"}
    assert set(parsed["enrollment_gender"]["school_number"]) == {"0", "326"}
    assert parsed["enrollment_gender"]["enrollment"].sum() == parsed["enrollment"]["enrollment"].sum()


def test_enrollment_grain_and_total_row(tmp_path: Path) -> None:
    book = tmp_path / "enrollment.xlsx"
    _enrollment_book(book)
    from pa_edu.parse_enrollment import parse_enrollment

    parsed = parse_enrollment(book, {"school_year": 2024, "document_id": "enrollment-test"})
    frame = parsed["enrollment"]
    assert "total" not in set(frame["grade_code"])
    assert set(frame["grade_code"]) == {"012", "eug"}
    schools = set(frame["school_number"])
    assert schools == {"1234", "9999"}
    assert frame.loc[frame["school_number"] == "9999", "enrollment"].sum() == 2
    gender = parsed["enrollment_gender"]
    assert set(gender["gender"]) == {"Female", "Male"}
    assert gender["enrollment"].sum() == frame["enrollment"].sum()
    assert parsed["enrollment_race"]["enrollment"].sum() == frame.groupby("grade_code")["enrollment"].sum().sum()


def test_race_omits_suppressed_cells_and_blank_twins(tmp_path: Path) -> None:
    book = tmp_path / "enrollment.xlsx"
    header = ["AUN", "LEA Name", "LEA Type", "County", "Race", "001", "012"]
    _save(
        book,
        {
            "LEA and School": [
                ["AUN", "LEA Name", "LEA Type", "County", "School Number", "School Name", "001", "012", "Total"],
                ["101260303", "Albert Gallatin Area SD", "SD", "Fayette", "1", "One", 5, 4, 9],
            ],
            "LEA and Race": [
                header,
                ["101260303", "Albert Gallatin Area SD", "SD", "Fayette", "White", "3^", 4],
                ["101260303", "Albert Gallatin Area SD", "SD", "Fayette", "White", 0, 0],
                ["101260303", "Albert Gallatin Area SD", "SD", "Fayette", "Asian", "*", 0],
            ],
        },
    )
    from pa_edu.parse_enrollment import parse_enrollment

    race = parse_enrollment(book, {"school_year": 2024, "document_id": "enrollment-test"})["enrollment_race"]
    white = race.loc[race["race"] == "White"].set_index("grade_code")["enrollment"]
    assert white.to_dict() == {"012": 4}
    assert race.loc[race["race"] == "Asian", "grade_code"].tolist() == ["012"]


def test_leaw_is_dropped_when_buildings_already_match_exp() -> None:
    from pa_edu.parse_afr import _drop_redundant_leaw

    keys = {
        "aun": "107657103",
        "school_year": 2024,
        "fund_code": "10",
        "function_code": "3300",
        "object_code": "640",
        "program_code": "",
        "elementary_amount": 0.0,
        "secondary_amount": 0.0,
        "federal_amount": 0.0,
        "document_id": "afr-test",
    }
    school = pd.DataFrame(
        [
            {**keys, "school_number": "4490", "school_name": "McCullough", "total_amount": 8.0},
            {**keys, "school_number": "LEAW", "school_name": None, "total_amount": 8.0},
        ]
    )
    expense = pd.DataFrame([{**keys, "total_amount": 8.0}])
    kept = _drop_redundant_leaw(school, expense)
    assert kept["school_number"].tolist() == ["4490"]


def test_chart_titles_stop_at_the_description() -> None:
    text = """
1000 INSTRUCTION
1110 * REGULAR PROGRAMS Use this account for instruction.
100 PERSONNEL SERVICES – SALARIES Gross salaries paid.
120 PROFESSIONAL – TEACHERS Gross salaries for teachers.
6000 REVENUE FROM LOCAL SOURCES
6111 Current Real Estate Taxes Revenue received.
"""
    functions, objects, revenue = titles_from_text(text)
    assert functions["1110"] == "REGULAR PROGRAMS"
    assert objects["120"] == "PROFESSIONAL – TEACHERS"
    assert "6111" not in objects
    assert "6111" not in functions
    assert revenue["6111"] == "Current Real Estate Taxes"
    assert revenue["6000"] == "REVENUE FROM LOCAL SOURCES"
    described = descriptions_from_text(text)
    assert described[0]["1110"] == "Use this account for instruction."
    assert described[1]["100"] == "Gross salaries paid."
    assert described[1]["120"] == "Gross salaries for teachers."
    assert described[2]["6111"] == "Revenue received."
    assert "1000" not in described[0]
    assert "6000" not in described[2]


def test_chart_descriptions_stay_with_their_heading() -> None:
    text = """
1000 INSTRUCTION
Instruction includes teaching.
1800 PRE-KINDERGARTEN
Activities designed to provide Pre-K students with learning experiences.
1801* Instruction
Include in this function costs for salaries and benefits.
Expenditure Function Codes: 2024-2025 FY E-3
1802* Pre-K Administrative Support
Include in this function costs for admin salaries.
2611 SUPERVISION OF PLANT – HEAD OF
Component
Activities associated with the director.
100 PERSONNEL SERVICES – SALARIES
Gross salaries paid to employees of the LEA. (Expenditures may be charged to the following sub-
accounts.)
120 PROFESSIONAL – TEACHERS
Gross salaries for teachers.
REVENUE FROM LOCAL SOURCES
6110 AD VALOREM TAXES
Taxes levied by an LEA on the assessed valuation.
6111 Current Real Estate Taxes
Revenue received from taxes assessed and levied upon real property.
"""
    functions, objects, revenue = descriptions_from_text(text)
    assert functions["1800"] == "Activities designed to provide Pre-K students with learning experiences."
    assert functions["1801"] == "Include in this function costs for salaries and benefits."
    assert "Expenditure Function Codes" not in functions["1802"]
    assert functions["1802"] == "Include in this function costs for admin salaries."
    assert functions["2611"] == "Activities associated with the director."
    assert objects["100"].endswith("sub-accounts.)")
    assert revenue["6110"] == "Taxes levied by an LEA on the assessed valuation."
    assert revenue["6111"] == "Revenue received from taxes assessed and levied upon real property."
    assert revenue["6110"] != revenue["6111"]


def test_chart_description_rejects_a_heading_in_the_wrong_section() -> None:
    text = """
1000 INSTRUCTION
Instruction includes teaching.
1110 REGULAR PROGRAMS
Use this account for regular programs.
100 SALARIES
Gross salaries paid.
"""
    try:
        descriptions_from_text(text)
    except RuntimeError as error:
        assert "no longer sits under the heading" in str(error)
        assert "100" in str(error)
    else:
        raise AssertionError("a salary heading inside the function section was accepted")


def test_chart_description_keeps_the_heading_beside_the_paragraph() -> None:
    from pa_edu.refine import _chart_description_frame

    frame = _chart_description_frame(
        {"object": {"571": "Food Service Management – Food Costs"}},
        {"object": {"571": "Expenditures for food costs paid to a food service management company."}},
    )
    row = frame.loc[frame["code"] == "571"].iloc[0]
    assert row["name"] == "Food Service Management – Food Costs"
    assert row["description"].startswith("Expenditures for food costs")


def test_review_is_downloaded_and_not_parsed(tmp_path: Path) -> None:
    raw = tmp_path / "files"
    gfb = raw / "gfb.xlsx"
    afr = raw / "afr.xlsx"
    enrollment = raw / "enrollment.xlsx"
    review = raw / "review.txt"
    _gfb_book(gfb)
    _afr_book(afr)
    _enrollment_book(enrollment)
    review.write_text("not a workbook")
    catalog = tmp_path / "catalog.toml"
    _catalog(catalog, gfb=gfb, afr=afr, enrollment=enrollment, review=review)
    data = tmp_path / "data"
    run(data, catalog)
    calls = {"count": 0}
    import pa_edu.storage as storage

    original = storage.fetch

    def boom(entry):
        calls["count"] += 1
        raise AssertionError("second refine fetched")

    storage.fetch = boom
    try:
        run(data, catalog)
    finally:
        storage.fetch = original
    assert calls["count"] == 0
    index = load_index(data)
    assert index["current"]["review"].startswith("review-")
    expenses = pd.read_parquet(data / "refined" / "gfb_expenditure.parquet")
    assert set(expenses["school_year"]) == {2019}
    general = duckdb.connect(str(data / "pde.duckdb")).execute(
        "SELECT sum(total_amount) FROM afr_general_fund"
    ).fetchone()[0]
    assert general == 5
    cited = duckdb.connect(str(data / "pde.duckdb")).execute(
        """
        SELECT source_url FROM afr_expenditure
        JOIN document USING (document_id)
        LIMIT 1
        """
    ).fetchone()[0]
    assert cited == afr.as_uri()


def _finance_catalog(tmp_path: Path, amount: int = 5) -> tuple[Path, Path, Path]:
    raw = tmp_path / "files"
    gfb = raw / "gfb.xlsx"
    afr = raw / "afr.xlsx"
    enrollment = raw / "enrollment.xlsx"
    _gfb_book(gfb, amount)
    _afr_book(afr)
    _enrollment_book(enrollment)
    catalog = tmp_path / "catalog.toml"
    _catalog(catalog, gfb=gfb, afr=afr, enrollment=enrollment)
    return tmp_path / "data", catalog, gfb


def _corrupt_cached(data: Path, keep: set[str] | None = None) -> None:
    kept = keep or set()
    for record in load_index(data)["documents"].values():
        if record["catalog_id"] in kept:
            continue
        Path(record["path"]).write_bytes(b"not a workbook")


def _district_gfb(data: Path) -> float:
    expenses = pd.read_parquet(data / "refined" / "gfb_expenditure.parquet")
    district = expenses.loc[expenses["aun"] == "101260303"]
    assert district["aun"].tolist()
    assert all(isinstance(value, str) for value in district["aun"])
    return float(district["amount"].sum())


def test_unchanged_refine_keeps_tables_without_rereading(tmp_path: Path, capsys) -> None:
    data, catalog, _gfb = _finance_catalog(tmp_path)
    run(data, catalog)
    capsys.readouterr()
    _corrupt_cached(data)
    run(data, catalog)
    assert "kept refined tables" in capsys.readouterr().out
    assert _district_gfb(data) == 5


def test_reparse_uses_the_extract_when_the_workbook_is_unreadable(tmp_path: Path, monkeypatch) -> None:
    data, catalog, _gfb = _finance_catalog(tmp_path)
    run(data, catalog)
    metas = list((data / "refined" / "_parts").glob("gfb-*/meta.json"))
    meta = json.loads(metas[0].read_text())
    meta["fingerprint"] = "stale"
    metas[0].write_text(json.dumps(meta))
    stamp_path = data / "refined" / "_inputs.json"
    stamp = json.loads(stamp_path.read_text())
    for row in stamp["parsed"]:
        if row["catalog_id"] == "gfb":
            row["fingerprint"] = "stale"
    stamp_path.write_text(json.dumps(stamp))
    _corrupt_cached(data)

    def refuse(path, *args, **kwargs):
        raise AssertionError(f"opened {path}")

    monkeypatch.setattr("pa_edu.extract.read_workbook", refuse)
    monkeypatch.setattr(pd, "read_excel", refuse)
    run(data, catalog)
    assert _district_gfb(data) == 5


def test_a_new_stable_year_is_appended(tmp_path: Path, monkeypatch) -> None:
    data, catalog, _gfb = _finance_catalog(tmp_path)
    run(data, catalog)
    extra = tmp_path / "files" / "gfb-2020.xlsx"
    _gfb_book(extra, amount=3)
    text = catalog.read_text()
    text += "\n".join(
        [
            "[[document]]",
            'id = "gfb-2020"',
            'source_id = "test"',
            f'source_url = "{extra.as_uri()}"',
            f'page_url = "{extra.as_uri()}"',
            'parser = "gfb"',
            'status = "stable"',
            "school_year = 2020",
            "",
        ]
    )
    catalog.write_text(text)
    opened: list[str] = []
    import pa_edu.extract as extract

    original = extract.read_workbook

    def counting(path: Path):
        opened.append(Path(path).name)
        return original(path)

    monkeypatch.setattr(extract, "read_workbook", counting)
    run(data, catalog)
    assert opened == [extra.name]
    expenses = pd.read_parquet(data / "refined" / "gfb_expenditure.parquet")
    district = expenses.loc[expenses["aun"] == "101260303"]
    totals = district.groupby("school_year")["amount"].sum().to_dict()
    assert totals[2019] == 5
    assert totals[2020] == 3


def test_stale_parser_fingerprint_reparses_that_document_only(tmp_path: Path) -> None:
    data, catalog, _gfb = _finance_catalog(tmp_path)
    run(data, catalog)
    metas = list((data / "refined" / "_parts").glob("gfb-*/meta.json"))
    assert len(metas) == 1
    meta = json.loads(metas[0].read_text())
    meta["fingerprint"] = "stale"
    metas[0].write_text(json.dumps(meta))
    stamp_path = data / "refined" / "_inputs.json"
    stamp = json.loads(stamp_path.read_text())
    for row in stamp["parsed"]:
        if row["catalog_id"] == "gfb":
            row["fingerprint"] = "stale"
    stamp_path.write_text(json.dumps(stamp))
    _corrupt_cached(data, keep={"gfb"})
    run(data, catalog)
    restored = json.loads(metas[0].read_text())
    assert restored["fingerprint"] != "stale"
    assert _district_gfb(data) == 5
    actual = pd.read_parquet(data / "refined" / "afr_expenditure.parquet")
    assert float(actual.loc[actual["fund_code"].astype(str) == "10", "total_amount"].sum()) == 5


def test_a_new_hash_reparses_only_that_document(tmp_path: Path) -> None:
    data, catalog, gfb = _finance_catalog(tmp_path)
    run(data, catalog)
    for record in load_index(data)["documents"].values():
        path = Path(record["path"])
        if record["catalog_id"] == "gfb":
            path.unlink()
        else:
            path.write_bytes(b"not a workbook")
    _gfb_book(gfb, amount=7)
    run(data, catalog)
    assert _district_gfb(data) == 7
    actual = pd.read_parquet(data / "refined" / "afr_expenditure.parquet")
    assert float(actual.loc[actual["fund_code"].astype(str) == "10", "total_amount"].sum()) == 5


def test_a_bad_workbook_names_the_catalog_entry(tmp_path: Path) -> None:
    raw = tmp_path / "files"
    bad = raw / "bad.xlsx"
    afr = raw / "afr.xlsx"
    _afr_book(afr)
    bad.write_bytes(b"not a workbook")
    catalog = tmp_path / "catalog.toml"
    catalog.write_text(
        "\n".join(
            [
                "[[document]]",
                'id = "gfb"',
                'source_id = "test"',
                f'source_url = "{bad.as_uri()}"',
                f'page_url = "{bad.as_uri()}"',
                'parser = "gfb"',
                'status = "stable"',
                "school_year = 2019",
                "",
                "[[document]]",
                'id = "afr"',
                'source_id = "test"',
                f'source_url = "{afr.as_uri()}"',
                f'page_url = "{afr.as_uri()}"',
                'parser = "afr"',
                'status = "stable"',
                "school_year = 2024",
                "",
            ]
        )
    )
    with pytest.raises(RuntimeError, match="gfb failed"):
        run(tmp_path / "data", catalog)


def test_a_second_hash_keeps_the_first_file(tmp_path: Path) -> None:
    entry = CatalogEntry(
        id="gfb-2019",
        source_id="gfb",
        source_url="https://example.test/gfb.xlsx",
        page_url="https://example.test/",
        parser="gfb",
        status="stable",
        school_year=2019,
    )
    data = tmp_path / "data"
    index = load_index(data)
    first = store_bytes(entry, b"one", data, index, "gfb.xlsx")
    second = store_bytes(entry, b"two", data, index, "gfb.xlsx")
    assert first["sha256"] != second["sha256"]
    assert Path(first["path"]).read_bytes() == b"one"
    assert Path(second["path"]).read_bytes() == b"two"
    assert load_index(data)["current"]["gfb-2019"] == second["document_id"]


def test_duplicate_school_account_fails_the_grain_check() -> None:
    keys = GRAIN["afr_expenditure_school"]
    row = {key: "1" for key in keys}
    row["school_year"] = 2024
    frame = pd.DataFrame([row, row])
    tables = {name: pd.DataFrame(columns=columns) for name, columns in GRAIN.items()}
    tables["afr_expenditure_school"] = frame
    errors = _grain(tables)
    assert any("afr_expenditure_school" in error for error in errors)


def _assessment_book(path: Path, *, year: int = 2025, sheet: str = "PSSA") -> None:
    header = [
        "Year", "AUN", "County", "District Name", "Subject", "Group", "Grade",
        "Number Scored", "Percent Advanced", "Percent Proficient", "Percent Basic",
        "Percent Below Basic", "Percent Proficient and above",
    ]
    _save(
        path,
        {
            sheet: [
                ["title"],
                ["notes"],
                header,
                [year, 124150503, "CHESTER", "Avon Grove SD", "English Language Arts", "All Students", 3, 357, 10.0, 35.9, 30.0, 24.1, 45.9],
                [year, 124150503, "CHESTER", "Avon Grove SD", "Math", "All Students", "District Total", 2184, 15.0, 39.9, 25.0, 20.1, 54.9],
                [year, 124150503, "CHESTER", "Avon Grove SD", "Math", "IEP", 3, 10, "IS", "IS", "IS", "IS", "IS"],
            ]
        },
    )


def test_pssa_district_parser_normalizes_codes(tmp_path: Path) -> None:
    path = tmp_path / "pssa.xlsx"
    _assessment_book(path)
    frame = parse_pssa(path, {"school_year": 2024, "document_id": "pssa-test"})["assessment_result"]
    assert list(frame["subject"]) == ["ela", "math", "math"]
    assert list(frame["grade"]) == ["003", "total", "003"]
    row = frame.loc[(frame["subject"] == "ela") & (frame["grade"] == "003")].iloc[0]
    assert row["aun"] == "124150503"
    assert row["pct_proficient_and_above"] == 45.9
    assert row["county"] == "Chester"
    suppressed = frame.loc[frame["student_group"] == "IEP"].iloc[0]
    assert pd.isna(suppressed["pct_proficient_and_above"])


def test_act1_index_keeps_decimal_rates_and_skips_blanks(tmp_path: Path) -> None:
    path = tmp_path / "act1.xlsx"
    _save(
        path,
        {
            "SD Adj Index": [
                ["AUN", "School District", "County", "2024-25", "2023-24"],
                [101260303.0, "Albert Gallatin Area SD", "Fayette", 0.078, 0.06],
                [126515001, "Philadelphia City SD", "Philadelphia", None, None],
            ],
        },
    )
    frame = parse_act1(path, {"document_id": "act1-test"})["act1_index"]
    assert set(frame["aun"]) == {"101260303"}
    gallatin = frame.loc[frame["school_year"] == 2024].iloc[0]
    assert gallatin["aun"] == "101260303"
    assert gallatin["adjusted_index"] == 0.078
    assert gallatin["lea_name"] == "Albert Gallatin Area SD"
    assert gallatin["document_id"] == "act1-test"
    assert set(frame["school_year"]) == {2024, 2023}


def test_retax_keeps_split_rates_and_skips_a_blank(tmp_path: Path) -> None:
    path = tmp_path / "retax.xlsx"
    _save(
        path,
        {
            "Rates": [
                [
                    "AUN", "School District", "Tax County", "Municipality / Other Info",
                    "FY 2025-26\nCY 2026\nReal Estate Mills",
                    "FY 2025-26 Additional Community College Mills",
                ],
                [124150503.0, "Avon Grove SD", "Chester", None, 36, None],
                [103021903, "Clairton City SD", "Allegheny", "Land", 105.7527, None],
                [103021903, "Clairton City SD", "Allegheny", "Buildings", 10, None],
                [102027451, "Pittsburgh SD", "Allegheny", "2026 Calendar Year", 10.25, None],
                [125238402, "Southeast Delco SD", "Delaware", None, 32.5341, 0.2059],
            ],
        },
    )
    frame = parse_retax(path, {"school_year": 2025, "document_id": "retax-test"})["real_estate_tax"]
    pitt = frame.loc[frame["aun"] == "102027451"].iloc[0]
    assert pitt["mills"] == 10.25
    assert pitt["locality"] == ""
    avon = frame.loc[frame["aun"] == "124150503"].iloc[0]
    assert avon["mills"] == 36
    assert avon["locality"] == ""
    assert avon["county"] == "Chester"
    assert int(avon["school_year"]) == 2025
    assert set(frame.loc[frame["aun"] == "103021903", "locality"]) == {"Land", "Buildings"}
    assert frame.loc[frame["aun"] == "125238402", "college_mills"].iloc[0] == 0.2059


def test_act1_base_reads_the_history_line() -> None:
    frame = base_from_text(
        "Use for school year: 2027-2028 2026-2027\n"
        "Statewide Average Weekly Wage $1,373.17 $1,328.63\n"
        "Employment Cost Index 173.492 167.325\n"
        "Percent (%) Increase  -  SAWW 3.4% 3.4%\n"
        "Percent (%) Increase  -  ECI 3.7% 3.5%\n"
        "Base index: 3.6% 3.5%\n"
    )
    assert list(frame["school_year"]) == [2027, 2026]
    assert list(frame["base_index"]) == [0.036, 0.035]
    assert list(frame["saww_increase"]) == [0.034, 0.034]
    assert list(frame["eci_increase"]) == [0.037, 0.035]


def test_pssa_school_keeps_growth_and_does_not_invent_a_combined_percent(tmp_path: Path) -> None:
    path = tmp_path / "school.xlsx"
    _save(
        path,
        {
            "PSSA data (2)": [
                ["The 2015 PSSA School Level results"],
                ["notes"],
                [
                    "Year", "AUN", "School Number", "District", "School", "Subject", "Group", "Grade",
                    "Number Scored", "% Advanced", "% Proficient", "% Basic", "% Below Basic", "Growth**",
                ],
                [2015, 124150002.0, "000007691", "21ST CENTURY CYBER CS", "21ST CENTURY CYBER CS", "English Language Arts", "All Students", "School Total", 188, 7.4, 46.8, 38.8, 6.9, 57.75],
                [2015, 124150002, "000007691", "21ST CENTURY CYBER CS", "21ST CENTURY CYBER CS", "English Language Arts", "All Students", 6, 45, 13.3, 35.6, 42.2, 8.9, None],
                [2015, 124150002, "000007691", "21ST CENTURY CYBER CS", "21ST CENTURY CYBER CS", "Science", "All Students", 8, 3, None, None, None, None, None],
            ],
        },
    )
    frame = parse_pssa_school(path, {"school_year": 2014, "document_id": "pssa-school-test"})["assessment_result_school"]
    assert list(frame["grade"]) == ["total", "006", "008"]
    assert set(frame["subject"]) == {"ela", "science"}
    total = frame.loc[frame["grade"] == "total"].iloc[0]
    assert total["aun"] == "124150002"
    assert total["school_number"] == "7691"
    assert total["school_name"] == "21ST CENTURY CYBER CS"
    assert total["pct_advanced"] == 7.4
    assert total["growth"] == 57.75
    assert pd.isna(total["pct_proficient_and_above"])
    assert pd.isna(total["county"])
    assert total["assessment"] == "pssa"
    assert total["document_id"] == "pssa-school-test"
    grade = frame.loc[frame["grade"] == "006"].iloc[0]
    assert pd.isna(grade["growth"])
    suppressed = frame.loc[frame["subject"] == "science"].iloc[0]
    assert suppressed["number_scored"] == 3
    assert pd.isna(suppressed["pct_advanced"])


def test_pssa_school_reads_total_without_a_year_column(tmp_path: Path) -> None:
    path = tmp_path / "school.xlsx"
    _save(
        path,
        {
            "PSSA website": [
                ["2019 PSSA"],
                [
                    "AUN", "School Number", "County", "District Name", "School Name", "Subject", "Group", "Grade",
                    "Number Scored", "Percent Advanced", "Percent Proficient", "Percent Basic", "Percent Below Basic",
                ],
                [112011103, "000007302", "ADAMS", "BERMUDIAN SPRINGS SD", "BERMUDIAN SPRINGS EL SCH", "Math", "All Students", "Total", 263, 15.6, 45.6, 27.4, 11.4],
            ],
        },
    )
    frame = parse_pssa_school(path, {"school_year": 2018, "document_id": "pssa-school-2018"})["assessment_result_school"]
    row = frame.iloc[0]
    assert int(row["school_year"]) == 2018
    assert row["school_number"] == "7302"
    assert row["grade"] == "total"
    assert row["county"] == "Adams"
    assert row["subject"] == "math"
    assert pd.isna(row["pct_proficient_and_above"])
    assert pd.isna(row["growth"])


def test_pssa_school_keeps_the_published_combined_percent(tmp_path: Path) -> None:
    path = tmp_path / "school.xlsx"
    _save(
        path,
        {
            "Sheet1": [
                ["2025 PSSA"],
                [
                    "Year", "AUN", "School Number", "County", "District Name", "School Name", "Subject", "Group", "Grade",
                    "Number Scored", "Percent Advanced", "Percent Proficient", "Percent Basic", "Percent Below Basic",
                    "Percent Proficient and above",
                ],
                [2025, 112011103, "000007302", "ADAMS", "BERMUDIAN SPRINGS SD", "BERMUDIAN SPRINGS EL SCH", "English Language Arts", "All Students", 3, 106, 10.0, 20.0, 27.4, 30.2, 45.9, None, "x"],
            ],
        },
    )
    row = parse_pssa_school(path, {"school_year": 2024, "document_id": "pssa-school-2024"})["assessment_result_school"].iloc[0]
    assert row["grade"] == "003"
    assert row["pct_proficient_and_above"] == 45.9
    assert pd.isna(row["growth"])


def test_pssa_school_rejects_an_unknown_header(tmp_path: Path) -> None:
    path = tmp_path / "school.xlsx"
    _save(
        path,
        {
            "web": [
                [
                    "AUN", "School Number", "County", "District Name", "School Name", "Subject", "Group", "Grade",
                    "Number Scored", "Difference in Number Scored From 2019", "Percent Advanced", "Percent Proficient",
                    "Percent Basic", "Percent Below Basic",
                ],
                [112011103, "000007302", "Adams", "BERMUDIAN SPRINGS SD", "BERMUDIAN SPRINGS EL SCH", "Math", "All Students", "Total", 10, -4, 1, 2, 3, 4],
            ],
        },
    )
    with pytest.raises(ValueError, match="unknown columns"):
        parse_pssa_school(path, {"school_year": 2020, "document_id": "pssa-school-2020"})


def test_pssa_school_rejects_two_data_sheets(tmp_path: Path) -> None:
    header = ["AUN", "School Number", "District", "School", "Subject", "Group", "Grade", "Number Scored", "% Advanced", "% Proficient", "% Basic", "% Below Basic"]
    row = [124150002, "000007691", "Charter", "Charter", "Math", "All Students", "Total", 10, 1, 2, 3, 4]
    path = tmp_path / "school.xlsx"
    _save(path, {"PSSA": [header, row], "Sheet1": [header, row]})
    with pytest.raises(ValueError, match="school sheets"):
        parse_pssa_school(path, {"school_year": 2014, "document_id": "pssa-school"})


def test_pssa_school_cell_round_trips_from_the_workbook(tmp_path: Path) -> None:
    path = tmp_path / "school.xlsx"
    _save(
        path,
        {
            "PSSA data (2)": [
                ["title"],
                [
                    "Year", "AUN", "School Number", "District", "School", "Subject", "Group", "Grade",
                    "Number Scored", "% Advanced", "% Proficient", "% Basic", "% Below Basic", "Growth**",
                ],
                [2015, 124150002, "000007691", "21ST CENTURY CYBER CS", "21ST CENTURY CYBER CS", "English Language Arts", "All Students", "School Total", 188, 7.4, 46.8, 38.8, 6.9, 57.75],
            ],
        },
    )
    index = {
        "current": {"pssa-school-2014": "doc-1"},
        "documents": {
            "doc-1": {
                "parser": "pssa_school",
                "status": "stable",
                "school_year": 2014,
                "path": str(path),
                "catalog_id": "pssa-school-2014",
            }
        },
    }
    cell = {
        "school_year": 2014,
        "aun": "124150002",
        "school_number": "7691",
        "subject": "ela",
        "grade": "total",
        "student_group": "All Students",
    }
    tables = {
        "assessment_result_school": pd.DataFrame([{
            "aun": "124150002",
            "school_number": "7691",
            "school_year": 2014,
            "assessment": "pssa",
            "subject": "ela",
            "grade": "total",
            "student_group": "All Students",
            "number_scored": 188,
            "pct_advanced": 7.4,
            "pct_proficient": 46.8,
            "pct_basic": 38.8,
            "pct_below_basic": 6.9,
            "pct_proficient_and_above": None,
            "growth": 57.75,
        }])
    }
    assert _assessment_school_cell(tables, index, cell) == []
    tables["assessment_result_school"].loc[0, "growth"] = 1
    assert _assessment_school_cell(tables, index, cell)


def test_two_school_non_district_fails_and_is_not_an_lea_row() -> None:
    district = _assessment_row("112011103", 10.0, "district-doc")
    school = pd.concat(
        [
            _school_row("112011103", "0001", "Elem", 99.0, "school-doc"),
            _school_row("124150002", "000007691", "21st Century Cyber CS", 40.0, "school-doc"),
            _school_row("123456789", "0001", "One", 1.0, "school-doc"),
            _school_row("123456789", "0002", "Two", 2.0, "school-doc"),
        ],
        ignore_index=True,
    )
    lea = pd.DataFrame([
        {"aun": "112011103", "category": "school_district"},
        {"aun": "124150002", "category": "charter_school"},
        {"aun": "123456789", "category": "charter_school"},
    ])
    tables = {
        "assessment_result": pd.DataFrame([district]),
        "assessment_result_school": school,
        "lea": lea,
    }
    errors = _assessment_school_lea(tables)
    assert any("123456789" in error and "2 schools" in error for error in errors)
    assert not any("has an LEA row" in error for error in errors)
    assert not any("assessment_lea school" in error or "assessment_lea district" in error for error in errors)


def _assessment_row(aun: str, proficient: float, document_id: str, assessment: str = "pssa") -> dict:
    return {
        "aun": aun,
        "school_year": 2024,
        "assessment": assessment,
        "subject": "ela",
        "grade": "total",
        "student_group": "All Students",
        "number_scored": 10,
        "pct_advanced": 1.0,
        "pct_proficient": 2.0,
        "pct_basic": 3.0,
        "pct_below_basic": 4.0,
        "pct_proficient_and_above": proficient,
        "lea_name": "District",
        "county": "Adams",
        "document_id": document_id,
    }


def _school_row(
    aun: str,
    school_number: str,
    school_name: str,
    proficient: float,
    document_id: str,
    assessment: str = "pssa",
) -> pd.DataFrame:
    return pd.DataFrame([{
        **_assessment_row(aun, proficient, document_id, assessment),
        "school_number": school_number,
        "school_name": school_name,
        "growth": 5.0,
    }])


def test_keystone_two_school_lea_is_left_out() -> None:
    district = pd.DataFrame([
        _assessment_row("112011103", 10.0, "district-doc", "pssa"),
        _assessment_row("112011103", 20.0, "district-key", "keystone"),
    ])
    school = pd.concat(
        [
            _school_row("124150002", "7727", "City CHS", 40.0, "pssa-school", "pssa"),
            _school_row("124150002", "7727", "City CHS", 22.8, "key-school", "keystone"),
            _school_row("114060557", "6304", "Berks CTC East", 1.0, "key-school", "keystone"),
            _school_row("114060557", "7068", "Berks CTC West", 2.0, "key-school", "keystone"),
        ],
        ignore_index=True,
    )
    lea = pd.DataFrame([
        {"aun": "112011103", "category": "school_district"},
        {"aun": "124150002", "category": "charter_school"},
        {"aun": "114060557", "category": "career_and_technical_center"},
    ])
    errors = _assessment_school_lea({
        "assessment_result": district,
        "assessment_result_school": school,
        "lea": lea,
    })
    assert errors == []


def test_keystone_school_lea_matches_the_view_sum_when_the_cell_is_null() -> None:
    building = _school_row("112011103", "1367", "Avon Grove HS", None, "key-school", "keystone")
    building["pct_advanced"] = 4.1
    building["pct_proficient"] = 56.4
    charter = _school_row("102020001", "7727", "City CHS", None, "key-school", "keystone")
    charter["pct_advanced"] = 10.0
    charter["pct_proficient"] = 30.0
    published = _school_row("115210001", "8001", "One Campus", 16.0, "key-school", "keystone")
    partial = _school_row("124150002", "7691", "Cyber", None, "key-school", "keystone")
    partial["pct_proficient"] = None
    pssa = _school_row("126000002", "3", "Early", None, "pssa-school", "pssa")
    pssa["pct_advanced"] = 10.4
    pssa["pct_proficient"] = 25.9
    school = pd.concat(
        [building, charter, published, partial, pssa],
        ignore_index=True,
    )
    lea = pd.DataFrame([
        {"aun": "112011103", "category": "school_district"},
        {"aun": "102020001", "category": "charter_school"},
        {"aun": "115210001", "category": "career_and_technical_center"},
        {"aun": "124150002", "category": "charter_school"},
        {"aun": "126000002", "category": "charter_school"},
    ])
    tables = {
        "assessment_result": pd.DataFrame([
            _assessment_row("112011103", 20.0, "district-key", "keystone"),
        ]),
        "assessment_result_school": school,
        "lea": lea,
    }
    view, school_view = _assessment_lea_frame(tables)

    def proficient(frame: pd.DataFrame, aun: str):
        value = frame.loc[frame["aun"].astype(str) == aun, "pct_proficient_and_above"].iloc[0]
        return None if pd.isna(value) else value

    assert proficient(school_view, "112011103") == 60.5
    assert proficient(view, "112011103") == 20.0
    assert proficient(view, "102020001") == 40.0
    assert proficient(view, "115210001") == 16.0
    assert proficient(school_view, "126000002") == 36.3
    assert proficient(view, "124150002") is None
    assert proficient(view, "126000002") == 36.3
    assert _assessment_school_lea(tables) == []


def test_keystone_school_keeps_grade_11_and_does_not_invent_a_combined_percent(tmp_path: Path) -> None:
    path = tmp_path / "school.xlsx"
    _save(
        path,
        {
            "data": [
                ["2016 Keystone Exams School Level Data"],
                ["notes"],
                [
                    "Year", "AUN", "School Number", "County", "District", "School", "Subject", "Group", "Grade",
                    "Number Scored", "Percent Advanced", "Percent Proficient", "Percent Basic", "Percent Below Basic",
                ],
                [2016, 102020001.0, "000007727", "ADAMS", "CITY CHS", "CITY CHS", "Algebra I", "All Students", 11, 133, 23.3, 49.6, 21.8, 5.3],
                [2016, 102020001, "000007727", "ADAMS", "CITY CHS", "CITY CHS", "Biology", "All Students", 11, 10, "IS", "IS", "IS", "IS"],
            ],
        },
    )
    frame = parse_keystone_school(path, {"school_year": 2015, "document_id": "key-school"})["assessment_result_school"]
    assert list(frame["grade"]) == ["011", "011"]
    assert list(frame["subject"]) == ["algebra_i", "biology"]
    row = frame.iloc[0]
    assert row["aun"] == "102020001"
    assert row["school_number"] == "7727"
    assert row["school_name"] == "CITY CHS"
    assert row["lea_name"] == "CITY CHS"
    assert row["county"] == "Adams"
    assert row["pct_advanced"] == 23.3
    assert row["pct_proficient"] == 49.6
    assert pd.isna(row["pct_proficient_and_above"])
    assert pd.isna(row["growth"])
    assert row["assessment"] == "keystone"
    assert int(row["school_year"]) == 2015
    assert row["document_id"] == "key-school"
    suppressed = frame.iloc[1]
    assert suppressed["number_scored"] == 10
    assert pd.isna(suppressed["pct_advanced"])


def test_keystone_school_reads_a_grade_first_sheet_without_a_year_column(tmp_path: Path) -> None:
    path = tmp_path / "school.xlsx"
    _save(
        path,
        {
            "Sheet1": [
                ["2019 Keystone"],
                [
                    "Grade", "AUN", "School Number", "County", "District Name", "School Name", "Subject", "Group",
                    "Number Scored", "Percent Advanced", "Percent Proficient", "Percent Basic", "Percent Below Basic",
                ],
                [11, 124150503, "000001367", "CHESTER", "AVON GROVE SD", "AVON GROVE HS", "Literature", "All Students", 400, 10.0, 20.0, 30.0, 40.0],
            ],
        },
    )
    row = parse_keystone_school(path, {"school_year": 2018, "document_id": "key-2018"})["assessment_result_school"].iloc[0]
    assert int(row["school_year"]) == 2018
    assert row["grade"] == "011"
    assert row["school_number"] == "1367"
    assert row["subject"] == "literature"
    assert pd.isna(row["pct_proficient_and_above"])
    assert pd.isna(row["growth"])


def test_keystone_school_keeps_the_published_combined_percent(tmp_path: Path) -> None:
    path = tmp_path / "school.xlsx"
    _save(
        path,
        {
            "Sheet1": [
                ["2023 Keystone"],
                [
                    "Year", "AUN", "School Number", "County", "District Name", "School Name", "Subject", "Group", "Grade",
                    "Number Scored", "Percent Advanced", "Percent Proficient", "Percent Basic", "Percent Below Basic",
                    "% Advanced/Proficient",
                ],
                [2023, 102020001, "7727", "Adams", "CITY CHS", "CITY CHS", "Algebra I", "All Students", 11, 81, 1.2, 14.8, 58.0, 25.9, 16.0],
            ],
        },
    )
    row = parse_keystone_school(path, {"school_year": 2022, "document_id": "key-2022"})["assessment_result_school"].iloc[0]
    assert row["pct_advanced"] == 1.2
    assert row["pct_proficient"] == 14.8
    assert row["pct_proficient_and_above"] == 16.0
    assert pd.isna(row["growth"])

    later = tmp_path / "later.xlsx"
    _save(
        later,
        {
            "Keystone": [
                ["2025 Keystone"],
                [
                    "Year", "AUN", "School Number", "County", "District Name", "School Name", "Subject", "Grade", "Group",
                    "Number Scored", "Percent Advanced", "Percent Proficient", "Percent Basic", "Percent Below Basic",
                    "Percent Proficient and above",
                ],
                [2025, 124150503, "000001367", "CHESTER", "AVON GROVE SD", "AVON GROVE HS", "Algebra I", 11, "All Students", 410, 35.6, 29.3, 29.5, 5.6, 64.9],
            ],
        },
    )
    building = parse_keystone_school(later, {"school_year": 2024, "document_id": "key-2024"})["assessment_result_school"].iloc[0]
    assert building["school_number"] == "1367"
    assert building["grade"] == "011"
    assert building["pct_proficient_and_above"] == 64.9
    assert building["assessment"] == "keystone"


def test_keystone_school_rejects_an_unknown_header(tmp_path: Path) -> None:
    path = tmp_path / "school.xlsx"
    _save(
        path,
        {
            "Sheet1": [
                [
                    "AUN", "School Number", "County", "District Name", "School Name", "Subject", "Group", "Grade",
                    "Number Scored", "Difference in Number Scored From 2019", "Percent Reduction From 2019",
                    "Percent Advanced", "Percent Proficient", "Percent Basic", "Percent Below Basic",
                ],
                [102020001, "7727", "Adams", "CITY CHS", "CITY CHS", "Algebra I", "All Students", 11, 10, -4, 0.1, 1, 2, 3, 4],
            ],
        },
    )
    with pytest.raises(ValueError, match="unknown columns"):
        parse_keystone_school(path, {"school_year": 2020, "document_id": "key-2020"})


def test_keystone_school_does_not_parse_the_2015_layout(tmp_path: Path) -> None:
    path = tmp_path / "school.xlsx"
    _save(
        path,
        {
            "School_AssessmentProficiencyWit": [
                ["2014 - 2015 School Accountability Assessment Results"],
                [
                    "Schl", "District Name", "School Name", "Subject", "Grade", "Student_Group_Name",
                    "N Scored", "Pct. Advanced", "Pct. Proficient", "Pct. Basic", "Pct. Below Basic", "Growth",
                ],
                ["7691", "21ST CENTURY CYBER CS", "21ST CENTURY CYBER CS", "A", 11, "All Students", 20, 1, 2, 3, 4, 75],
            ],
        },
    )
    with pytest.raises(ValueError, match="school sheets"):
        parse_keystone_school(path, {"school_year": 2014, "document_id": "key-2014"})


def test_keystone_school_cell_round_trips_from_the_workbook(tmp_path: Path) -> None:
    path = tmp_path / "school.xlsx"
    _save(
        path,
        {
            "Sheet1": [
                ["2023 Keystone"],
                [
                    "Year", "AUN", "School Number", "County", "District Name", "School Name", "Subject", "Group", "Grade",
                    "Number Scored", "Percent Advanced", "Percent Proficient", "Percent Basic", "Percent Below Basic",
                    "% Advanced/Proficient",
                ],
                [2023, 102020001, "000007727", "Adams", "CITY CHS", "CITY CHS", "Algebra I", "All Students", 11, 81, 1.2, 14.8, 58.0, 25.9, 16.0],
            ],
        },
    )
    index = {
        "current": {"keystone-school-2022": "doc-1"},
        "documents": {
            "doc-1": {
                "parser": "keystone_school",
                "status": "stable",
                "school_year": 2022,
                "path": str(path),
                "catalog_id": "keystone-school-2022",
            }
        },
    }
    cell = {
        "school_year": 2022,
        "aun": "102020001",
        "school_number": "7727",
        "assessment": "keystone",
        "subject": "algebra_i",
        "grade": "011",
        "student_group": "All Students",
    }
    tables = {
        "assessment_result_school": pd.DataFrame([{
            "aun": "102020001",
            "school_number": "7727",
            "school_year": 2022,
            "assessment": "keystone",
            "subject": "algebra_i",
            "grade": "011",
            "student_group": "All Students",
            "number_scored": 81,
            "pct_advanced": 1.2,
            "pct_proficient": 14.8,
            "pct_basic": 58.0,
            "pct_below_basic": 25.9,
            "pct_proficient_and_above": 16.0,
            "growth": None,
        }])
    }
    assert _assessment_school_cell(tables, index, cell) == []
    tables["assessment_result_school"].loc[0, "pct_proficient_and_above"] = 16.1
    assert _assessment_school_cell(tables, index, cell)


def test_keystone_district_parser(tmp_path: Path) -> None:
    path = tmp_path / "keystone.xlsx"
    _assessment_book(path, sheet="Keystone")
    # rewrite subject/grade for keystone-shaped row via direct parse of same layout
    frame = parse_keystone(path, {"school_year": 2024, "document_id": "key-test"})["assessment_result"]
    assert frame.iloc[0]["assessment"] == "keystone"


def test_charter_adm_by_sd_keeps_aun_text(tmp_path: Path) -> None:
    path = tmp_path / "adm.xlsx"
    _save(
        path,
        {
            "CS ADM by SD": [
                ["AUN", "School District", "County", "2024-25\nAverage Daily Membership (ADM) in\nCharter Schools"],
                [112011103.0, "Bermudian Springs SD", "Adams", 116.716],
                [124150503, "Avon Grove SD", "Chester", 0],
            ],
            "CS ADM by CS": [
                ["AUN", "Charter School", "2024-25\nAverage Daily Membership (ADM)"],
                [124150003, "Avon Grove CS", 1886.148],
            ],
        },
    )
    frame = parse_charter_adm(path, {"school_year": 2024, "document_id": "adm-test"})["charter_adm"]
    assert set(frame["aun"]) == {"112011103", "124150503"}
    bermudian = frame.loc[frame["aun"] == "112011103"].iloc[0]
    assert bermudian["adm"] == 116.716
    assert int(bermudian["school_year"]) == 2024
    assert bermudian["document_id"] == "adm-test"
    assert float(frame.loc[frame["aun"] == "124150503", "adm"].iloc[0]) == 0.0


def test_iep_multi_year_skips_suppressed_and_wards(tmp_path: Path) -> None:
    path = tmp_path / "iep.xlsx"
    _save(
        path,
        {
            "2024-2025": [
                ["Number of Special Education Students and Total Enrollment by LEA"],
                ["2024-2025 School Year"],
                [],
                [],
                [],
                ["Created: 6/6/2025"],
                [],
                ["vw"],
                ["AGG"],
                [],
                [],
                [
                    "IU", "AUN", "School Name", "Number of Special Education Students",
                    "Total Enrollment", "Special Ed % of Total Public SD Enrollment",
                ],
                [1, 101260303.0, "Albert Gallatin Area SD", 858, 2903, 0.295556],
                [1, 101999999, "Wards of State", "*", 10, None],
                [1, 110143120, "Nittany Valley CS", "*", 50, None],
            ],
            "2008-2009": [
                ["Number of Special Education Students and Total Enrollment by LEA"],
                ["2008-2009 School Year"],
                [],
                [],
                [],
                ["Created: 1/1/2009"],
                [],
                ["vw"],
                ["RAW"],
                [],
                [],
                [
                    "IU", "AUN", "School Name", "Number of Special Education Students",
                    "Total Enrollment", "Special Ed % of Total Public SD Enrollment",
                ],
                [1, "101260303", "Albert Gallatin Area SD", 742, 3785, 19.6037],
            ],
        },
    )
    frame = parse_iep(path, {"document_id": "iep-test"})["enrollment_iep"]
    assert set(frame["aun"]) == {"101260303"}
    assert set(frame["school_year"]) == {2024, 2008}
    recent = frame.loc[frame["school_year"] == 2024].iloc[0]
    assert recent["iep_enrollment"] == 858
    assert recent["total_enrollment"] == 2903
    assert abs(recent["pct_iep"] - 29.5556) < 0.001
    assert recent["document_id"] == "iep-test"
    older = frame.loc[frame["school_year"] == 2008].iloc[0]
    assert older["iep_enrollment"] == 742
    assert abs(older["pct_iep"] - 19.6037) < 0.001


def test_low_income_lea_keeps_aun_text_and_percent(tmp_path: Path) -> None:
    path = tmp_path / "low_income.xlsx"
    _save(
        path,
        {
            "2025 LIP by LEA": [
                ["Percent Of Enrollments from Low-Income Families"],
                [],
                ["LEA Level"],
                ["Year: 2024-2025"],
                [
                    "SUBMITTING AUN", "LEA NAME", "LEA TYPE", "TOTAL ENROLLMENT",
                    "LOW INCOME ENROLLMENT", "PERCENT OF ENROLLMENT FROM LOW INCOME FAMILIES",
                ],
                [124150002.0, "21st Century Cyber CS", "Cyber CS", 996, 71, 0.0712],
                [112011103, "Bermudian Springs SD", "SD", 2000, 0, 0.0],
            ],
            "2025 LIP by School": [
                ["School Level"],
                [
                    "SUBMITTING AUN", "LEA NAME", "LEA TYPE", "SCHOOL NUMBER", "SCHOOL NAME",
                    "TOTAL ENROLLMENT", "LOW-INCOME ENROLLMENT",
                    "PERCENT OF ENROLLMENT FROM LOW INCOME FAMILIES",
                ],
                [124150002, "21st Century Cyber CS", "Cyber CS", "7691", "Campus", 996, 71, 0.0712],
            ],
        },
    )
    frame = parse_low_income(path, {"school_year": 2024, "document_id": "li-test"})["enrollment_low_income"]
    assert set(frame["aun"]) == {"124150002", "112011103"}
    cyber = frame.loc[frame["aun"] == "124150002"].iloc[0]
    assert cyber["low_income_enrollment"] == 71
    assert cyber["total_enrollment"] == 996
    assert cyber["pct_low_income"] == 7.12
    assert int(cyber["school_year"]) == 2024
    assert cyber["document_id"] == "li-test"
    assert int(frame.loc[frame["aun"] == "112011103", "low_income_enrollment"].iloc[0]) == 0


def test_homeschool_skips_county_totals(tmp_path: Path) -> None:
    path = tmp_path / "homeschool.xlsx"
    _save(
        path,
        {
            "For publication": [
                [
                    "2024-25 SY", "District Code", "County Name", "Private Tutor Total",
                    "Home Education Student Total", "Home School Students  5-11 yrs.",
                    "Home School Students  12+  yrs.",
                ],
                ["Bermudian Springs SD", 112011103.0, "Adams", 0, 120, 69, 51],
                [None, None, "Adams Total", 5, 708, 396, 312],
                [None, None, "Grand Total", 1476, 44692, 26355, 18337],
            ],
        },
    )
    frame = parse_homeschool(path, {"school_year": 2024, "document_id": "hs-test"})["home_education"]
    assert list(frame["aun"]) == ["112011103"]
    row = frame.iloc[0]
    assert row["students"] == 120
    assert row["private_tutor"] == 0
    assert row["age_5_11"] == 69
    assert row["age_12_plus"] == 51
    assert row["document_id"] == "hs-test"


_COHORT_GROUPS = [
    "Male Grad Rate", "Female Grad Rate", "AIAN Grad Rate",
    "Native Hawaiian or Pacific Islander Grad Rate", "Asian Grad Rate",
    "Black Grad Rate", "Hispanic Grad Rate", "White Grad Rate",
    "Multi-Racial Grad Rate", "Special Ed Grad Rate", "EL\nGrad Rate",
    "Econ Disadv Grad Rate", "Migrant Grad Rate",
]


def _cohort_book(path: Path, rows: list[list], *, extra: list[str] | None = None) -> None:
    header = ["LEA Type", "AUN", "LEA", "Grads", "Cohort", "Cohort Grad Rate", *_COHORT_GROUPS]
    if extra:
        header.extend(extra)
    _save(
        path,
        {
            "Notes": [["SY 1999-00 4-Year Cohort Graduation Rate"]],
            "Grad Rate by LEA": [["SY 1999-00 4-Year Cohort Graduation Rate by LEA"], [], header, *rows],
            "Grad Rate by School": [["School Number"], [7691]],
        },
    )


def _cohort_rates(*values: object) -> list:
    rates = list(values) + [None] * (len(_COHORT_GROUPS) - len(values))
    return rates[: len(_COHORT_GROUPS)]


def test_cohort_grad_keeps_published_rate_and_skips_blanks(tmp_path: Path) -> None:
    path = tmp_path / "cohort.xlsx"
    _cohort_book(
        path,
        [
            ["CS", 124150002.0, "21st Century Cyber CS", 180, 301, 0.598006644518272, *_cohort_rates(0.576923076923077, "Due to cohort size demographic information has been supressed to comply with FERPA regulations."), None, None, 0],
            ["Summary", None, "Statewide", 10, 10, 1, *_cohort_rates(1)],
            ["The LEA graduation rates include students attributed to the district.", None, None, None, None, None, *_cohort_rates()],
            ["SD", "112011103", "Bermudian Springs SD", 0, 10, 0, *_cohort_rates()],
        ],
        extra=["Foster Grad Rate", "Homeless Grad Rate", "Military Grad Rate"],
    )
    parsed = parse_cohort_grad(path, {"school_year": 2024, "span": 4, "document_id": "cohort-test"})
    facts = parsed["cohort_graduation"]
    assert list(facts["aun"]) == ["124150002", "112011103"]
    cyber = facts.loc[facts["aun"] == "124150002"].iloc[0]
    assert int(cyber["school_year"]) == 2024
    assert int(cyber["span"]) == 4
    assert int(cyber["graduates"]) == 180
    assert int(cyber["cohort"]) == 301
    assert cyber["rate"] == 0.598006644518272
    assert cyber["document_id"] == "cohort-test"
    assert int(facts.loc[facts["aun"] == "112011103", "graduates"].iloc[0]) == 0
    groups = parsed["cohort_graduation_group"]
    cyber_groups = groups.loc[groups["aun"] == "124150002"].set_index("student_group")["rate"]
    assert cyber_groups["male"] == 0.576923076923077
    assert cyber_groups["military"] == 0
    assert "female" not in cyber_groups.index
    assert "migrant" not in cyber_groups.index
    assert groups.loc[groups["aun"] == "112011103"].empty


def test_cohort_grad_reads_a_blank_header_from_the_extract(tmp_path: Path) -> None:
    path = tmp_path / "cohort-blank.xlsx"
    header = [None, "LEA Type", "AUN", "LEA", "Grads", "Cohort", "Cohort Grad Rate", *_COHORT_GROUPS]
    row = [None, "SD", 101260303.0, "Albert Gallatin Area SD", 262, 327, 0.80122324159, *_cohort_rates(0.811764705882)]
    _save(
        path,
        {
            "Notes": [["note"]],
            "Grad Rate by LEA": [["title"], [], header, row],
            "Grad Rate by School": [["School Number"], [1]],
        },
    )
    document = {"school_year": 2017, "span": 4, "document_id": "cohort-2017"}
    direct = parse_cohort_grad(path, document)["cohort_graduation"]
    data = tmp_path / "data"
    index = load_index(data)
    entry = CatalogEntry(
        id="cohort-grad-2017-4",
        source_id="cohort",
        source_url=path.as_uri(),
        page_url=path.as_uri(),
        parser="cohort_grad",
        status="stable",
        school_year=2017,
        span=4,
    )
    record = store_bytes(entry, path.read_bytes(), data, index, path.name)
    from pa_edu.extract import ensure_extract, use_extract

    record = ensure_extract(data, index, record)
    with use_extract(path, record["extract_path"]):
        extracted = parse_cohort_grad(path, document)["cohort_graduation"]
    assert list(extracted["aun"]) == list(direct["aun"])
    assert int(extracted.iloc[0]["graduates"]) == 262
    assert extracted.iloc[0]["rate"] == direct.iloc[0]["rate"]


def test_cohort_grad_accepts_the_layout_without_later_groups(tmp_path: Path) -> None:
    path = tmp_path / "cohort-core.xlsx"
    _cohort_book(
        path,
        [["SD", 101260303.0, "Albert Gallatin Area SD", 262, 327, 0.80122324159, *_cohort_rates(0.811764705882)]],
    )
    facts = parse_cohort_grad(path, {"school_year": 2017, "span": 6, "document_id": "cohort-2017"})["cohort_graduation"]
    assert list(facts["aun"]) == ["101260303"]
    assert int(facts.iloc[0]["span"]) == 6
    assert int(facts.iloc[0]["school_year"]) == 2017


def test_cohort_grad_rejects_an_unknown_column(tmp_path: Path) -> None:
    path = tmp_path / "cohort-unknown.xlsx"
    _cohort_book(
        path,
        [["SD", 101260303, "Albert Gallatin Area SD", 1, 2, 0.5, *_cohort_rates(0.5)]],
        extra=["Mystery Grad Rate"],
    )
    try:
        parse_cohort_grad(path, {"school_year": 2024, "span": 4, "document_id": "cohort-test"})
    except ValueError as error:
        assert "Mystery" in str(error)
    else:
        raise AssertionError("unknown column was accepted")


def test_cohort_grad_rejects_the_older_total_grads_layout(tmp_path: Path) -> None:
    path = tmp_path / "cohort-old.xlsx"
    _save(
        path,
        {
            "Grad Rate by LEA": [[
                "LEA Type", "AUN", "LEA", "Total Grads", "Total Cohort", "Total Grad Rate",
                "Male Grad Rate", "ELL Grad Rate",
            ]],
        },
    )
    try:
        parse_cohort_grad(path, {"school_year": 2010, "span": 4, "document_id": "cohort-old"})
    except ValueError as error:
        assert "unrecognized" in str(error) or "missing" in str(error)
    else:
        raise AssertionError("older layout was accepted")
