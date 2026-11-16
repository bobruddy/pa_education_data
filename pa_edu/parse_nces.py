"""NCES CCD directory rows that crosswalk a SAIPE district id to an AUN.

The pinned file is the 2009–10 CCD universe (``ag091a.txt``). Later directories
that use ``ST_LEAID`` have dropped Center Area and Monaca. This file still has
them. ``STID09`` is the nine-digit AUN, the same digits a later file writes
after ``PA-``. Regular Pennsylvania districts are kept, including closed ones.
Charters and other agency types are left out. A bad id fails the file.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd

from pa_edu.codes import as_code

COLUMNS = ["LEAID", "FIPST", "STID09", "NAME09", "TYPE09"]


def parse_nces(path: Path, document: dict) -> dict[str, pd.DataFrame]:
    frame = _table(path)
    missing = [name for name in COLUMNS if name not in frame.columns]
    if missing:
        raise ValueError(f"{path.name} missing {missing}")
    work = frame.loc[:, COLUMNS].map(lambda value: str(value).strip())
    kept = work.loc[(work["FIPST"] == "42") & (work["TYPE09"] == "1")].copy()
    if kept.empty:
        raise ValueError(f"{path.name} has no Pennsylvania regular school districts")
    bad_leaid = kept.loc[~kept["LEAID"].str.fullmatch(r"\d{7}"), "LEAID"].head(8).tolist()
    if bad_leaid:
        raise ValueError(f"{path.name} LEAID is not seven digits: {bad_leaid}")
    bad_aun = kept.loc[~kept["STID09"].str.fullmatch(r"\d{9}"), "STID09"].head(8).tolist()
    if bad_aun:
        raise ValueError(f"{path.name} state id is not a nine-digit AUN: {bad_aun}")
    districts = pd.DataFrame(
        {
            "nces_leaid": as_code(kept["LEAID"], 7),
            "aun": as_code(kept["STID09"], 9),
            "ccd_name": kept["NAME09"].astype("string"),
            "document_id": document["document_id"],
        }
    )
    duplicated = districts.loc[districts["nces_leaid"].duplicated(keep=False), "nces_leaid"]
    if not duplicated.empty:
        ids = sorted(set(duplicated.astype(str)))[:8]
        raise ValueError(f"{path.name} has more than one row for {ids}")
    districts["document_id"] = districts["document_id"].astype("string")
    return {"nces_district": districts.reset_index(drop=True)}


def _table(path: Path) -> pd.DataFrame:
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            names = [
                name for name in archive.namelist()
                if name.lower().endswith((".txt", ".csv")) and not name.endswith("/")
            ]
            if len(names) != 1:
                raise ValueError(f"{path.name} has {len(names)} text members")
            source = io.BytesIO(archive.read(names[0]))
    else:
        source = path
    frame = pd.read_csv(source, sep="\t", dtype=str, keep_default_na=False, encoding="latin-1")
    frame.columns = [str(column).strip() for column in frame.columns]
    return frame
