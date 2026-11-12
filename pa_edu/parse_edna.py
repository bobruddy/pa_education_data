"""EdNA public-entity extract, one row per administrative unit number."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from pa_edu.codes import as_code, as_text, read_sheet

CATEGORIES = {
    "career and technical center": "career_and_technical_center",
    "charter school": "charter_school",
    "intermediate unit": "intermediate_unit",
    "school district": "school_district",
    "special program jointure": "jointure",
    "state juvenile correctional inst": "state_juvenile_correctional",
}


def parse_edna(path: Path, document: dict) -> dict[str, pd.DataFrame]:
    frame = read_sheet(path, 0)
    found = {str(column).strip().casefold(): column for column in frame.columns}
    required = ["aunumber", "instname", "category", "countyname", "statusdescription"]
    missing = [name for name in required if name not in found]
    if missing:
        raise ValueError(f"{path.name} missing {missing}")
    lea = pd.DataFrame(
        {
            "aun": as_code(frame[found["aunumber"]], 9),
            "lea_name": frame[found["instname"]].map(_text),
            "category_label": frame[found["category"]].map(_text),
            "county": frame[found["countyname"]].map(_text),
            "status_label": frame[found["statusdescription"]].map(_text),
            "iu_number": as_code(frame[found["iunumber"]]) if "iunumber" in found else pd.NA,
        }
    )
    lea = lea.loc[lea["aun"].str.fullmatch(r"\d{9}", na=False)].copy()
    lea["category"] = lea["category_label"].map(_category)
    lea = lea.loc[lea["category"].notna()].copy()
    lea["status"] = lea["status_label"].map(_status)
    lea["rank"] = lea["status"].map({"open": 0, "closed": 1, "unknown": 2})
    lea = lea.sort_values(["aun", "rank"]).drop_duplicates("aun", keep="first")
    lea["iu_aun"] = lea["iu_number"].map(_iu_aun)
    lea["in_directory"] = True
    lea["document_id"] = document["document_id"]
    columns = ["aun", "lea_name", "category", "status", "county", "iu_aun", "in_directory", "document_id"]
    return {"lea": lea.loc[:, columns]}


def _category(value: object) -> object:
    text = as_text(value)
    if text is None:
        return pd.NA
    return CATEGORIES.get(text.casefold(), pd.NA)


def _status(value: object) -> str:
    text = (as_text(value) or "").casefold()
    if text == "open":
        return "open"
    if text == "closed":
        return "closed"
    return "unknown"


def _iu_aun(value: object) -> object:
    text = as_text(value)
    if text is None or not text.isdigit():
        return pd.NA
    return f"1{int(text):02d}000000"


def _text(value: object) -> object:
    text = as_text(value)
    return text if text is not None else pd.NA
