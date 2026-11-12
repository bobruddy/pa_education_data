"""Parser and rebuild tests. They use tiny workbooks, not PDE."""

from pathlib import Path

import duckdb
import pandas as pd
from openpyxl import Workbook

from pa_edu.check import _grain, GRAIN
from pa_edu.parse_act1 import base_from_text, parse_act1
from pa_edu.parse_charter_adm import parse_charter_adm
from pa_edu.parse_homeschool import parse_homeschool
from pa_edu.parse_retax import parse_retax
from pa_edu.parse_assessment import parse_keystone, parse_pssa
from pa_edu.parse_chart import titles_from_text
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
    functions, objects = titles_from_text(text)
    assert functions["1110"] == "REGULAR PROGRAMS"
    assert objects["120"] == "PROFESSIONAL – TEACHERS"
    assert "6111" not in objects


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
