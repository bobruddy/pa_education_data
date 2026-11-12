"""Public-school October 1 economically disadvantaged (low-income) enrollment.

PDE publishes a separate “Percent Low Income” workbook on the enrollment page.
LEA sheets carry submitting AUN, total enrollment, low-income enrollment, and
the published low-income share. School sheets are a different grain and are not
this table.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from pa_edu.codes import as_amount, as_code, as_text, sheet_names


def parse_low_income(path: Path, document: dict) -> dict[str, pd.DataFrame]:
    frame = _lea_table(path)
    year = int(document["school_year"])
    document_id = document["document_id"]
    low = as_amount(frame["low_income_enrollment"])
    total = as_amount(frame["total_enrollment"])
    pct = as_amount(frame["pct_low_income"])
    rows: list[dict] = []
    seen: set[str] = set()
    for index, count in low.items():
        aun = frame["aun"].at[index]
        if aun is None or pd.isna(aun):
            continue
        aun = str(aun)
        if pd.isna(count):
            continue
        if aun in seen:
            raise ValueError(f"{path.name} repeats AUN {aun} on the LEA low-income sheet")
        seen.add(aun)
        total_count = total.at[index]
        pct_value = pct.at[index]
        rows.append(
            {
                "aun": aun,
                "school_year": year,
                "lea_name": frame["lea_name"].at[index],
                "lea_type": frame["lea_type"].at[index],
                "low_income_enrollment": int(round(float(count))),
                "total_enrollment": None if pd.isna(total_count) else int(round(float(total_count))),
                "pct_low_income": None if pd.isna(pct_value) else _as_percent(float(pct_value)),
                "document_id": document_id,
            }
        )
    if not rows:
        raise ValueError(f"{path.name} has no LEA low-income rows")
    return {"enrollment_low_income": pd.DataFrame(rows)}


def _lea_table(path: Path) -> pd.DataFrame:
    last_error: Exception | None = None
    for name in sheet_names(path):
        if not _is_lea_sheet(name):
            continue
        try:
            return _read_lea_sheet(path, name)
        except ValueError as error:
            last_error = error
            continue
    raise ValueError(last_error or f"{path.name} has no LEA low-income sheet")


def _is_lea_sheet(name: str) -> bool:
    folded = name.casefold()
    if "school" in folded:
        return False
    return "by lea" in folded or folded.endswith("lea") or "lea-2" in folded


def _read_lea_sheet(path: Path, sheet: str) -> pd.DataFrame:
    engine = "xlrd" if path.suffix.lower() == ".xls" else "openpyxl"
    raw = pd.read_excel(path, sheet_name=sheet, header=None, engine=engine)
    header_index = None
    for index, row in raw.iterrows():
        labels = [_label(value) for value in row.tolist()]
        if any(label in {"aun", "submitting aun"} for label in labels):
            header_index = int(index)
            break
    if header_index is None:
        raise ValueError(f"{path.name} sheet {sheet} has no AUN header")
    columns = [_label(value) or f"col_{position}" for position, value in enumerate(raw.iloc[header_index].tolist())]
    frame = raw.iloc[header_index + 1 :].copy()
    frame.columns = columns
    frame = frame.loc[:, ~pd.Index(frame.columns).duplicated()].copy()
    aun_column = _column(frame, {"aun", "submitting aun"})
    name_column = _column(frame, {"lea", "lea name"})
    type_column = _column(frame, {"lea type"})
    total_column = _column(frame, {"total enrollment"})
    low_column = _column(frame, {"low income enrollment", "low-income enrollment"})
    pct_column = _column(
        frame,
        {
            "percent of enrollment from low income families",
            "percent of enrollment from low-income families",
        },
        contains=("percent", "low"),
    )
    if aun_column is None or low_column is None:
        raise ValueError(f"{path.name} sheet {sheet} missing AUN or low-income enrollment")
    out = pd.DataFrame(
        {
            "aun": as_code(frame[aun_column], 9),
            "lea_name": frame[name_column].map(as_text) if name_column else pd.NA,
            "lea_type": frame[type_column].map(as_text) if type_column else pd.NA,
            "total_enrollment": frame[total_column] if total_column else pd.NA,
            "low_income_enrollment": frame[low_column],
            "pct_low_income": frame[pct_column] if pct_column else pd.NA,
        }
    )
    return out.loc[out["aun"].notna()].reset_index(drop=True)


def _column(
    frame: pd.DataFrame,
    exact: set[str],
    contains: tuple[str, ...] | None = None,
) -> str | None:
    for column in frame.columns:
        label = str(column).casefold().strip()
        if label in exact:
            return column
    if contains:
        found = [
            column
            for column in frame.columns
            if all(token in str(column).casefold() for token in contains)
        ]
        if len(found) == 1:
            return found[0]
    return None


def _label(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).replace("\xa0", " ").strip().casefold()


def _as_percent(value: float) -> float:
    """Workbook cells are usually a fraction (0.0712); normalize to 0–100."""
    if 0 <= value <= 1:
        return round(value * 100, 4)
    return float(value)
