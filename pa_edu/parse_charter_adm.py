"""Resident students of a school district attending charter schools (ADM).

PDE’s ADM workbook gained a `CS ADM by SD` sheet in 2024–25: one row per
school district with average daily membership in charter schools. Earlier
workbooks only publish membership by charter school, which is a different
grain and is not this table.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from pa_edu.codes import as_amount, as_code, as_text, read_sheet, require_columns, sheet_names


def parse_charter_adm(path: Path, document: dict) -> dict[str, pd.DataFrame]:
    frame, columns, amount_column = _table(path)
    year = int(document["school_year"])
    document_id = document["document_id"]
    amounts = as_amount(frame[amount_column])
    rows: list[dict] = []
    for index, amount in amounts.items():
        if pd.isna(amount):
            continue
        aun = columns["aun"].at[index]
        if aun is None or pd.isna(aun):
            continue
        rows.append(
            {
                "aun": aun,
                "school_year": year,
                "lea_name": columns["lea_name"].at[index],
                "county": columns["county"].at[index],
                "adm": float(amount),
                "document_id": document_id,
            }
        )
    if not rows:
        raise ValueError(f"{path.name} has no charter ADM by school district")
    return {"charter_adm": pd.DataFrame(rows)}


def _table(path: Path) -> tuple[pd.DataFrame, dict[str, pd.Series], str]:
    last_error: Exception | None = None
    for name in sheet_names(path):
        if not _is_by_sd_sheet(name):
            continue
        frame = read_sheet(path, name)
        try:
            found = require_columns(frame, ["AUN", "School District", "County"], path, name)
        except ValueError as error:
            last_error = error
            continue
        amount = _amount_column(frame.columns)
        if amount is None:
            last_error = ValueError(f"{path.name} sheet {name} has no charter ADM column")
            continue
        return (
            frame,
            {
                "aun": as_code(frame[found["AUN"]], 9),
                "lea_name": frame[found["School District"]].map(as_text),
                "county": frame[found["County"]].map(as_text),
            },
            amount,
        )
    raise ValueError(last_error or f"{path.name} has no CS ADM by SD sheet")


def _is_by_sd_sheet(name: str) -> bool:
    folded = name.casefold()
    return "cs adm by sd" in folded or ("charter" in folded and "by sd" in folded)


def _amount_column(columns) -> str | None:
    found = [
        column
        for column in columns
        if "charter" in str(column).casefold() and "adm" in str(column).casefold()
    ]
    if len(found) != 1:
        return None
    return found[0]
