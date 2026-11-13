"""Parser and rebuild tests. They use tiny workbooks, not PDE."""

from pathlib import Path

import duckdb
import pandas as pd
from openpyxl import Workbook

from pa_edu.check import _grain, GRAIN
from pa_edu.parse_act1 import base_from_text, parse_act1
from pa_edu.parse_charter_adm import parse_charter_adm
from pa_edu.parse_cohort_grad import parse_cohort_grad
from pa_edu.parse_homeschool import parse_homeschool
from pa_edu.parse_iep import parse_iep
from pa_edu.parse_low_income import parse_low_income
from pa_edu.parse_retax import parse_retax
from pa_edu.parse_assessment import parse_keystone, parse_pssa
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


def _gfb_book(path: Path) -> None:
    _save(
        path,
        {
            "Exp": [
                ["InstCat", "AUN", "InstName", "CountyName", "1100-100", "1100-200", "Notes", ""],
                [1, 101260303.0, "Albert Gallatin Area SD", "Fayette", 5, 0, "ignore", None],
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
