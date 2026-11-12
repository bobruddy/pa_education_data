"""Expense figures for the Dash app.

District totals include charter tuition. Per-pupil cost removes it, because
those students are in the charter's enrollment, not the district's. Tuition
paid to approved private schools and PRRIs stays in the per-pupil figure:
those students are still in the district count.
"""

from __future__ import annotations

import sqlite3

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from pa_edu.common import DB_PATH

LEA_TYPES = ("SD", "CS", "Cyber CS")
MEASURE_TOTAL = "total"
MEASURE_PER_PUPIL = "per_pupil"


def connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"missing {DB_PATH}; run python -m pa_edu.load")
    return sqlite3.connect(DB_PATH)


def counties() -> list[str]:
    with connect() as connection:
        rows = connection.execute(
            "select county from lea_info where county is not null group by county order by county"
        ).fetchall()
    return [row[0] for row in rows]


def years() -> list[int]:
    with connect() as connection:
        rows = connection.execute(
            """
            select e.school_year
            from finance_expense e
            inner join lea_w_enrollment le
                on e.aun = le.aun and e.school_year = le.school_year
            group by e.school_year
            order by e.school_year
            """
        ).fetchall()
    return [int(row[0]) for row in rows]


def tuition_years() -> list[int]:
    with connect() as connection:
        found = connection.execute(
            "select name from sqlite_master where type='table' and name='tuition_paid'"
        ).fetchone()
        if found is None:
            return []
        rows = connection.execute(
            "select distinct school_year from tuition_paid order by school_year"
        ).fetchall()
    return [int(row[0]) for row in rows]


def leas(county: str, school_year: int) -> list[str]:
    placeholders = ",".join("?" for _ in LEA_TYPES)
    with connect() as connection:
        rows = connection.execute(
            f"""
            select l.lea_name
            from lea_info l
            inner join lea_w_enrollment e on l.aun = e.aun
            where l.county = ?
              and e.school_year = ?
              and l.lea_type in ({placeholders})
            group by l.lea_name
            order by l.lea_name
            """,
            (county, school_year, *LEA_TYPES),
        ).fetchall()
    return [row[0] for row in rows]


def expense_frame(county: str, lea_names: list[str], school_year: int) -> pd.DataFrame:
    if not lea_names:
        return pd.DataFrame()
    type_marks = ",".join("?" for _ in LEA_TYPES)
    name_marks = ",".join("?" for _ in lea_names)
    sql = f"""
        select l.aun,
               l.lea_name,
               l.lea_type,
               l.county,
               e.expense_category,
               e.school_year,
               e.expense_value,
               le.enrollment,
               e.expense_category_name_0,
               e.expense_category_name_1,
               e.expense_category_name_2,
               coalesce(t.charter_nonspecial, 0) as charter_nonspecial,
               coalesce(t.charter_special, 0) as charter_special,
               coalesce(t.sped_aps, 0) as sped_aps,
               coalesce(t.sped_prri, 0) as sped_prri,
               case when t.aun is null then 0 else 1 end as has_tuition_row
        from lea_info l
        inner join finance_expense e
            on l.aun = e.aun and e.school_year = ?
        inner join lea_w_enrollment le
            on e.aun = le.aun and e.school_year = le.school_year
        left join tuition_paid t
            on t.aun = l.aun and t.school_year = e.school_year
        where l.county = ?
          and l.lea_name in ({name_marks})
          and l.lea_type in ({type_marks})
          and le.enrollment > 0
          and e.expense_value > 0
    """
    params: list[object] = [school_year, county, *lea_names, *LEA_TYPES]
    with connect() as connection:
        return pd.read_sql(sql, connection, params=params)


def apply_measure(frame: pd.DataFrame, measure: str) -> pd.DataFrame:
    """Return a copy with amount_used and slice_value for the chosen measure."""
    if frame.empty:
        return frame
    out = frame.copy()
    out["charter_removed"] = 0.0
    out["amount_used"] = out["expense_value"].astype(float)
    if measure == MEASURE_PER_PUPIL:
        for aun, indexes in out.groupby("aun").groups.items():
            rows = out.loc[indexes]
            if rows["lea_type"].iloc[0] != "SD":
                continue
            nonspecial = float(rows["charter_nonspecial"].iloc[0])
            special = float(rows["charter_special"].iloc[0])
            nonspecial = _consume(out, indexes, nonspecial, out["expense_category"] == "1100-500")
            special = _consume(out, indexes, special, out["expense_category"] == "1200-500")
            leftover = nonspecial + special
            if leftover > 0:
                leftover = _consume(out, indexes, leftover, out["expense_category"].str.endswith("-500"))
            if leftover > 0:
                _consume(out, indexes, leftover, out["amount_used"] > 0)
        out["slice_value"] = out["amount_used"] / out["enrollment"]
    else:
        out["slice_value"] = out["amount_used"]
    return out[out["slice_value"] > 0].copy()


def selection_summary(frame: pd.DataFrame, measure: str, school_year: int) -> dict[str, float | int | bool]:
    if frame.empty:
        return {"empty": True, "school_year": school_year}
    districts = frame[frame["lea_type"] == "SD"]
    one_per_lea = frame.drop_duplicates("aun")
    district_leas = one_per_lea[one_per_lea["lea_type"] == "SD"]
    charter_removed = float(district_leas["charter_nonspecial"].sum() + district_leas["charter_special"].sum())
    sped_kept = float(district_leas["sped_aps"].sum() + district_leas["sped_prri"].sum())
    total = float(frame["expense_value"].sum())
    enrollment = float(one_per_lea["enrollment"].sum())
    tuition_ready = school_year in tuition_years()
    per_pupil = (total - charter_removed) / enrollment if enrollment and tuition_ready else None
    return {
        "empty": False,
        "school_year": school_year,
        "measure": measure,
        "total": total,
        "charter_removed": charter_removed,
        "sped_kept": sped_kept,
        "enrollment": enrollment,
        "per_pupil": per_pupil,
        "tuition_ready": tuition_ready,
        "districts": int((one_per_lea["lea_type"] == "SD").sum()),
        "charters": int((one_per_lea["lea_type"] != "SD").sum()),
        "district_expense": float(districts["expense_value"].sum()) if not districts.empty else 0.0,
    }


def build_sunburst(
    county: str,
    lea_names: list[str],
    school_year: int,
    measure: str = MEASURE_PER_PUPIL,
) -> go.Figure:
    label = f"{school_year}-{str(school_year + 1)[-2:]}"
    if measure == MEASURE_PER_PUPIL and school_year not in tuition_years():
        figure = go.Figure()
        figure.update_layout(
            title=f"{label}: charter tuition actuals are not published for this year yet"
        )
        return figure
    raw = expense_frame(county, lea_names, school_year)
    frame = apply_measure(raw, measure)
    title = (
        f"Per pupil, charter tuition removed, {label}"
        if measure == MEASURE_PER_PUPIL
        else f"All district expenses, {label}"
    )
    if frame.empty:
        figure = go.Figure()
        figure.update_layout(title=f"{title}: no rows for this selection")
        return figure
    figure = px.sunburst(
        frame,
        path=[
            "lea_name",
            "expense_category_name_0",
            "expense_category_name_1",
            "expense_category_name_2",
        ],
        values="slice_value",
        color="expense_category_name_0",
        hover_data={
            "expense_value": ":.0f",
            "amount_used": ":.0f",
            "charter_removed": ":.0f",
            "enrollment": True,
            "expense_category": True,
        },
        title=title,
    )
    figure.update_layout(margin=dict(t=48, l=8, r=8, b=8), height=720)
    return figure


def _consume(frame: pd.DataFrame, indexes, bucket: float, mask: pd.Series) -> float:
    if bucket <= 0:
        return 0.0
    chosen = frame.loc[indexes].index[mask.loc[indexes].to_numpy()]
    chosen = frame.loc[chosen].sort_values("amount_used", ascending=False).index
    for index in chosen:
        available = float(frame.at[index, "amount_used"])
        if available <= 0:
            continue
        take = min(available, bucket)
        frame.at[index, "amount_used"] = available - take
        frame.at[index, "charter_removed"] = float(frame.at[index, "charter_removed"]) + take
        bucket -= take
        if bucket <= 0.5:
            return 0.0
    return bucket
