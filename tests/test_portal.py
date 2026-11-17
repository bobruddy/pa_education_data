import json
import os
import threading
import zipfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from pa_edu.portal import (
    TABLES,
    assessment_school_select,
    build_portal,
    county_slug,
    load_views,
    schema_sql,
    write_duckdb,
)
from pa_edu.refine import COLUMNS


def test_portal_describes_every_refined_table() -> None:
    assert set(TABLES) == set(COLUMNS)


def test_county_slug_is_a_file_name() -> None:
    assert county_slug("McKean") == "mckean"
    assert county_slug("Adams") == "adams"


def test_about_control_opens_from_the_header_and_footer() -> None:
    root = Path(__file__).resolve().parents[1]
    html = (root / "pa_edu" / "web" / "index.html").read_text(encoding="utf-8")
    script = (root / "pa_edu" / "web" / "app.js").read_text(encoding="utf-8")
    header, _, rest = html.partition("</header>")
    assert header.index('class="nav-link" data-about-open') < header.index('href="download/"')
    footer = rest[rest.index('class="site-foot"') :]
    assert footer.index('class="foot-link" data-about-open') < footer.index("Download the tables")
    assert 'id="about"' in html
    assert "pde-about-seen" in script
    assert "30 * 24 * 60 * 60 * 1000" in script


def test_downloads_link_leaves_the_lea_browser() -> None:
    root = Path(__file__).resolve().parents[1]
    html = (root / "pa_edu" / "web" / "index.html").read_text(encoding="utf-8")
    script = (root / "pa_edu" / "web" / "app.js").read_text(encoding="utf-8")
    stamp = (root / "pa_edu" / "web" / "stamp.js").read_text(encoding="utf-8")
    assert 'class="nav-link site-link" href="download/"' in html
    assert 'class="site-link" href="download/"' in html
    assert 'classList.contains("site-link")' in script
    assert 'id="build-stamp"' in html
    assert 'data-template="01-feature-request.yml"' in html
    assert 'data-template="02-data-problem.yml"' in html
    assert 'data-template="03-site-bug.yml"' in html
    assert 'data-page-field="url"' in html
    assert "build.json" in stamp
    assert 'params.set("build"' in stamp
    for name in ("01-feature-request.yml", "02-data-problem.yml", "03-site-bug.yml"):
        body = (root / ".github" / "ISSUE_TEMPLATE" / name).read_text(encoding="utf-8")
        assert "id: build" in body


def test_portal_packages_one_county_and_keeps_lookup_tables(tmp_path: Path) -> None:
    refined = tmp_path / "refined"
    refined.mkdir()
    _write(refined / "lea.parquet", """
        SELECT * FROM (VALUES
            ('101260303', 'Albert Gallatin Area SD', 'school_district', 'open', 'Adams', NULL, true, 'doc-1'),
            ('112011103', 'Beaver Area SD', 'school_district', 'open', 'Beaver', NULL, true, 'doc-1'),
            ('131000000', 'Corrections', 'unknown', 'unknown', NULL, NULL, false, 'doc-1')
        ) t(aun, lea_name, category, status, county, iu_aun, in_directory, document_id)
    """)
    _write(refined / "document.parquet", """
        SELECT 'doc-1' AS document_id, 'https://example.test/gfb.xlsx' AS source_url
    """)
    _write(refined / "account.parquet", """
        SELECT '1100' AS function_code, '100' AS object_code,
               'Regular programs' AS function_name, 'Salaries' AS object_name,
               '1000' AS major_function, '100' AS major_object
    """)
    _write(refined / "grade.parquet", """
        SELECT '001' AS grade_code, 'Grade 1' AS label, 'grade' AS band, 'full' AS session
    """)
    _write(refined / "act1_base.parquet", """
        SELECT 2024 AS school_year, 3.5 AS base_index, 'doc-1' AS document_id
    """)
    _write(refined / "chart_description.parquet", """
        SELECT * FROM (VALUES
            ('object', '571', 'Food Service Management – Food Costs', 'Expenditures for food costs.'),
            ('function', '1100', 'REGULAR PROGRAMS – ELEMENTARY / SECONDARY', 'Activities designed to provide grades K-12.')
        ) t(kind, code, name, description)
    """)
    _write(refined / "enrollment.parquet", """
        SELECT * FROM (VALUES
            ('101260303', '0001', 'A G High', 2024, '001', 10, 'Albert Gallatin Area SD', 'SD', 'Adams', 'doc-1'),
            ('101260303', '0001', 'A G High', 2024, '002', 5, 'Albert Gallatin Area SD', 'SD', 'Adams', 'doc-1'),
            ('112011103', '0001', 'Beaver High', 2024, '001', 3, 'Beaver Area SD', 'SD', 'Beaver', 'doc-1'),
            ('131000000', '0001', 'Corrections', 2024, '001', 9, 'Corrections', 'STATE', NULL, 'doc-1')
        ) t(aun, school_number, school_name, school_year, grade_code, enrollment, lea_name, lea_type, county, document_id)
    """)
    _write(refined / "gfb_expenditure.parquet", """
        SELECT * FROM (VALUES
            ('101260303', 2024, '1100', '100', '', 80.0, '10', 'doc-1'),
            ('131000000', 2024, '1100', '100', '', 4.0, '10', 'doc-1')
        ) t(aun, school_year, function_code, object_code, program_code, amount, fund_code, document_id)
    """)
    _write(refined / "afr_expenditure.parquet", """
        SELECT * FROM (VALUES
            ('101260303', 2024, '10', '1110', '120', '', 1.0, 2.0, 0.0, 5.0, 'doc-1'),
            ('101260303', 2024, '23', '1110', '120', '', 0.0, 0.0, 7.0, 7.0, 'doc-1')
        ) t(aun, school_year, fund_code, function_code, object_code, program_code,
            elementary_amount, secondary_amount, federal_amount, total_amount, document_id)
    """)
    _write(refined / "professional_staff.parquet", """
        SELECT * FROM (VALUES
            ('101260303', 2024, 'p1', 50000.0, 100.0),
            ('112011103', 2024, 'p2', 60000.0, 100.0)
        ) t(aun, school_year, public_id, annual_salary, fte_percent)
    """)

    out = tmp_path / "download"
    build_portal(out, refined)

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["tables"][0]["name"] == "document"
    lea = next(item for item in manifest["tables"] if item["name"] == "lea")
    assert lea["rows"] == 3
    assert {item["slug"] for item in manifest["counties"]} == {"adams", "beaver"}
    assert manifest["unassigned"] == [{"aun": "131000000", "lea_name": "Corrections"}]
    assert "enrollment_headcount" in {item["name"] for item in manifest["views"]}

    page = (out / "index.html").read_text(encoding="utf-8")
    assert 'href="counties/adams.zip"' in page
    assert "1 LEA" in page
    assert "1 LEAs" not in page
    assert "Corrections (131000000)" in page
    assert "enrollment_headcount" in page
    assert 'href="../"' in page
    assert 'id="build-stamp"' in page
    assert 'src="../stamp.js?v=' in page
    schema = (out / "schema.sql").read_text(encoding="utf-8")
    assert "https://pdenumbers.org/download/tables/lea.parquet" in schema
    assert "schema=" not in schema
    assert "INSTALL httpfs;" in schema

    adams = _unzip(out / "counties" / "adams.zip", tmp_path / "adams")
    beaver = _unzip(out / "counties" / "beaver.zip", tmp_path / "beaver")
    assert _column(adams / "lea.parquet", "aun") == ["101260303"]
    assert _column(beaver / "lea.parquet", "aun") == ["112011103"]
    assert _column(adams / "gfb_expenditure.parquet", "aun") == ["101260303"]
    assert _column(adams / "enrollment.parquet", "aun") == ["101260303", "101260303"]
    assert _column(adams / "professional_staff.parquet", "public_id") == ["p1"]
    assert _column(beaver / "professional_staff.parquet", "public_id") == ["p2"]
    assert "_portal_county" not in _describe(adams / "gfb_expenditure.parquet")
    assert _scalar(adams / "document.parquet", "SELECT source_url FROM read_parquet(?)") == "https://example.test/gfb.xlsx"
    assert _scalar(adams / "act1_base.parquet", "SELECT base_index FROM read_parquet(?)") == 3.5
    assert _scalar(adams / "grade.parquet", "SELECT label FROM read_parquet(?)") == "Grade 1"
    assert _scalar(
        adams / "chart_description.parquet",
        "SELECT name FROM read_parquet(?) WHERE code = '571'",
    ) == "Food Service Management – Food Costs"
    assert _column(adams / "chart_description.parquet", "code") == _column(
        beaver / "chart_description.parquet", "code"
    )
    readme = (adams / "README.txt").read_text(encoding="utf-8")
    assert "Adams County" in readme
    assert "duckdb county.duckdb" in readme

    previous = Path.cwd()
    os.chdir(adams)
    try:
        connection = duckdb.connect("county.duckdb", read_only=True)
        try:
            assert connection.execute("SELECT count(*) FROM school_district").fetchone()[0] == 1
            assert connection.execute(
                "SELECT sum(enrollment) FROM enrollment_headcount WHERE aun = '101260303'"
            ).fetchone()[0] == 15
            assert connection.execute("SELECT count(*) FROM afr_general_fund").fetchone()[0] == 1
            assert connection.execute("SELECT function_name, object_name, amount FROM gfb_line").fetchone() == (
                "Regular programs",
                "Salaries",
                80.0,
            )
            assert connection.execute(
                "SELECT total_amount FROM afr_general_fund_line"
            ).fetchone()[0] == 5.0
        finally:
            connection.close()
    finally:
        os.chdir(previous)


def test_assessment_lea_copies_one_school_and_skips_two() -> None:
    statement = next(view.sql for view in load_views() if view.name == "assessment_lea")
    district = _result("112011103", 10.0, "district-doc")
    charter_only = _result("124150002", 1.0, "district-doc")
    school = pd.DataFrame([
        _school("112011103", "0001", "Elem", 99.0, "school-doc"),
        _school("124150002", "000007691", "21st Century Cyber CS", 40.0, "school-doc"),
        _school("123456789", "0001", "One", 1.0, "school-doc"),
        _school("123456789", "0002", "Two", 2.0, "school-doc"),
        _school("999999999", "0001", "Missing", 8.0, "school-doc"),
    ])
    lea = pd.DataFrame([
        {"aun": "112011103", "category": "school_district"},
        {"aun": "124150002", "category": "charter_school"},
        {"aun": "123456789", "category": "charter_school"},
    ])
    connection = duckdb.connect()
    try:
        connection.register("assessment_result", pd.DataFrame([district, charter_only]))
        connection.register("assessment_result_school", school)
        connection.register("lea", lea)
        connection.execute(statement)
        frame = connection.execute("SELECT * FROM assessment_lea ORDER BY aun").fetchdf()
    finally:
        connection.close()
    assert "growth" not in frame.columns
    assert list(frame["aun"]) == ["112011103", "124150002"]
    district_row = frame.loc[frame["aun"] == "112011103"].iloc[0]
    assert district_row["pct_proficient_and_above"] == 10.0
    assert pd.isna(district_row["school_number"])
    assert pd.isna(district_row["school_name"])
    assert district_row["document_id"] == "district-doc"
    charter = frame.loc[frame["aun"] == "124150002"].iloc[0]
    assert charter["pct_proficient_and_above"] == 40.0
    assert charter["school_number"] == "000007691"
    assert charter["school_name"] == "21st Century Cyber CS"
    assert charter["category"] == "charter_school"
    assert charter["document_id"] == "school-doc"


def test_assessment_lea_copies_one_keystone_school_and_skips_two() -> None:
    statement = next(view.sql for view in load_views() if view.name == "assessment_lea")
    district = _result("112011103", 20.0, "district-key", "keystone")
    school = pd.DataFrame([
        _school("112011103", "1367", "Avon Grove HS", 99.0, "school-doc", "keystone"),
        _school("102020001", "7727", "City CHS", 22.8, "school-doc", "keystone"),
        _school("114060557", "6304", "Berks CTC East", 1.0, "school-doc", "keystone"),
        _school("114060557", "7068", "Berks CTC West", 2.0, "school-doc", "keystone"),
    ])
    lea = pd.DataFrame([
        {"aun": "112011103", "category": "school_district"},
        {"aun": "102020001", "category": "charter_school"},
        {"aun": "114060557", "category": "career_and_technical_center"},
    ])
    connection = duckdb.connect()
    try:
        connection.register("assessment_result", pd.DataFrame([district]))
        connection.register("assessment_result_school", school)
        connection.register("lea", lea)
        connection.execute(statement)
        frame = connection.execute("SELECT * FROM assessment_lea ORDER BY aun").fetchdf()
    finally:
        connection.close()
    assert list(frame["aun"]) == ["102020001", "112011103"]
    charter = frame.loc[frame["aun"] == "102020001"].iloc[0]
    assert charter["assessment"] == "keystone"
    assert charter["pct_proficient_and_above"] == 22.8
    assert charter["school_number"] == "7727"
    assert charter["school_name"] == "City CHS"
    assert charter["category"] == "charter_school"
    district_row = frame.loc[frame["aun"] == "112011103"].iloc[0]
    assert district_row["pct_proficient_and_above"] == 20.0
    assert pd.isna(district_row["school_number"])
    assert district_row["document_id"] == "district-key"
    assert "114060557" not in set(frame["aun"])


def test_model_school_view_uses_the_keystone_sum() -> None:
    text = (Path(__file__).resolve().parents[1] / "sql" / "model.sql").read_text(encoding="utf-8")
    expected = (
        "CREATE OR REPLACE VIEW assessment_result_school AS\n"
        + assessment_school_select("read_parquet('data/refined/assessment_result_school.parquet')")
        + ";"
    )
    assert expected in text


def test_school_view_fills_a_null_keystone_proficient_plus(tmp_path: Path) -> None:
    building = _school("112011103", "1367", "Avon Grove HS", None, "school-doc", "keystone")
    building["pct_advanced"] = 4.1
    building["pct_proficient"] = 56.4
    charter = _school("102020001", "7727", "City CHS", None, "school-doc", "keystone")
    charter["pct_advanced"] = 10.0
    charter["pct_proficient"] = 30.0
    published = _school("115210001", "8001", "One Campus", 16.0, "school-doc", "keystone")
    partial = _school("124150002", "7691", "Cyber", None, "school-doc", "keystone")
    partial["pct_proficient"] = None
    pssa = _school("126000002", "3", "Early", None, "pssa-school", "pssa")
    pssa["pct_advanced"] = 10.4
    pssa["pct_proficient"] = 25.9
    east = _school("114060557", "6304", "East", None, "school-doc", "keystone")
    west = _school("114060557", "7068", "West", None, "school-doc", "keystone")
    tables = tmp_path / "tables"
    tables.mkdir()
    pd.DataFrame([building, charter, published, partial, pssa, east, west]).to_parquet(
        tables / "assessment_result_school.parquet", index=False,
    )
    pd.DataFrame([_result("112011103", 20.0, "district-key", "keystone")]).to_parquet(
        tables / "assessment_result.parquet", index=False,
    )
    pd.DataFrame([
        {"aun": "112011103", "category": "school_district"},
        {"aun": "102020001", "category": "charter_school"},
        {"aun": "115210001", "category": "career_and_technical_center"},
        {"aun": "124150002", "category": "charter_school"},
        {"aun": "126000002", "category": "charter_school"},
        {"aun": "114060557", "category": "career_and_technical_center"},
    ]).to_parquet(tables / "lea.parquet", index=False)

    connection = duckdb.connect()
    try:
        connection.execute(schema_sql(tables.resolve().as_posix(), [
            "assessment_result",
            "assessment_result_school",
            "lea",
        ]))
        building_pct = connection.execute("""
            SELECT pct_proficient_and_above
            FROM assessment_result_school
            WHERE school_number = '1367'
        """).fetchone()[0]
        kept = connection.execute("""
            SELECT pct_proficient_and_above
            FROM assessment_result_school
            WHERE aun = '115210001'
        """).fetchone()[0]
        partial_pct = connection.execute("""
            SELECT pct_proficient_and_above
            FROM assessment_result_school
            WHERE aun = '124150002'
        """).fetchone()[0]
        pssa_pct = connection.execute("""
            SELECT pct_proficient_and_above
            FROM assessment_result_school
            WHERE aun = '126000002'
        """).fetchone()[0]
        centers = connection.execute("""
            SELECT school_number, pct_proficient_and_above
            FROM assessment_result_school
            WHERE aun = '114060557'
            ORDER BY school_number
        """).fetchall()
        lea = connection.execute("SELECT aun, pct_proficient_and_above FROM assessment_lea").fetchdf()
    finally:
        connection.close()

    assert building_pct == 60.5
    assert kept == 16.0
    assert partial_pct is None or pd.isna(partial_pct)
    assert pssa_pct == 36.3
    assert centers == [("6304", 3.0), ("7068", 3.0)]

    def proficient(aun: str):
        value = lea.loc[lea["aun"] == aun, "pct_proficient_and_above"].iloc[0]
        return None if pd.isna(value) else value

    assert set(lea["aun"]) == {"112011103", "102020001", "115210001", "124150002", "126000002"}
    assert proficient("112011103") == 20.0
    assert proficient("102020001") == 40.0
    assert proficient("115210001") == 16.0
    assert proficient("124150002") is None
    assert proficient("126000002") == 36.3


def test_public_school_view_binds_the_sum_without_fetching(tmp_path: Path) -> None:
    tables = tmp_path / "tables"
    tables.mkdir()
    frame = pd.DataFrame([{
        "aun": "102020001",
        "assessment": "keystone",
        "pct_advanced": 4.1,
        "pct_proficient": 56.4,
        "pct_proficient_and_above": None,
    }])
    frame.to_parquet(tables / "assessment_result_school.parquet", index=False)
    database = tmp_path / "pdenumbers.duckdb"
    write_duckdb(
        database,
        "https://127.0.0.1:9/download/tables",
        ["assessment_result_school"],
        schema_from=tables,
        extension_directory=tmp_path / "extensions",
    )
    connection = duckdb.connect(
        str(database),
        read_only=True,
        config={
            "extension_directory": str(tmp_path / "extensions"),
            "home_directory": str(tmp_path / "extensions"),
        },
    )
    try:
        sql = connection.execute(
            "SELECT sql FROM duckdb_views() WHERE view_name = 'assessment_result_school'"
        ).fetchone()[0]
        assert "pct_advanced + pct_proficient" in sql
        assert "https://127.0.0.1:9/download/tables/assessment_result_school.parquet" in sql
        assert str(tables) not in sql
        columns = connection.execute("DESCRIBE SELECT * FROM assessment_result_school").fetchall()
        assert [row[0] for row in columns] == list(frame.columns)
    finally:
        connection.close()


def _result(aun: str, proficient: float, document_id: str, assessment: str = "pssa") -> dict:
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
        "lea_name": "Name",
        "county": "Adams",
        "document_id": document_id,
    }


def _school(
    aun: str,
    school_number: str,
    school_name: str,
    proficient: float,
    document_id: str,
    assessment: str = "pssa",
) -> dict:
    return {
        **_result(aun, proficient, document_id, assessment),
        "school_number": school_number,
        "school_name": school_name,
        "growth": 5.0,
    }


def test_unknown_refined_table_is_rejected(tmp_path: Path) -> None:
    refined = tmp_path / "refined"
    refined.mkdir()
    _write(refined / "lea.parquet", """
        SELECT '101260303' AS aun, 'One' AS lea_name, 'school_district' AS category,
               'open' AS status, 'Adams' AS county
    """)
    _write(refined / "extra.parquet", "SELECT 1 AS n")
    with pytest.raises(SystemExit, match="extra.parquet"):
        build_portal(tmp_path / "download", refined)


def test_public_duckdb_binds_columns_without_fetching(tmp_path: Path) -> None:
    tables = tmp_path / "tables"
    tables.mkdir()
    _write(tables / "lea.parquet", """
        SELECT '101260303' AS aun, 'Albert Gallatin Area SD' AS lea_name,
               'school_district' AS category, true AS in_directory
    """)
    database = tmp_path / "pdenumbers.duckdb"
    write_duckdb(
        database,
        "https://127.0.0.1:9/download/tables",
        ["lea"],
        schema_from=tables,
        extension_directory=tmp_path / "extensions",
    )
    connection = duckdb.connect(
        str(database),
        read_only=True,
        config={
            "extension_directory": str(tmp_path / "extensions"),
            "home_directory": str(tmp_path / "extensions"),
        },
    )
    try:
        sql = connection.execute(
            "SELECT sql FROM duckdb_views() WHERE view_name = 'lea'"
        ).fetchone()[0]
        assert "https://127.0.0.1:9/download/tables/lea.parquet" in sql
        assert '"schema"' in sql
        assert str(tables) not in sql
        columns = connection.execute("DESCRIBE SELECT * FROM lea").fetchall()
        assert [row[0] for row in columns] == ["aun", "lea_name", "category", "in_directory"]
        assert [row[1] for row in columns] == ["VARCHAR", "VARCHAR", "VARCHAR", "BOOLEAN"]
        district = connection.execute("DESCRIBE SELECT * FROM school_district").fetchall()
        assert [row[0] for row in district] == ["aun", "lea_name", "category", "in_directory"]
    finally:
        connection.close()


def test_duckdb_views_read_parquet_over_http(tmp_path: Path) -> None:
    tables = tmp_path / "tables"
    tables.mkdir()
    _write(tables / "lea.parquet", """
        SELECT '101260303' AS aun, 'Albert Gallatin Area SD' AS lea_name,
               'school_district' AS category, 'Fayette' AS county
    """)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(tables))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        database = tmp_path / "pdenumbers.duckdb"
        write_duckdb(
            database,
            f"http://127.0.0.1:{port}",
            ["lea"],
            extension_directory=tmp_path / "extensions",
        )
        connection = duckdb.connect(
            str(database),
            read_only=True,
            config={
                "extension_directory": str(tmp_path / "extensions"),
                "home_directory": str(tmp_path / "extensions"),
            },
        )
        try:
            connection.execute("LOAD httpfs")
            sql = connection.execute(
                "SELECT sql FROM duckdb_views() WHERE view_name = 'lea'"
            ).fetchone()[0]
            assert f"http://127.0.0.1:{port}/lea.parquet" in sql
            assert connection.execute("SELECT lea_name FROM lea").fetchone()[0] == "Albert Gallatin Area SD"
        finally:
            connection.close()
    finally:
        server.shutdown()


def _handler(directory: Path):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)

        def log_message(self, fmt: str, *args) -> None:
            return

    return Handler


def _write(path: Path, select_sql: str) -> None:
    connection = duckdb.connect()
    connection.execute(f"COPY ({select_sql}) TO '{path.as_posix()}' (FORMAT PARQUET)")
    connection.close()


def _unzip(path: Path, dest: Path) -> Path:
    dest.mkdir()
    with zipfile.ZipFile(path) as archive:
        archive.extractall(dest)
    return dest


def _column(path: Path, name: str) -> list:
    connection = duckdb.connect()
    try:
        return [row[0] for row in connection.execute(
            f"SELECT {name} FROM read_parquet(?) ORDER BY ALL",
            [str(path)],
        ).fetchall()]
    finally:
        connection.close()


def _describe(path: Path) -> set[str]:
    connection = duckdb.connect()
    try:
        return {row[0] for row in connection.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]).fetchall()}
    finally:
        connection.close()


def _scalar(path: Path, sql: str):
    connection = duckdb.connect()
    try:
        return connection.execute(sql, [str(path)]).fetchone()[0]
    finally:
        connection.close()
