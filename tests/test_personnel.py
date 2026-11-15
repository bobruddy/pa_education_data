from pathlib import Path

import duckdb
import pandas as pd
from openpyxl import Workbook

from pa_edu.extract import read_workbook
from pa_edu.personnel import _primary_flag, normalize_assignments, refresh, staff_rows, write_personnel_tables
from pa_edu.personnel_layouts import LAYOUTS
from pa_edu.refine import COLUMNS, _ensure_personnel
from pa_edu.storage import load_index


def test_primary_flag_accepts_an_all_blank_string_column() -> None:
    blank = _primary_flag(pd.Series([pd.NA, pd.NA], dtype="string"))
    assert blank.isna().all()
    assert str(blank.dtype) == "boolean"
    marked = _primary_flag(pd.Series(["Yes", "No", None], dtype="string"))
    assert marked.iloc[0]
    assert marked.iloc[1] == False
    assert pd.isna(marked.iloc[2])


def test_normalize_accepts_blank_string_columns() -> None:
    headers = list(LAYOUTS["spaced_2012"])
    frame = pd.DataFrame({header: pd.Series([pd.NA], dtype="string") for header in headers})
    frame["SY"] = "2024-25"
    frame["Staff Snapshot Date"] = "2024-10-01"
    frame["Public ID"] = "12345"
    frame["AUN"] = "101260303"
    frame["Annual Salary"] = "70000"
    out = normalize_assignments(frame, 2024, "staff.xlsx")
    assert out["primary_assignment"].isna().all()
    assert pd.isna(out["time_status"].iloc[0])


def test_staff_rows_keep_one_salary_per_person() -> None:
    assignments = pd.DataFrame({
        "public_id": ["1", "1", "2", "2"],
        "aun": ["101260303", "101260303", "101260303", "101260303"],
        "school_year": [2024, 2024, 2024, 2024],
        "primary_assignment": pd.Series([True, False, pd.NA, pd.NA], dtype="boolean"),
        "fte_percent": [40.0, 80.0, 50.0, 90.0],
        "assignment_code": ["b", "a", "z", "m"],
        "annual_salary": [70_000.0, 70_000.0, 40_000.0, 40_000.0],
    })
    staff = staff_rows(assignments)
    assert len(staff) == 2
    primary = staff.loc[staff["public_id"] == "1"].iloc[0]
    assert primary["assignment_code"] == "b"
    assert primary["row_rule"] == "primary_assignment"
    assert int(primary["assignment_count"]) == 2
    assert primary["annual_salary"] == 70_000
    fallback = staff.loc[staff["public_id"] == "2"].iloc[0]
    assert fallback["assignment_code"] == "m"
    assert fallback["row_rule"] == "highest_fte"


def test_personnel_parquet_keeps_assignment_and_staff_grain(tmp_path: Path) -> None:
    early = _assignment("b", "101260303", 2024, "20", 80_000.0)
    late = _assignment("a", "101260303", 2023, "10", 60_000.0)
    refined = tmp_path / "refined"
    write_personnel_tables(
        [early, late],
        [staff_rows(early), staff_rows(late)],
        refined,
    )
    connection = duckdb.connect()
    try:
        assignment = connection.execute(
            """
            SELECT school_year, public_id, annual_salary
            FROM read_parquet(?)
            ORDER BY school_year, public_id
            """,
            [str(refined / "professional_assignment.parquet")],
        ).fetchall()
        staff = connection.execute(
            """
            SELECT school_year, public_id, row_rule, assignment_count
            FROM read_parquet(?)
            """,
            [str(refined / "professional_staff.parquet")],
        ).fetchall()
        columns = [
            row[0]
            for row in connection.execute(
                "DESCRIBE SELECT * FROM read_parquet(?)",
                [str(refined / "professional_staff.parquet")],
            ).fetchall()
        ]
    finally:
        connection.close()
    assert assignment == [(2023, "a", 60_000.0), (2024, "b", 80_000.0)]
    assert staff == [(2023, "a", "highest_fte", 1), (2024, "b", "highest_fte", 1)]
    assert columns == COLUMNS["professional_staff"]


def test_refine_leaves_existing_staff_parquet_in_place(tmp_path: Path) -> None:
    refined = tmp_path / "refined"
    refined.mkdir()
    sentinel = refined / "professional_staff.parquet"
    sentinel.write_bytes(b"already-written")
    _ensure_personnel(refined)
    assert sentinel.read_bytes() == b"already-written"
    assert (refined / "professional_assignment.parquet").exists()


def _assignment(
    public_id: str,
    aun: str,
    school_year: int,
    assignment_code: str,
    annual_salary: float,
) -> pd.DataFrame:
    return pd.DataFrame({
        "public_id": [public_id],
        "aun": [aun],
        "school_year": [school_year],
        "primary_assignment": pd.Series([pd.NA], dtype="boolean"),
        "fte_percent": [100.0],
        "assignment_code": [assignment_code],
        "annual_salary": [annual_salary],
        "source_file": ["staff.xlsx"],
    })


def _staff_book(path: Path, year: int, salary: float, public_id: float = 12345.0) -> None:
    headers = list(LAYOUTS["spaced_2012"])
    values = {header: None for header in headers}
    values.update({
        "SY": f"{year}-{(year + 1) % 100:02d}",
        "Staff Snapshot Date": f"{year}-10-01",
        "Public ID": public_id,
        "Last Name": "Ada",
        "First Name": "Ann",
        "Gender": "F",
        "Race With Description": "White",
        "Annual Salary": salary,
        "Degree Code": "05",
        "Years In ED": 10,
        "Years In LEA": 4,
        "Status": "A",
        "AUN": 101260303.0,
        "LEAName": "Albert Gallatin Area SD",
        "LEAType Description": "School District",
        "LEACounty Code": "26",
        "LEACounty": "Fayette",
        "School Location Number": 9999.0,
        "School": "Elem",
        "FT/PT": "FT",
        "Job Class": "1",
        "Primary Assignment": "Yes",
        "Assign Code": "b",
        "Assignment Description": "Teacher",
        "Position Number": "1",
        "Position Description": "Teacher",
        "EDF Number": "1",
        "EDF Category": "Elementary",
        "Category Description": "Elementary",
        "FTE%": 40,
    })
    second = dict(values)
    second["Primary Assignment"] = "No"
    second["Assign Code"] = "a"
    second["FTE%"] = 80
    second["School Location Number"] = 0
    book = Workbook()
    sheet = book.active
    sheet.append(headers)
    sheet.append([values[header] for header in headers])
    sheet.append([second[header] for header in headers])
    path.parent.mkdir(parents=True, exist_ok=True)
    book.save(path)


def test_personnel_warm_run_does_not_open_excel(tmp_path, monkeypatch) -> None:
    early = tmp_path / "files" / "staff-2024.xlsx"
    late = tmp_path / "files" / "staff-2025.xlsx"
    _staff_book(early, 2024, 70_000)
    _staff_book(late, 2025, 80_000)
    data = tmp_path / "data"
    sources = [(2024, early.as_uri()), (2025, late.as_uri())]
    refresh(data, sources)
    assignment = pd.read_parquet(data / "refined" / "professional_assignment.parquet")
    staff = pd.read_parquet(data / "refined" / "professional_staff.parquet")
    assert len(assignment) == 4
    assert len(staff) == 2
    chosen = staff.loc[staff["school_year"] == 2024].iloc[0]
    assert chosen["row_rule"] == "primary_assignment"
    assert chosen["assignment_code"] == "b"
    assert int(chosen["assignment_count"]) == 2
    assert chosen["annual_salary"] == 70_000
    schools = set(assignment.loc[assignment["school_year"] == 2024, "school_number"])
    assert schools == {"9999", "0"}
    assert set(assignment["aun"]) == {"101260303"}

    def refuse(path):
        raise AssertionError(f"opened {path}")

    monkeypatch.setattr("pa_edu.extract.read_workbook", refuse)
    monkeypatch.setattr(pd, "read_excel", refuse)
    refresh(data, sources)
    again = pd.read_parquet(data / "refined" / "professional_staff.parquet")
    assert set(again["school_year"]) == {2024, 2025}


def test_personnel_appends_a_year_and_updates_a_replaced_file(tmp_path, monkeypatch) -> None:
    early = tmp_path / "files" / "staff-2024.xlsx"
    _staff_book(early, 2024, 70_000)
    data = tmp_path / "data"
    refresh(data, [(2024, early.as_uri())])
    first_raw = [Path(record["path"]) for record in load_index(data)["documents"].values()]
    assert len(first_raw) == 1
    late = tmp_path / "files" / "staff-2025.xlsx"
    _staff_book(late, 2025, 80_000)
    opened: list[str] = []
    original = read_workbook

    def counting(path):
        opened.append(Path(path).name)
        return original(path)

    monkeypatch.setattr("pa_edu.extract.read_workbook", counting)
    refresh(data, [(2024, early.as_uri()), (2025, late.as_uri())])
    assert opened == [late.name]
    staff = pd.read_parquet(data / "refined" / "professional_staff.parquet")
    salaries = dict(zip(staff["school_year"], staff["annual_salary"], strict=True))
    assert salaries == {2024: 70_000, 2025: 80_000}
    assert first_raw[0].is_file()

    first_raw[0].unlink()
    _staff_book(early, 2024, 75_000)
    opened.clear()
    refresh(data, [(2024, early.as_uri()), (2025, late.as_uri())])
    assert opened == [early.name]
    staff = pd.read_parquet(data / "refined" / "professional_staff.parquet")
    salaries = dict(zip(staff["school_year"], staff["annual_salary"], strict=True))
    assert salaries == {2024: 75_000, 2025: 80_000}

