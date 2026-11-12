"""General Fund Budget workbooks at the finest published grain."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from pa_edu.codes import (
    ACCOUNT_RE,
    as_amount,
    as_code,
    as_text,
    find_sheet,
    read_sheet,
    require_columns,
    sheets_starting,
)

ID_COLUMNS = ["InstCat", "AUN", "InstName", "CountyName"]


def parse_gfb(path: Path, document: dict) -> dict[str, pd.DataFrame]:
    year = int(document["school_year"])
    document_id = document["document_id"]
    expense_sheet = find_sheet(path, "Exp") if _has(path, "Exp") else find_sheet(path, "ExpDetail")
    expense = read_sheet(path, expense_sheet)
    program_name = _program_sheet(path)
    program = read_sheet(path, program_name) if program_name else None
    if program is not None:
        expense = expense.loc[as_code(expense_column(expense, "InstCat"), 2) != "02"].copy()
    frames = [_melt(expense, year, document_id, with_program=False)]
    if program is not None:
        frames.append(_melt(program, year, document_id, with_program=True))
    amounts = pd.concat(frames, ignore_index=True)
    names = _names(expense if program is None else pd.concat([expense, program], ignore_index=True), year, document_id)
    return {"gfb_expenditure": amounts, "lea_year": names}


def _has(path: Path, name: str) -> bool:
    try:
        find_sheet(path, name)
    except ValueError:
        return False
    return True


def _program_sheet(path: Path) -> str | None:
    found = sheets_starting(path, "IUExp_Prog")
    return found[0] if found else None


def expense_column(frame: pd.DataFrame, name: str) -> pd.Series:
    found = {str(column).strip().casefold(): column for column in frame.columns}
    return frame[found[name.casefold()]]


def _melt(frame: pd.DataFrame, year: int, document_id: str, with_program: bool) -> pd.DataFrame:
    columns = require_columns(frame, ID_COLUMNS, Path(document_id), "budget")
    rows: list[dict] = []
    id_frame = pd.DataFrame(
        {
            "aun": as_code(frame[columns["AUN"]], 9),
            "inst_cat": as_code(frame[columns["InstCat"]], 2),
        }
    )
    for header in frame.columns:
        match = ACCOUNT_RE.fullmatch(str(header).strip())
        if match is None:
            continue
        if bool(match.group(3)) != with_program:
            continue
        values = as_amount(frame[header])
        for index, amount in values.items():
            if pd.isna(amount):
                continue
            aun = id_frame.at[index, "aun"]
            if aun is None or pd.isna(aun):
                continue
            rows.append(
                {
                    "aun": aun,
                    "school_year": year,
                    "function_code": match.group(1),
                    "object_code": match.group(2),
                    "program_code": match.group(3) or "",
                    "amount": float(amount),
                    "fund_code": "10",
                    "document_id": document_id,
                }
            )
    columns = [
        "aun",
        "school_year",
        "function_code",
        "object_code",
        "program_code",
        "amount",
        "fund_code",
        "document_id",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows, columns=columns)


def _names(frame: pd.DataFrame, year: int, document_id: str) -> pd.DataFrame:
    columns = require_columns(frame, ID_COLUMNS, Path("gfb"), "budget")
    names = pd.DataFrame(
        {
            "aun": as_code(frame[columns["AUN"]], 9),
            "school_year": year,
            "lea_name": frame[columns["InstName"]].map(_clean_name),
            "county": frame[columns["CountyName"]].map(_clean_name),
            "inst_cat": as_code(frame[columns["InstCat"]], 2),
            "document_id": document_id,
        }
    )
    names = names.dropna(subset=["aun"])
    return names.drop_duplicates(["aun", "school_year", "document_id"])


def _clean_name(value: object) -> object:
    text = as_text(value)
    return text if text is not None else pd.NA
