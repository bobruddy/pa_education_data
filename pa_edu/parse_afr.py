"""Annual Financial Report expenditures and revenue.

EXP is the expenditure ledger, including the building split when PDE published
one. REV is revenue. There is no building-level revenue sheet.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from pa_edu.codes import as_amount, as_code, as_text, find_sheet, read_sheet, sheets_starting

AMOUNT_COLUMNS = {
    "ElementaryAmount": "elementary_amount",
    "SecondaryAmount": "secondary_amount",
    "FederalAmount": "federal_amount",
    "TotalAmount": "total_amount",
}
CODE_COLUMNS = {
    "FundCode": "fund_code",
    "RollupFundCode": "rollup_fund_code",
    "AccountCode": "function_code",
    "Rollup1AccountCode": "rollup1_account_code",
    "Rollup2AccountCode": "rollup2_account_code",
    "Rollup3AccountCode": "rollup3_account_code",
    "ObjectCode": "object_code",
    "Rollup1ObjectCode": "rollup1_object_code",
    "Rollup2ObjectCode": "rollup2_object_code",
    "ProgramCode": "program_code",
}


def parse_afr(path: Path, document: dict) -> dict[str, pd.DataFrame]:
    year = int(document["school_year"])
    document_id = document["document_id"]
    sheet = find_sheet(path, "EXP")
    raw = read_sheet(path, sheet)
    expense = _normalize(raw, path, sheet, year, document_id, school=False)
    school_frames = []
    for name in sheets_starting(path, "SLFS_EXP"):
        school_frames.append(
            _normalize(read_sheet(path, name), path, name, year, document_id, school=True)
        )
    school = (
        pd.concat(school_frames, ignore_index=True)
        if school_frames
        else pd.DataFrame(columns=["school_number", "school_name", *expense.columns])
    )
    school = _collapse_school(school)
    school = _drop_redundant_leaw(school, expense)
    return {
        "afr_expenditure": expense,
        "afr_expenditure_school": school,
        "afr_revenue": _revenue(path, year, document_id),
        "lea_year": _names(raw, year, document_id),
    }


def _normalize(
    frame: pd.DataFrame,
    path: Path,
    sheet: str,
    year: int,
    document_id: str,
    school: bool,
) -> pd.DataFrame:
    found = {str(column).strip().casefold(): column for column in frame.columns}
    required = ["InstCat", "AUN", "InstName", "CountyName", *CODE_COLUMNS, *AMOUNT_COLUMNS]
    if school:
        required = [name for name in required if name != "ProgramCode"]
        required.extend(["SchoolName", "BranchNumber"])
    missing = [name for name in required if name.casefold() not in found]
    if missing:
        raise ValueError(f"{path.name} sheet {sheet} missing {missing}")

    def source(name: str) -> pd.Series:
        return frame[found[name.casefold()]]

    output = pd.DataFrame(
        {
            "aun": as_code(source("AUN"), 9),
            "school_year": year,
            "inst_cat": as_code(source("InstCat"), 2),
            "lea_name": source("InstName").map(_name),
            "county": source("CountyName").map(_name),
            "document_id": document_id,
        }
    )
    for original, renamed in CODE_COLUMNS.items():
        width = 4 if "Account" in original else None
        if original.casefold() not in found:
            output[renamed] = ""
            continue
        output[renamed] = as_code(source(original), width)
    output["fund_code"] = as_code(source("FundCode"))
    output["program_code"] = output["program_code"].fillna("").astype("string")
    output.loc[output["program_code"].isna(), "program_code"] = ""
    for original, renamed in AMOUNT_COLUMNS.items():
        output[renamed] = as_amount(source(original))
    if school:
        output["school_name"] = source("SchoolName").map(_name)
        output["school_number"] = as_code(source("BranchNumber"))
    output = output.dropna(subset=["aun", "function_code", "object_code"])
    keep = [
        "aun",
        "school_year",
        "fund_code",
        "function_code",
        "object_code",
        "program_code",
        "rollup_fund_code",
        "rollup1_account_code",
        "rollup2_account_code",
        "rollup3_account_code",
        "rollup1_object_code",
        "rollup2_object_code",
        "elementary_amount",
        "secondary_amount",
        "federal_amount",
        "total_amount",
        "document_id",
    ]
    if school:
        keep[2:2] = ["school_number", "school_name"]
    return output.loc[:, keep]


SCHOOL_KEYS = [
    "aun",
    "school_number",
    "school_year",
    "fund_code",
    "function_code",
    "object_code",
    "program_code",
]
ACCOUNT_KEYS = ["aun", "school_year", "fund_code", "function_code", "object_code", "program_code"]
AMOUNT_FIELDS = ["elementary_amount", "secondary_amount", "federal_amount", "total_amount"]


def _collapse_school(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or not frame.duplicated(SCHOOL_KEYS).any():
        return frame
    others = [column for column in frame.columns if column not in SCHOOL_KEYS and column not in AMOUNT_FIELDS]
    return frame.groupby(SCHOOL_KEYS, dropna=False, as_index=False).agg(
        {**{column: "first" for column in others}, **{column: "sum" for column in AMOUNT_FIELDS}}
    )


def _drop_redundant_leaw(school: pd.DataFrame, expense: pd.DataFrame) -> pd.DataFrame:
    """Drop LEA-wide rows when the named buildings already equal the EXP amount.

    LEAW is the unallocated remainder. When the buildings already account for the
    whole EXP line, a LEAW row on that line is a second copy, not more spending.
    """
    if school.empty or expense.empty or "school_number" not in school.columns:
        return school
    leaw = school["school_number"].astype("string") == "LEAW"
    if not leaw.any():
        return school
    buildings = school.loc[~leaw].groupby(ACCOUNT_KEYS, dropna=False)["total_amount"].sum()
    lea = expense.groupby(ACCOUNT_KEYS, dropna=False)["total_amount"].sum()
    compared = buildings.to_frame("school").join(lea.rename("lea"), how="inner")
    matched = compared.loc[(compared["school"] - compared["lea"]).abs() <= 0.01]
    if matched.empty:
        return school
    keys = pd.MultiIndex.from_frame(school.loc[:, ACCOUNT_KEYS])
    drop = leaw.to_numpy() & keys.isin(matched.index)
    return school.loc[~drop].copy()


REVENUE_COLUMNS = [
    "InstCat",
    "AUN",
    "InstName",
    "CountyName",
    "FundCode",
    "RollupFundCode",
    "AccountCode",
    "Rollup1AccountCode",
    "Rollup2AccountCode",
    "Rollup3AccountCode",
    "ProgramCode",
    "Amount1",
    "Amount2",
    "Amount3",
    "TotalAmount",
]


def reported_revenue(amount_1: pd.Series, total: pd.Series) -> pd.Series:
    """The revenue figure PDE published for the account.

    Where TotalAmount is filled, it equals Amount1 − Amount2 + Amount3. That
    is the chart's net tax: face, less discounts, plus interest and penalties.
    Amount2 and Amount3 show up on current and delinquent tax accounts. Most
    other rows fill only Amount1 and leave TotalAmount blank. Use TotalAmount
    when PDE filled it; otherwise use Amount1. Do not add the two together.
    """
    return total.where(total.notna(), amount_1)


def _revenue(path: Path, year: int, document_id: str) -> pd.DataFrame:
    sheet = find_sheet(path, "REV")
    frame = read_sheet(path, sheet)
    found = {str(column).strip().casefold(): column for column in frame.columns}
    required = {name.casefold() for name in REVENUE_COLUMNS}
    missing = [name for name in REVENUE_COLUMNS if name.casefold() not in found]
    extra = [str(column) for column in frame.columns if str(column).strip().casefold() not in required]
    if missing or extra:
        raise ValueError(f"{path.name} sheet {sheet} missing {missing} unexpected {extra}")

    def source(name: str) -> pd.Series:
        return frame[found[name.casefold()]]

    amount_1 = as_amount(source("Amount1"))
    amount_2 = as_amount(source("Amount2"))
    amount_3 = as_amount(source("Amount3"))
    total = as_amount(source("TotalAmount"))
    output = pd.DataFrame(
        {
            "aun": as_code(source("AUN"), 9),
            "school_year": year,
            "fund_code": as_code(source("FundCode")),
            "account_code": as_code(source("AccountCode"), 4),
            "program_code": as_code(source("ProgramCode")).fillna(""),
            "rollup_fund_code": as_code(source("RollupFundCode")),
            "rollup1_account_code": as_code(source("Rollup1AccountCode"), 4),
            "rollup2_account_code": as_code(source("Rollup2AccountCode"), 4),
            "rollup3_account_code": as_code(source("Rollup3AccountCode"), 4),
            "amount_1": amount_1,
            "amount_2": amount_2,
            "amount_3": amount_3,
            "total_amount": total,
            "amount": reported_revenue(amount_1, total),
            "document_id": document_id,
        }
    )
    output["program_code"] = output["program_code"].fillna("").astype("string")
    output = output.dropna(subset=["aun", "fund_code", "account_code"])
    output = output.loc[output["amount"].notna()].copy()
    bad = sorted(output.loc[~output["account_code"].str.fullmatch(r"\d{4}"), "account_code"].dropna().unique())
    if bad:
        raise ValueError(f"{path.name} sheet {sheet} has account codes {bad[:8]}")
    keep = [
        "aun",
        "school_year",
        "fund_code",
        "account_code",
        "program_code",
        "rollup_fund_code",
        "rollup1_account_code",
        "rollup2_account_code",
        "rollup3_account_code",
        "amount_1",
        "amount_2",
        "amount_3",
        "total_amount",
        "amount",
        "document_id",
    ]
    return output.loc[:, keep]


def _names(frame: pd.DataFrame, year: int, document_id: str) -> pd.DataFrame:
    found = {str(column).strip().casefold(): column for column in frame.columns}
    names = pd.DataFrame(
        {
            "aun": as_code(frame[found["aun"]], 9),
            "school_year": year,
            "lea_name": frame[found["instname"]].map(_name),
            "county": frame[found["countyname"]].map(_name),
            "inst_cat": as_code(frame[found["instcat"]], 2),
            "document_id": document_id,
        }
    )
    return names.dropna(subset=["aun"]).drop_duplicates(["aun", "school_year", "document_id"])


def _name(value: object) -> object:
    text = as_text(value)
    return text if text is not None else pd.NA
