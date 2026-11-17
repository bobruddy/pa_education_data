"""County comparison of general-fund amounts per student.

One payload per county: every LEA except intermediate units and career and
technical centers. Actuals, budget, and income each replace the bars. Each
click opens the next account until the posted one. ``publish`` writes a
file per county for the LEA browser. This module also serves Chester locally:

    python -m pa_edu.compare
"""

from __future__ import annotations

import json
import statistics
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import duckdb

from pa_edu.common import DATA_DIR

PORT = 8092
PAGE = Path(__file__).resolve().parent / "compare_web"

COUNTY = "Chester"
EXCLUDED = {"intermediate_unit", "career_and_technical_center"}
COMPARISON_ID = "fund10"
COMPARISON_TITLE = "General fund per student"
COMPARISON_BLURB = (
    "Actuals, budget, and income, one account at a time. "
    "Career and technical centers are left out."
)

# Labels and colors the sunburst already uses for these majors.
MAJORS = (
    ("1000", "Instruction", "#0c5c56"),
    ("2000", "Support services", "#2f5f8a"),
    ("3000", "Noninstructional", "#8a6a2f"),
    ("4000", "Facilities", "#6b5344"),
    ("5000", "Other financing uses", "#a1622a"),
)
MAJOR_CODES = {code for code, _label, _color in MAJORS}
# Same object classes the sunburst uses. A posted 510 stays under 500 until the click.
OBJECTS = (
    ("100", "Salaries"),
    ("200", "Benefits"),
    ("300", "Professional services"),
    ("400", "Property services"),
    ("500", "Other purchased services"),
    ("600", "Supplies"),
    ("700", "Property"),
    ("800", "Other objects"),
    ("900", "Other uses of funds"),
)
OBJECT_LABELS = dict(OBJECTS)
REVENUE_MAJORS = (
    ("6000", "Local", "#1f7a4d"),
    ("7000", "State", "#2f5f8a"),
    ("8000", "Federal", "#6b4c7a"),
    ("9000", "Other financing sources", "#8a5a2f"),
)
REVENUE_CODES = {code for code, _label, _color in REVENUE_MAJORS}


def comparison_catalog() -> list[dict]:
    """Comparisons the county page can open. The browser renders each id."""
    return [{
        "id": COMPARISON_ID,
        "title": COMPARISON_TITLE,
        "blurb": COMPARISON_BLURB,
    }]


def comparison_counties(refined: Path) -> list[str]:
    """Directory counties that still have an LEA after the exclusions."""
    excluded = ", ".join(f"'{item}'" for item in sorted(EXCLUDED))
    connection = duckdb.connect()
    try:
        rows = connection.sql(f"""
            SELECT DISTINCT county
            FROM '{_sql_path(Path(refined) / "lea.parquet")}'
            WHERE county IS NOT NULL AND county <> ''
              AND (category IS NULL OR category NOT IN ({excluded}))
            ORDER BY county
        """).fetchall()
    finally:
        connection.close()
    return [str(row[0]) for row in rows]


def build_compare(refined: Path | None = None, county: str = COUNTY) -> dict:
    """One county, one view each for actuals, budget, and income."""
    root = Path(refined) if refined is not None else DATA_DIR / "refined"
    missing = [
        name
        for name in (
            "afr_expenditure.parquet",
            "gfb_expenditure.parquet",
            "afr_revenue.parquet",
            "enrollment.parquet",
            "lea.parquet",
            "account.parquet",
            "revenue_account.parquet",
            "document.parquet",
        )
        if not (root / name).exists()
    ]
    if missing:
        raise SystemExit(f"refined data is missing {', '.join(missing)}")

    connection = duckdb.connect()
    try:
        leas = _leas(connection, root, county)
        auns = [aun for aun, _name, _category in leas]
        labels = _function_labels(connection, root)
        object_labels = _object_labels(connection, root)
        revenue_labels = _revenue_labels(connection, root)
        actual = _expenditure_view(
            connection, root, county, leas, auns, labels, object_labels,
            view_id="actual", label="Actuals", heading="actual", source_label="AFR",
            table="afr_expenditure.parquet", amount_column="total_amount",
            note="General fund only. Charter tuition (object 562) is removed. A year with no AFR is left blank. ",
            blurb="General-fund actual, divided by October 1 enrollment.",
        )
        budget = _expenditure_view(
            connection, root, county, leas, auns, labels, object_labels,
            view_id="budget", label="Budget", heading="budget", source_label="Budget",
            table="gfb_expenditure.parquet", amount_column="amount",
            note="General fund only. Charter tuition (object 562) is removed. A year with no budget is left blank. ",
            blurb="General-fund budget, divided by October 1 enrollment.",
        )
        income = _revenue_view(connection, root, county, leas, auns, revenue_labels)
    finally:
        connection.close()

    return {
        "id": COMPARISON_ID,
        "title": COMPARISON_TITLE,
        "blurb": COMPARISON_BLURB,
        "county": county,
        "views": [actual, budget, income],
    }


def _expenditure_view(
    connection: duckdb.DuckDBPyConnection,
    root: Path,
    county: str,
    leas: list[tuple[str, str, str]],
    auns: list[str],
    function_labels: dict[str, str],
    object_labels: dict[str, str],
    *,
    view_id: str,
    label: str,
    heading: str,
    source_label: str,
    table: str,
    amount_column: str,
    note: str,
    blurb: str,
) -> dict:
    year, enrolled = _open_year(connection, root, table, auns, label, county)
    spending = _spending(connection, root, table, amount_column, year, auns, label)
    districts = [
        _district(aun, name, spending["rows"].get(aun), enrolled["counts"].get(aun))
        for aun, name, _category in leas
    ]
    nodes = _nodes(
        districts,
        lambda code: _node_label(code, function_labels, object_labels),
        _node_parent,
    )
    return _assemble(
        view_id, label, heading, source_label, note, year, districts, nodes, MAJORS,
        _source(connection, root, spending["document_id"], label),
        _source(connection, root, enrolled["document_id"], "Enrollment"),
        blurb,
    )


def _revenue_view(
    connection: duckdb.DuckDBPyConnection,
    root: Path,
    county: str,
    leas: list[tuple[str, str, str]],
    auns: list[str],
    revenue_labels: dict[str, str],
) -> dict:
    year, enrolled = _open_year(connection, root, "afr_revenue.parquet", auns, "Income", county)
    revenue = _revenue_rows(connection, root, year, auns)
    districts = []
    parents: dict[str, str | None] = {}
    for aun, name, _category in leas:
        row, found = _revenue_district(aun, name, revenue["rows"].get(aun), enrolled["counts"].get(aun))
        districts.append(row)
        for code, parent in found.items():
            if code in parents and parents[code] != parent:
                raise SystemExit(f"{code} rolls up to both {parents[code]} and {parent}")
            parents[code] = parent
    nodes = _nodes(
        districts,
        lambda code: _revenue_label(code, revenue_labels),
        lambda code: parents[code],
    )
    return _assemble(
        "income", "Income", "income", "AFR revenue",
        "General fund only. A year with no AFR revenue is left blank. ",
        year, districts, nodes, REVENUE_MAJORS,
        _source(connection, root, revenue["document_id"], "Income"),
        _source(connection, root, enrolled["document_id"], "Enrollment"),
        "General-fund revenue, divided by October 1 enrollment.",
    )


def _assemble(
    view_id: str,
    label: str,
    heading: str,
    source_label: str,
    note: str,
    year: int,
    districts: list[dict],
    nodes: dict[str, dict],
    majors: tuple,
    source: dict | None,
    enrollment: dict | None,
    blurb: str,
) -> dict:
    districts.sort(key=lambda item: (not item["published"], -(item.get("perStudent") or 0), item["name"]))
    medians = {"total": _median([item["perStudent"] for item in districts if item["published"]])}
    for code in nodes:
        medians[code] = _median([
            item["levels"][code]["perStudent"]
            for item in districts
            if item["published"] and code in item.get("levels", {})
        ])
    return {
        "id": view_id,
        "label": label,
        "heading": heading,
        "sourceLabel": source_label,
        "note": note,
        "blurb": blurb,
        "year": year,
        "yearLabel": f"{year}–{str(year + 1)[-2:]}",
        "source": source,
        "enrollment": enrollment,
        "majors": [
            {"code": code, "label": major_label, "color": color}
            for code, major_label, color in majors
        ],
        "nodes": nodes,
        "medians": medians,
        "districts": districts,
    }


def _district(aun: str, name: str, rows: list[tuple[str, str, float]] | None, enrolled: int | None) -> dict:
    if not rows or enrolled is None or enrolled <= 0:
        return {"aun": aun, "name": name, "published": False, "enrolled": enrolled}
    levels = _levels(aun, rows)
    _children_match(aun, levels)
    total = round(sum(levels[code] for code in MAJOR_CODES if code in levels), 2)
    packed = {
        code: {"amount": amount, "perStudent": round(amount / enrolled, 2)}
        for code, amount in levels.items()
    }
    return {
        "aun": aun,
        "name": name,
        "published": True,
        "enrolled": enrolled,
        "total": total,
        "perStudent": round(total / enrolled, 2),
        "levels": packed,
    }


def _revenue_district(
    aun: str,
    name: str,
    rows: list[tuple] | None,
    enrolled: int | None,
) -> tuple[dict, dict[str, str | None]]:
    if not rows or enrolled is None or enrolled <= 0:
        return {"aun": aun, "name": name, "published": False, "enrolled": enrolled}, {}
    levels, parents = _revenue_levels(aun, rows)
    total = round(sum(levels[code] for code in REVENUE_CODES if code in levels), 2)
    packed = {
        code: {"amount": amount, "perStudent": round(amount / enrolled, 2)}
        for code, amount in levels.items()
    }
    return {
        "aun": aun,
        "name": name,
        "published": True,
        "enrolled": enrolled,
        "total": total,
        "perStudent": round(total / enrolled, 2),
        "levels": packed,
    }, parents


def _revenue_levels(
    aun: str,
    rows: list[tuple],
) -> tuple[dict[str, float], dict[str, str | None]]:
    """Sum each posted revenue leaf into its rollup chain. A parent row is not added again."""
    posted = {str(account) for account, _r1, _r2, _r3, _amount in rows}
    covered = set()
    for account, r1, r2, r3, _amount in rows:
        for code in (r1, r2, r3):
            if code and str(code) in posted and str(code) != str(account):
                covered.add(str(code))
    levels: dict[str, float] = {}
    parents: dict[str, str | None] = {}
    for account, r1, r2, r3, amount in rows:
        account = str(account)
        if account in covered:
            continue
        if amount is None:
            raise SystemExit(f"{aun} revenue {account} has no amount")
        chain = _revenue_chain(account, r1, r2, r3)
        if chain[0] not in REVENUE_CODES:
            raise SystemExit(f"{aun} revenue {account} is outside the revenue majors")
        for index, code in enumerate(chain):
            parent = chain[index - 1] if index else None
            if code in parents and parents[code] != parent:
                raise SystemExit(f"{aun} {code} rolls up to both {parents[code]} and {parent}")
            parents[code] = parent
            _add(levels, code)
            levels[code] += float(amount)
    rounded = {code: round(amount, 2) for code, amount in levels.items()}
    for code, amount in rounded.items():
        kids = [other for other, parent in parents.items() if parent == code and other in rounded]
        if not kids:
            continue
        total = round(sum(rounded[kid] for kid in kids), 2)
        if abs(total - amount) > 0.05:
            raise SystemExit(f"{aun} {code} is {amount} and its accounts add to {total}")
    return rounded, parents


def _revenue_chain(account: str, r1: object, r2: object, r3: object) -> list[str]:
    chain = []
    for code in (r1, r2, r3):
        if code is None or str(code) in {"", "None", "nan"}:
            continue
        text = str(code)
        if len(text) != 4 or not text.isdigit():
            raise SystemExit(f"revenue rollup {text} is not a 4-digit account")
        if text not in chain:
            chain.append(text)
    if len(account) != 4 or not account.isdigit():
        raise SystemExit(f"revenue account {account} is not a 4-digit account")
    if not chain:
        major = account[0] + "000"
        return [account] if account == major else [major, account]
    if chain[-1] != account:
        chain.append(account)
    return chain


def _revenue_label(code: str, labels: dict[str, str]) -> str:
    for major, label, _color in REVENUE_MAJORS:
        if code == major:
            return label
    return labels.get(code, code)


def _levels(aun: str, rows: list[tuple[str, str, float]]) -> dict[str, float]:
    """Sum each posted leaf into every account above it. Drop object 562 from the function that posted it."""
    codes = {function for function, _object, _amount in rows}
    leaves = leaf_codes(codes)
    posted: dict[str, set[str]] = {}
    for function, obj, _amount in rows:
        if obj == "562" and function not in leaves:
            raise SystemExit(f"{aun} object 562 is posted on parent function {function}")
        if function in leaves:
            posted.setdefault(function, set()).add(obj)
    kept_objects = {function: object_leaves(objs) for function, objs in posted.items()}
    levels: dict[str, float] = {}
    for function, obj, amount in rows:
        if function not in leaves:
            continue
        if function[0] + "000" not in MAJOR_CODES:
            raise SystemExit(f"{aun} function {function} is outside the five majors")
        for key in _function_keys(function):
            _add(levels, key)
        if obj == "562" or obj not in kept_objects[function]:
            continue
        if obj[0] + "00" not in OBJECT_LABELS:
            raise SystemExit(f"{aun} object {obj} is outside the major objects")
        for key in _account_keys(function, obj):
            _add(levels, key)
            levels[key] += amount
    return {code: round(amount, 2) for code, amount in levels.items()}


def _function_keys(function: str) -> list[str]:
    major = function[0] + "000"
    activity = function[:2] + "00"
    keys = [major]
    if activity != major:
        keys.append(activity)
    if function != activity:
        keys.append(function)
    return keys


def _account_keys(function: str, obj: str) -> list[str]:
    """The posted account and each rollup that contains it, from the major down."""
    keys = _function_keys(function)
    major_object = obj[0] + "00"
    keys.append(f"{function}-{major_object}")
    if obj != major_object:
        keys.append(f"{function}-{obj}")
    return keys


def _node_parent(code: str) -> str | None:
    if "-" in code:
        function, obj = code.split("-", 1)
        if obj.endswith("00"):
            return function
        return f"{function}-{obj[0]}00"
    if len(code) == 4 and code.endswith("000"):
        return None
    if len(code) == 4 and code.endswith("00"):
        return code[0] + "000"
    if len(code) == 4:
        return code[:2] + "00"
    raise SystemExit(f"account {code} is not a function or function-object")


def _add(levels: dict[str, float], code: str) -> None:
    levels.setdefault(code, 0.0)


def _children_match(aun: str, levels: dict[str, float]) -> None:
    for code, amount in levels.items():
        kids = [other for other in levels if _node_parent(other) == code]
        if not kids:
            continue
        total = round(sum(levels[kid] for kid in kids), 2)
        if abs(total - amount) > 0.05:
            raise SystemExit(f"{aun} {code} is {amount} and its accounts add to {total}")


def _nodes(districts: list[dict], label_of, parent_of) -> dict[str, dict]:
    codes: set[str] = set()
    for district in districts:
        codes.update(district.get("levels") or {})
    nodes: dict[str, dict] = {}
    for code in codes:
        parent = parent_of(code)
        if parent is not None and parent not in codes:
            raise SystemExit(f"{code} has no {parent}")
        nodes[code] = {"label": label_of(code), "parent": parent, "children": []}
    for code in codes:
        parent = parent_of(code)
        if parent is None:
            continue
        nodes[parent]["children"].append(code)
    for node in nodes.values():
        node["children"].sort()
    return nodes


def _node_label(code: str, function_labels: dict[str, str], object_labels: dict[str, str]) -> str:
    for major, label, _color in MAJORS:
        if code == major:
            return label
    if "-" in code:
        obj = code.split("-", 1)[1]
        if obj in OBJECT_LABELS:
            return OBJECT_LABELS[obj]
        return object_labels.get(obj, obj)
    return function_labels.get(code, code)


def object_leaves(codes: set[str]) -> set[str]:
    """Posted objects, without a parent that also has a child in the set.

    100 beside 110 is the parent. 130 with no other 1xx is the leaf, and it
    still rolls into major object 100.
    """
    return {code for code in codes if not _is_object_parent(code, codes)}


def _is_object_parent(code: str, codes: set[str]) -> bool:
    if len(code) != 3 or not code.endswith("00"):
        return False
    return any(other != code and other.startswith(code[0]) for other in codes)


def leaf_codes(codes: set[str]) -> set[str]:
    """Posted functions, without a parent that also has a child in the set.

    1100 beside 1110 is the parent. 3200 with no 32xx child is the leaf.
    """
    return {code for code in codes if not _is_parent(code, codes)}


def _is_parent(code: str, codes: set[str]) -> bool:
    for other in codes:
        if other == code or len(code) != 4 or len(other) != 4:
            continue
        if code.endswith("000") and other[0] == code[0]:
            return True
        if code.endswith("00") and other.startswith(code[:2]):
            return True
    return False


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return round(float(statistics.median(values)), 2)


def _leas(connection: duckdb.DuckDBPyConnection, root: Path, county: str) -> list[tuple[str, str, str]]:
    frame = connection.sql(f"""
        SELECT aun, lea_name, category
        FROM '{_sql_path(root / "lea.parquet")}'
        WHERE county = {_sql_literal(county)}
        ORDER BY lea_name
    """).fetchall()
    if not frame:
        raise SystemExit(f"{county} has no LEAs in the directory")
    leas = []
    seen: set[str] = set()
    for aun, lea_name, category in frame:
        aun = str(aun)
        if aun in seen:
            raise SystemExit(f"{aun} is in the directory twice")
        seen.add(aun)
        if category in EXCLUDED:
            continue
        if not lea_name:
            raise SystemExit(f"{aun} has no directory name")
        leas.append((aun, str(lea_name), str(category or "")))
    if not leas:
        raise SystemExit(f"{county} has no LEAs in the directory")
    return leas


def _open_year(
    connection: duckdb.DuckDBPyConnection,
    root: Path,
    table: str,
    auns: list[str],
    kind: str,
    county: str,
) -> tuple[int, dict]:
    years = connection.sql(f"""
        SELECT DISTINCT school_year
        FROM '{_sql_path(root / table)}'
        WHERE fund_code = '10' AND aun IN ({_aun_list(auns)})
        ORDER BY 1 DESC
    """).fetchall()
    if not years:
        raise SystemExit(f"{county} has no general-fund {kind}")
    for (year,) in years:
        year = int(year)
        enrolled = _enrollment(connection, root, year, auns)
        if any(count > 0 for count in enrolled["counts"].values()):
            return year, enrolled
    raise SystemExit(f"{county} general-fund {kind} has no year with October 1 enrollment")


def _function_labels(connection: duckdb.DuckDBPyConnection, root: Path) -> dict[str, str]:
    frame = connection.sql(f"""
        SELECT function_code, any_value(function_name) AS function_name
        FROM '{_sql_path(root / "account.parquet")}'
        WHERE function_code IS NOT NULL AND function_name IS NOT NULL
        GROUP BY 1
    """).fetchall()
    return {str(code): _account_label(name) for code, name in frame}


def _object_labels(connection: duckdb.DuckDBPyConnection, root: Path) -> dict[str, str]:
    frame = connection.sql(f"""
        SELECT object_code, any_value(object_name) AS object_name
        FROM '{_sql_path(root / "account.parquet")}'
        WHERE object_code IS NOT NULL AND object_name IS NOT NULL
        GROUP BY 1
    """).fetchall()
    return {str(code): _detail_label(name) for code, name in frame}


def _detail_label(value: object) -> str:
    text = " ".join(str(value).replace("–", "-").replace("—", "-").split())
    if not text:
        return text
    return text[:1].upper() + text[1:].lower()


def _account_label(value: object) -> str:
    text = " ".join(str(value).replace("–", "-").replace("—", "-").split())
    if " - " in text:
        head, tail = text.split(" - ", 1)
        if head.casefold() == "support services" and tail.strip():
            text = tail.strip()
        else:
            text = head
    if not text:
        return text
    head, sep, tail = text.partition("(")
    label = head[:1].upper() + head[1:].lower()
    if sep:
        label = f"{label}{sep}{tail}"
    if label.count("(") != label.count(")"):
        label = label.split("(", 1)[0].rstrip()
    return label


def _spending(
    connection: duckdb.DuckDBPyConnection,
    root: Path,
    table: str,
    amount_column: str,
    year: int,
    auns: list[str],
    kind: str,
) -> dict:
    frame = connection.sql(f"""
        SELECT aun, function_code, object_code, {amount_column}, document_id
        FROM '{_sql_path(root / table)}'
        WHERE fund_code = '10' AND school_year = {int(year)} AND aun IN ({_aun_list(auns)})
    """).fetchall()
    rows: dict[str, list[tuple[str, str, float]]] = {}
    documents = set()
    for aun, function, obj, amount, document_id in frame:
        if function is None or obj is None or amount is None:
            raise SystemExit(f"{aun} general-fund {kind} row is missing a function, object, or amount")
        function = str(function)
        obj = str(obj)
        if len(function) != 4 or not function.isdigit() or len(obj) != 3 or not obj.isdigit():
            raise SystemExit(f"{aun} account {function}-{obj} is not a 4-digit function and 3-digit object")
        rows.setdefault(str(aun), []).append((function, obj, float(amount)))
        documents.add(str(document_id))
    if len(documents) > 1:
        raise SystemExit(f"{year} general-fund {kind} rows cite more than one document")
    return {"rows": rows, "document_id": next(iter(documents)) if documents else None}


def _revenue_rows(connection: duckdb.DuckDBPyConnection, root: Path, year: int, auns: list[str]) -> dict:
    frame = connection.sql(f"""
        SELECT aun, account_code, rollup1_account_code, rollup2_account_code,
               rollup3_account_code, amount, document_id
        FROM '{_sql_path(root / "afr_revenue.parquet")}'
        WHERE fund_code = '10' AND school_year = {int(year)} AND aun IN ({_aun_list(auns)})
    """).fetchall()
    rows: dict[str, list[tuple]] = {}
    documents = set()
    for aun, account, r1, r2, r3, amount, document_id in frame:
        if account is None or amount is None:
            raise SystemExit(f"{aun} general-fund revenue row is missing an account or amount")
        rows.setdefault(str(aun), []).append((str(account), r1, r2, r3, float(amount)))
        documents.add(str(document_id))
    if len(documents) > 1:
        raise SystemExit(f"{year} general-fund revenue rows cite more than one document")
    return {"rows": rows, "document_id": next(iter(documents)) if documents else None}


def _revenue_labels(connection: duckdb.DuckDBPyConnection, root: Path) -> dict[str, str]:
    frame = connection.sql(f"""
        SELECT account_code, any_value(name) AS name
        FROM '{_sql_path(root / "revenue_account.parquet")}'
        WHERE account_code IS NOT NULL AND name IS NOT NULL
        GROUP BY 1
    """).fetchall()
    return {str(code): _detail_label(name) for code, name in frame}


def _enrollment(connection: duckdb.DuckDBPyConnection, root: Path, year: int, auns: list[str]) -> dict:
    frame = connection.sql(f"""
        SELECT aun, sum(enrollment) AS enrolled, count(DISTINCT document_id) AS documents,
               any_value(document_id) AS document_id
        FROM '{_sql_path(root / "enrollment.parquet")}'
        WHERE school_year = {int(year)} AND aun IN ({_aun_list(auns)})
        GROUP BY 1
    """).fetchall()
    counts = {}
    documents = set()
    for aun, enrolled, documents_n, document_id in frame:
        if documents_n and int(documents_n) > 1:
            raise SystemExit(f"{aun} {year} enrollment cites more than one document")
        if enrolled is None:
            continue
        number = float(enrolled)
        if abs(number - round(number)) > 0.001:
            raise SystemExit(f"{aun} October 1 enrollment is {number}, not a whole count")
        counts[str(aun)] = int(round(number))
        if document_id is not None:
            documents.add(str(document_id))
    if len(documents) > 1:
        raise SystemExit(f"{year} enrollment cites more than one document")
    return {"counts": counts, "document_id": next(iter(documents)) if documents else None}


def _source(connection: duckdb.DuckDBPyConnection, root: Path, document_id: str | None, kind: str) -> dict | None:
    if not document_id:
        return None
    found = connection.sql(f"""
        SELECT source_url
        FROM '{_sql_path(root / "document.parquet")}'
        WHERE document_id = '{document_id.replace("'", "''")}'
    """).fetchall()
    if len(found) != 1 or not found[0][0]:
        raise SystemExit(f"{kind} document {document_id} has no source URL")
    return {"name": kind, "url": str(found[0][0]), "documentId": document_id}


def _aun_list(auns: list[str]) -> str:
    return ", ".join(_sql_literal(aun) for aun in auns)


def _sql_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _sql_path(path: Path) -> str:
    return str(path).replace("'", "''")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/compare.json":
            body = json.dumps(build_compare(), ensure_ascii=False).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", body)
            return
        name = "index.html" if path in {"/", "/index.html"} else path.lstrip("/")
        if name not in {"index.html", "compare.css", "compare.js"}:
            self._send(404, "text/plain; charset=utf-8", b"not found")
            return
        file = PAGE / name
        kind = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
        }[file.suffix]
        self._send(200, kind, file.read_bytes())

    def log_message(self, fmt: str, *args) -> None:
        print(f"{self.address_string()} {fmt % args}")

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def serve(port: int = PORT) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"serving Chester comparison on http://127.0.0.1:{port}/")
    server.serve_forever()


def main() -> None:
    payload = build_compare()
    for item in payload["views"]:
        published = sum(1 for district in item["districts"] if district["published"])
        print(f"{item['label']} {item['yearLabel']}: {published} of {len(item['districts'])} LEAs")
    serve()


if __name__ == "__main__":
    main()
