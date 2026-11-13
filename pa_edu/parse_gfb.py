"""General Fund Budget workbooks at the finest published grain."""

from __future__ import annotations

import re
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
    sheet_names,
    sheets_starting,
)

ID_COLUMNS = ["InstCat", "AUN", "InstName", "CountyName"]
# Beginning fund balance sits on the revenue sheet. It is not revenue.
FUND_BALANCE_COLUMNS = {"0810", "0820", "0830", "0840", "0850"}
REVENUE_CODE = re.compile(r"^[6-9]\d{3}$")


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
    return {
        "gfb_expenditure": amounts,
        "gfb_revenue": _revenue(path, year, document_id),
        "lea_year": names,
    }


def revenue_budget_sheet(path: Path) -> str:
    """The general-fund revenue sheet. The name moves; the role does not.

    Rev_OtherTax, IURev_Prog, and JREV_* are other grains and are not this sheet.
    """
    hits = []
    for name in sheet_names(path):
        folded = re.sub(r"[^a-z0-9]", "", name.casefold())
        if "rev" not in folded or "othertax" in folded:
            continue
        if folded.startswith("iu") or folded.startswith("jrev"):
            continue
        if "beg" in folded or "fundbal" in folded:
            hits.append(name)
    if len(hits) != 1:
        raise ValueError(f"{path.name} revenue budget sheet is {hits or 'missing'}")
    return hits[0]


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


def _revenue(path: Path, year: int, document_id: str) -> pd.DataFrame:
    sheet = revenue_budget_sheet(path)
    frame = read_sheet(path, sheet)
    columns = require_columns(frame, ID_COLUMNS, path, sheet)
    id_columns = set(columns.values())
    value_columns: list[tuple[object, str]] = []
    seen: set[str] = set()
    for header in frame.columns:
        if header in id_columns:
            continue
        token = as_text(header) or ""
        if token in FUND_BALANCE_COLUMNS:
            continue
        if REVENUE_CODE.fullmatch(token) is None:
            raise ValueError(f"{path.name} sheet {sheet} has unknown column {header!r}")
        if token in seen:
            raise ValueError(f"{path.name} sheet {sheet} repeats revenue column {token}")
        seen.add(token)
        value_columns.append((header, token))
    rows: list[dict] = []
    auns = as_code(frame[columns["AUN"]], 9)
    for header, token in value_columns:
        values = as_amount(frame[header])
        for index, amount in values.items():
            if pd.isna(amount):
                continue
            aun = auns.at[index]
            if aun is None or pd.isna(aun):
                continue
            rows.append(
                {
                    "aun": aun,
                    "school_year": year,
                    "account_code": token,
                    "amount": float(amount),
                    "fund_code": "10",
                    "document_id": document_id,
                }
            )
    out_columns = ["aun", "school_year", "account_code", "amount", "fund_code", "document_id"]
    if not rows:
        return pd.DataFrame(columns=out_columns)
    return pd.DataFrame(rows, columns=out_columns)


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
