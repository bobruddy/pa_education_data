from pathlib import Path

import duckdb
import pandas as pd

from pa_edu.personnel import staff_rows, write_personnel_tables
from pa_edu.refine import COLUMNS, _ensure_personnel


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
