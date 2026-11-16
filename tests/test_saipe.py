"""SAIPE and CCD fixtures. They are not the Census files."""

import zipfile
from pathlib import Path

import pandas as pd
import pytest

from pa_edu.check import _population_districts, _saipe_cell
from pa_edu.parse_nces import parse_nces
from pa_edu.parse_saipe import parse_saipe
from pa_edu.refine import _district_population


def _line(length: int, fields: list[tuple]) -> str:
    chars = [" "] * length
    for start, end, text, align in fields:
        raw = "" if text is None else str(text)
        width = end - start + 1
        if len(raw) > width:
            raise AssertionError(raw)
        field = raw.rjust(width) if align == "right" else raw.ljust(width)
        chars[start - 1:end] = list(field)
    line = "".join(chars)
    assert len(line) == length
    return line


def _gallatin_2024() -> str:
    return _line(131, [
        (1, 2, "42", "left"),
        (4, 8, "02100", "left"),
        (10, 81, "Albert Gallatin Area SD", "left"),
        (83, 90, "21768", "right"),
        (92, 99, "0", "right"),
        (101, 108, None, "right"),
        (110, 130, "sd24-pa.txt", "left"),
    ])


def _center_2008() -> str:
    return _line(124, [
        (1, 2, "42", "left"),
        (4, 8, "05210", "left"),
        (10, 74, "CENTER AREA SCHOOL DISTRICT", "left"),
        (76, 83, "11703", "right"),
        (85, 92, "1824", "right"),
        (94, 101, "115", "right"),
        (103, 123, "sd08_PA.txt", "left"),
    ])


def _ccd(path: Path) -> None:
    text = "\n".join([
        "LEAID\tFIPST\tSTID09\tNAME09\tTYPE09",
        "4202100\t42\t101260303\tALBERT GALLATIN AREA SD\t1",
        "4205210\t42\t127041903\tCENTER AREA SD\t1",
        "4200001\t42\t123456789\tSOME CHARTER SCHOOL\t7",
        "3900001\t39\t000000001\tOHIO SD\t1",
        "",
    ])
    path.write_text(text, encoding="ascii")


def test_saipe_keeps_a_zero_and_takes_the_catalog_year(tmp_path: Path) -> None:
    path = tmp_path / "sd24-pa.txt"
    path.write_text(_gallatin_2024() + "\n", encoding="ascii")
    row = parse_saipe(path, {"school_year": 2024, "document_id": "saipe-2024"})["saipe_district"].iloc[0]
    assert row["nces_leaid"] == "4202100"
    assert int(row["school_year"]) == 2024
    assert row["document_id"] == "saipe-2024"
    assert row["census_name"] == "Albert Gallatin Area SD"
    assert int(row["total_population"]) == 21768
    assert int(row["population_5_17"]) == 0
    assert pd.isna(row["children_5_17_in_poverty"])


def test_saipe_reads_the_2008_layout(tmp_path: Path) -> None:
    path = tmp_path / "sd08-pa.txt"
    path.write_text(_center_2008() + "\n", encoding="ascii")
    row = parse_saipe(path, {"school_year": 2008, "document_id": "saipe-2008"})["saipe_district"].iloc[0]
    assert row["nces_leaid"] == "4205210"
    assert int(row["school_year"]) == 2008
    assert row["document_id"] == "saipe-2008"
    assert row["census_name"] == "CENTER AREA SCHOOL DISTRICT"
    assert int(row["total_population"]) == 11703
    assert int(row["population_5_17"]) == 1824
    assert int(row["children_5_17_in_poverty"]) == 115


def test_saipe_rejects_a_short_record(tmp_path: Path) -> None:
    path = tmp_path / "sd24-pa.txt"
    path.write_text("42 02100 too short\n", encoding="ascii")
    with pytest.raises(ValueError, match="record length"):
        parse_saipe(path, {"school_year": 2024, "document_id": "saipe-2024"})


def test_saipe_rejects_a_tag_for_another_year(tmp_path: Path) -> None:
    line = _line(131, [
        (1, 2, "42", "left"),
        (4, 8, "02100", "left"),
        (10, 81, "Albert Gallatin Area SD", "left"),
        (83, 90, "21768", "right"),
        (92, 99, "3351", "right"),
        (101, 108, "532", "right"),
        (110, 130, "sd23-pa.txt", "left"),
    ])
    path = tmp_path / "sd24-pa.txt"
    path.write_text(line + "\n", encoding="ascii")
    with pytest.raises(ValueError, match="does not match catalog year"):
        parse_saipe(path, {"school_year": 2024, "document_id": "saipe-2024"})


def test_nces_aun_stays_nine_digit_text(tmp_path: Path) -> None:
    text_path = tmp_path / "ag091a.txt"
    _ccd(text_path)
    archive = tmp_path / "ag091a_txt.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.write(text_path, "ag091a.txt")
    document = {"document_id": "nces-2009"}
    direct = parse_nces(text_path, document)["nces_district"]
    packed = parse_nces(archive, document)["nces_district"]
    assert list(packed["nces_leaid"]) == list(direct["nces_leaid"]) == ["4202100", "4205210"]
    assert list(direct["aun"]) == ["101260303", "127041903"]
    assert direct["aun"].dtype == "string"
    assert direct.iloc[0]["aun"] == "101260303"
    assert direct.iloc[0]["document_id"] == "nces-2009"
    assert "4200001" not in set(direct["nces_leaid"])
    assert "3900001" not in set(direct["nces_leaid"])


def test_join_keeps_the_saipe_document_and_fails_without_a_ccd_row(tmp_path: Path) -> None:
    saipe_path = tmp_path / "sd24-pa.txt"
    saipe_path.write_text(_gallatin_2024() + "\n", encoding="ascii")
    ccd_path = tmp_path / "ccd.txt"
    _ccd(ccd_path)
    saipe = parse_saipe(saipe_path, {"school_year": 2024, "document_id": "saipe-2024"})["saipe_district"]
    crosswalk = parse_nces(ccd_path, {"document_id": "nces-2009"})["nces_district"]
    joined = _district_population([saipe], crosswalk)
    row = joined.iloc[0]
    assert row["aun"] == "101260303"
    assert joined["aun"].dtype == "string"
    assert int(row["school_year"]) == 2024
    assert row["document_id"] == "saipe-2024"
    assert int(row["population_5_17"]) == 0

    missing = saipe.copy()
    missing["nces_leaid"] = "4299999"
    with pytest.raises(RuntimeError, match="no CCD row"):
        _district_population([missing], crosswalk)

    duplicated = pd.concat([crosswalk, crosswalk], ignore_index=True)
    with pytest.raises(RuntimeError, match="more than one CCD row"):
        _district_population([saipe], duplicated)


def test_refine_joins_saipe_to_the_ccd_aun(tmp_path: Path) -> None:
    saipe = tmp_path / "sd24-pa.txt"
    saipe.write_text(_gallatin_2024() + "\n", encoding="ascii")
    ccd = tmp_path / "ccd.txt"
    _ccd(ccd)
    catalog = tmp_path / "catalog.toml"
    catalog.write_text(
        "\n".join([
            "[[document]]",
            'id = "saipe-2024"',
            'source_id = "saipe"',
            f'source_url = "{saipe.as_uri()}"',
            f'page_url = "{saipe.as_uri()}"',
            'parser = "saipe"',
            'status = "stable"',
            "school_year = 2024",
            "",
            "[[document]]",
            'id = "nces-2009"',
            'source_id = "nces"',
            f'source_url = "{ccd.as_uri()}"',
            f'page_url = "{ccd.as_uri()}"',
            'parser = "nces"',
            'status = "stable"',
            "school_year = 2009",
            "",
        ]),
        encoding="utf-8",
    )
    from pa_edu.refine import run

    refined = run(tmp_path / "data", catalog)
    frame = pd.read_parquet(refined / "district_population.parquet")
    row = frame.iloc[0]
    assert row["aun"] == "101260303"
    assert int(row["school_year"]) == 2024
    assert str(row["document_id"]).startswith("saipe-2024-")
    assert int(row["population_5_17"]) == 0
    crosswalk = pd.read_parquet(refined / "nces_district.parquet")
    assert list(crosswalk["aun"]) == ["101260303", "127041903"]


def test_population_check_rejects_a_non_district() -> None:
    tables = {
        "lea": pd.DataFrame([{"aun": "101260303", "category": "charter_school"}]),
        "district_population": pd.DataFrame([{"aun": "101260303", "school_year": 2024}]),
    }
    errors = _population_districts(tables)
    assert errors and "101260303" in errors[0]


def test_saipe_cell_rereads_the_file(tmp_path: Path) -> None:
    path = tmp_path / "sd08-pa.txt"
    path.write_text(_center_2008() + "\n", encoding="ascii")
    index = {
        "current": {"saipe-2008": "doc-1"},
        "documents": {
            "doc-1": {
                "parser": "saipe",
                "status": "stable",
                "school_year": 2008,
                "catalog_id": "saipe-2008",
                "path": str(path),
            }
        },
    }
    cell = {"school_year": 2008, "aun": "127041903", "nces_leaid": "4205210"}
    tables = {
        "district_population": pd.DataFrame([{
            "aun": "127041903",
            "school_year": 2008,
            "nces_leaid": "4205210",
            "total_population": 11703,
            "population_5_17": 1824,
            "children_5_17_in_poverty": 115,
        }])
    }
    assert _saipe_cell(tables, index, cell) == []
    tables["district_population"].loc[0, "total_population"] = 1
    errors = _saipe_cell(tables, index, cell)
    assert errors and "11703" in errors[0]
