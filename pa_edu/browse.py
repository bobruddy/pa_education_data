"""Paginated HTML view of one refined Parquet file.

The data service links each table name here. The Parquet download stays at
``/refined/<table>.parquet``. A page is a DuckDB query with a limit, so the
browser does not load the whole file. Each column has a sort control and a
filter control. Filters on different columns are combined with AND.
"""

from __future__ import annotations

import html
import urllib.parse
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import duckdb
import pyarrow.parquet as pq

from pa_edu.status import redact

PAGE_SIZES = (50, 100, 150, 200, 250)
DEFAULT_PAGE_SIZE = 50
MAX_CELL = 4000
MAX_QUERY = 200
_NUMERIC = {
    "TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT",
    "UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT", "UHUGEINT",
    "FLOAT", "DOUBLE", "REAL", "DECIMAL",
}
_FILTER_PREFIX = "q."


@dataclass(frozen=True)
class _Request:
    page: int
    page_size: int
    sort: str
    direction: str
    filters: tuple[tuple[str, str], ...]
    open: str


@dataclass(frozen=True)
class _Page:
    columns: tuple[tuple[str, str], ...]
    rows: tuple[tuple, ...]
    total: int
    page: int
    page_size: int
    sort: str | None
    direction: str
    filters: tuple[tuple[str, str], ...]
    open: str | None


def render_browse(path: Path, query: dict[str, list[str]] | None = None) -> str:
    request = _request(query or {})
    try:
        page = _read(path, request)
    except Exception as exc:
        return _error_page(path, exc)
    return _html(path.name, page)


def _request(query: dict[str, list[str]]) -> _Request:
    filters = []
    for key, values in query.items():
        if not key.startswith(_FILTER_PREFIX) or not values or values[0] is None:
            continue
        column = key[len(_FILTER_PREFIX):]
        text = str(values[0]).strip()[:MAX_QUERY]
        if column and text:
            filters.append((column, text))
    return _Request(
        page=_page(_first(query, "page")),
        page_size=_page_size(_first(query, "page_size")),
        sort=_first(query, "sort"),
        direction="desc" if _first(query, "dir") == "desc" else "asc",
        filters=tuple(filters),
        open=_first(query, "open"),
    )


def _read(path: Path, request: _Request) -> _Page:
    connection = duckdb.connect()
    try:
        described = connection.execute(
            "DESCRIBE SELECT * FROM read_parquet(?)",
            [str(path)],
        ).fetchall()
        types = {str(row[0]): str(row[1]) for row in described}
        names = [str(row[0]) for row in described]
        requested = dict(request.filters)
        filters = tuple((name, requested[name]) for name in names if name in requested)
        sort = request.sort if request.sort in types else None
        opened = request.open if request.open in types else None
        params: list[object] = [str(path)]
        where = ""
        if filters:
            clauses = []
            for name, text in filters:
                clauses.append(f"CAST({_quote(name)} AS VARCHAR) ILIKE ? ESCAPE '\\'")
                params.append("%" + _like_escape(text) + "%")
            where = " WHERE " + " AND ".join(clauses)
            total = int(connection.execute(
                f"SELECT COUNT(*) FROM read_parquet(?){where}",
                params,
            ).fetchone()[0])
        else:
            total = int(pq.read_metadata(path).num_rows)
        page_size = request.page_size
        direction = request.direction if sort else "asc"
        if total == 0:
            return _Page(
                columns=tuple((name, types[name]) for name in names),
                rows=(),
                total=0,
                page=1,
                page_size=page_size,
                sort=sort,
                direction=direction,
                filters=filters,
                open=opened,
            )
        last = (total + page_size - 1) // page_size
        page_number = min(request.page, last)
        order = ""
        if sort:
            way = "DESC" if direction == "desc" else "ASC"
            order = f" ORDER BY {_quote(sort)} {way} NULLS LAST"
        offset = (page_number - 1) * page_size
        cursor = connection.execute(
            f"SELECT * FROM read_parquet(?){where}{order} LIMIT {page_size} OFFSET {offset}",
            params,
        )
        fetched = [item[0] for item in cursor.description]
        rows = tuple(cursor.fetchall())
        return _Page(
            columns=tuple((name, types.get(name, "")) for name in fetched),
            rows=rows,
            total=total,
            page=page_number,
            page_size=page_size,
            sort=sort,
            direction=direction,
            filters=filters,
            open=opened,
        )
    finally:
        connection.close()


def _html(file_name: str, page: _Page) -> str:
    title = html.escape(file_name)
    body = [
        f"<h1>{title}</h1>",
        _links(file_name),
        _size_form(file_name, page),
        _summary(page),
        _table(file_name, page),
        _pager(file_name, page),
    ]
    return _document(file_name, "\n".join(part for part in body if part))


def _error_page(path: Path, exc: BaseException) -> str:
    detail = html.escape(_public_error(path, exc))
    body = (
        f"<h1>{html.escape(path.name)}</h1>"
        f"{_links(path.name)}"
        "<p>This Parquet file could not be read.</p>"
        f'<p class="meta">{detail}</p>'
    )
    return _document(path.name, body)


def _document(file_name: str, body: str) -> str:
    title = html.escape(file_name)
    return "\n".join([
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="robots" content="noindex">',
        f"<title>{title} · PDE data</title>",
        f"<style>{_CSS}</style>",
        "</head>",
        "<body>",
        body,
        "</body>",
        "</html>",
        "",
    ])


def _links(file_name: str) -> str:
    safe = html.escape(file_name)
    return (
        f'<p class="meta"><a href="/">PDE data</a>'
        f' · <a href="/refined/{safe}">Download parquet</a></p>'
    )


def _size_form(file_name: str, page: _Page) -> str:
    sizes = []
    for size in PAGE_SIZES:
        selected = " selected" if size == page.page_size else ""
        sizes.append(f'<option value="{size}"{selected}>{size}</option>')
    action = html.escape(f"/browse/{file_name}", quote=True)
    hidden = _hidden(page, include_page_size=False, include_sort=True, include_filters=True)
    return (
        f'<form method="get" action="{action}" class="tools">'
        f'<label>Rows <select name="page_size" onchange="this.form.submit()">{"".join(sizes)}</select></label>'
        f"{hidden}"
        "</form>"
    )


def _summary(page: _Page) -> str:
    if page.total == 0:
        text = "No matching rows." if page.filters else "No rows."
        return f'<p class="meta">{text}</p>'
    if not page.rows:
        return '<p class="meta">No rows on this page.</p>'
    start = (page.page - 1) * page.page_size + 1
    end = start + len(page.rows) - 1
    return f'<p class="meta">Rows {start:,}-{end:,} of {page.total:,}</p>'


def _table(file_name: str, page: _Page) -> str:
    if not page.columns:
        return "<p>This Parquet file has no columns.</p>"
    headers = "".join(_header(file_name, name, type_name, page) for name, type_name in page.columns)
    body = "".join(
        "<tr>"
        + "".join(_cell(value, type_name) for value, (_name, type_name) in zip(row, page.columns, strict=True))
        + "</tr>"
        for row in page.rows
    )
    return f'<div class="wrap"><table><thead><tr>{headers}</tr></thead><tbody>{body}</tbody></table></div>'


def _header(file_name: str, name: str, type_name: str, page: _Page) -> str:
    cls = ' class="num"' if _numeric(type_name) else ""
    shown = html.escape(name)
    value = dict(page.filters).get(name, "")
    is_open = page.open == name
    sort_mark = "↕"
    sort_class = "icon"
    next_dir = "asc"
    if page.sort == name:
        sort_class = "icon on"
        if page.direction == "asc":
            sort_mark = "↑"
            next_dir = "desc"
        else:
            sort_mark = "↓"
    sort_href = html.escape(_href(
        file_name,
        page_size=page.page_size,
        sort=name,
        direction=next_dir,
        filters=page.filters,
        open_column=page.open,
    ), quote=True)
    filter_href = html.escape(_href(
        file_name,
        page=page.page,
        page_size=page.page_size,
        sort=page.sort,
        direction=page.direction,
        filters=page.filters,
        open_column=None if is_open else name,
    ), quote=True)
    if is_open:
        filter_label = f"Close {name} filter"
    elif value:
        filter_label = f"Filter {name}, contains {value}"
    else:
        filter_label = f"Filter {name}"
    filter_class = "icon on" if value else "icon"
    filter_mark = "▼" if value else "▽"
    label = html.escape(filter_label, quote=True)
    sort_label = html.escape(f"Sort by {name}", quote=True)
    form = _filter_form(file_name, name, value, page) if is_open else ""
    return (
        f"<th{cls}>"
        '<div class="head">'
        f'<span class="name">{shown}</span>'
        f'<a class="{sort_class}" href="{sort_href}" title="{sort_label}" aria-label="{sort_label}">{sort_mark}</a>'
        f'<a class="{filter_class}" href="{filter_href}" title="{label}" aria-label="{label}">{filter_mark}</a>'
        "</div>"
        f"{form}"
        "</th>"
    )


def _filter_form(file_name: str, name: str, value: str, page: _Page) -> str:
    action = html.escape(f"/browse/{file_name}", quote=True)
    field = html.escape(f"{_FILTER_PREFIX}{name}", quote=True)
    hidden = _hidden(
        page,
        include_page_size=True,
        include_sort=True,
        include_filters=True,
        open_column=name,
        skip_filter=name,
    )
    clear = ""
    if value:
        href = html.escape(_href(
            file_name,
            page_size=page.page_size,
            sort=page.sort,
            direction=page.direction,
            filters=tuple(item for item in page.filters if item[0] != name),
        ), quote=True)
        clear = f'<a href="{href}">Clear</a>'
    prompt = html.escape(f"{name} contains", quote=True)
    return (
        f'<form method="get" action="{action}" class="colfilter">'
        f'<input type="text" name="{field}" value="{html.escape(value, quote=True)}" aria-label="{prompt}">'
        f"{hidden}"
        '<button type="submit">Apply</button>'
        f"{clear}"
        "</form>"
    )


def _cell(value: object, type_name: str) -> str:
    cls = ' class="num"' if _numeric(type_name) else ""
    return f"<td{cls}>{html.escape(_format_cell(value))}</td>"


def _pager(file_name: str, page: _Page) -> str:
    if page.total == 0:
        return ""
    last = (page.total + page.page_size - 1) // page.page_size
    parts = []
    if page.page > 1:
        href = html.escape(_href(
            file_name, page=page.page - 1, page_size=page.page_size,
            sort=page.sort, direction=page.direction, filters=page.filters, open_column=page.open,
        ), quote=True)
        parts.append(f'<a href="{href}">Previous</a>')
    parts.append(f"<span>page {page.page:,} of {last:,}</span>")
    if page.page < last:
        href = html.escape(_href(
            file_name, page=page.page + 1, page_size=page.page_size,
            sort=page.sort, direction=page.direction, filters=page.filters, open_column=page.open,
        ), quote=True)
        parts.append(f'<a href="{href}">Next</a>')
    action = html.escape(f"/browse/{file_name}", quote=True)
    parts.append(
        f'<form method="get" action="{action}">'
        f'<input type="number" name="page" min="1" max="{last}" value="{page.page}">'
        f"{_hidden(page, include_page_size=True, include_sort=True, include_filters=True)}"
        '<button type="submit">Go</button>'
        "</form>"
    )
    return f'<div class="pager">{"".join(parts)}</div>'


def _hidden(
    page: _Page,
    *,
    include_page_size: bool,
    include_sort: bool,
    include_filters: bool,
    open_column: str | None = None,
    skip_filter: str | None = None,
) -> str:
    fields: list[tuple[str, str]] = []
    if include_page_size:
        fields.append(("page_size", str(page.page_size)))
    if include_sort and page.sort:
        fields.append(("sort", page.sort))
        fields.append(("dir", page.direction))
    if include_filters:
        for name, value in page.filters:
            if name != skip_filter:
                fields.append((f"{_FILTER_PREFIX}{name}", value))
    if open_column is None:
        open_column = page.open
    if open_column:
        fields.append(("open", open_column))
    return "".join(
        f'<input type="hidden" name="{html.escape(key, quote=True)}" value="{html.escape(value, quote=True)}">'
        for key, value in fields
    )


def _href(
    file_name: str,
    *,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    sort: str | None = None,
    direction: str = "asc",
    filters: tuple[tuple[str, str], ...] = (),
    open_column: str | None = None,
) -> str:
    params: list[tuple[str, str]] = []
    if page > 1:
        params.append(("page", str(page)))
    if page_size != DEFAULT_PAGE_SIZE:
        params.append(("page_size", str(page_size)))
    if sort:
        params.append(("sort", sort))
        params.append(("dir", direction))
    for name, value in filters:
        params.append((f"{_FILTER_PREFIX}{name}", value))
    if open_column:
        params.append(("open", open_column))
    query = urllib.parse.urlencode(params)
    base = f"/browse/{file_name}"
    if query:
        return f"{base}?{query}"
    return base


def _public_error(path: Path, exc: BaseException) -> str:
    text = redact(f"{type(exc).__name__}: {exc}", path.parent.parent)
    for candidate in (path, path.parent, path.parent.parent):
        for raw in {str(candidate), str(candidate.resolve())}:
            if raw:
                text = text.replace(raw, "<data>")
    if len(text) > 500:
        return text[:499] + "…"
    return text


def _first(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key) or []
    if not values or values[0] is None:
        return ""
    return str(values[0])


def _page(raw: str) -> int:
    if not raw.isdigit() or len(raw) > 9:
        return 1
    return max(int(raw), 1)


def _page_size(raw: str) -> int:
    if not raw.isdigit() or len(raw) > 3:
        return DEFAULT_PAGE_SIZE
    value = int(raw)
    if value in PAGE_SIZES:
        return value
    return DEFAULT_PAGE_SIZE


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _like_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _numeric(type_name: str) -> bool:
    return type_name.split("(", 1)[0].upper() in _NUMERIC


def _format_cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, int):
        text = str(value)
    elif isinstance(value, float):
        if value != value:
            text = "NaN"
        elif value == float("inf"):
            text = "inf"
        elif value == float("-inf"):
            text = "-inf"
        else:
            text = format(value, ".12f").rstrip("0").rstrip(".") or "0"
    elif isinstance(value, Decimal):
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        text = text or "0"
    elif isinstance(value, datetime):
        text = value.isoformat(sep=" ", timespec="seconds")
    elif isinstance(value, date):
        text = value.isoformat()
    else:
        text = str(value)
    if len(text) > MAX_CELL:
        return text[: MAX_CELL - 1] + "…"
    return text


_CSS = """
body { font: 15px/1.45 system-ui, sans-serif; margin: 1.25rem; color: #1c1917;
       background: #fafaf9; }
h1 { font-size: 1.4rem; margin: 0.2rem 0; }
.meta { color: #57534e; }
.tools, .pager { display: flex; flex-wrap: wrap; gap: 0.75rem; align-items: end; }
.pager { align-items: center; }
label { display: flex; flex-direction: column; gap: 0.15rem; font-size: 0.85rem; color: #57534e; }
.pager form, .colfilter { display: flex; gap: 0.35rem; align-items: center; }
.colfilter { margin-top: 0.35rem; }
.head { display: flex; align-items: center; gap: 0.3rem; }
.num .head, .num .colfilter { justify-content: flex-end; }
.icon { text-decoration: none; padding: 0 0.2rem; border-radius: 3px; }
.icon.on { background: #e7e5e4; }
input, select, button { font: inherit; color: inherit; }
input[type=number] { width: 5rem; }
input[type=text] { width: 8rem; }
table { border-collapse: collapse; min-width: 100%; width: max-content; margin: 0.4rem 0; }
.wrap { overflow-x: auto; }
th, td { text-align: left; padding: 0.28rem 0.5rem; border-bottom: 1px solid #e7e5e4;
         vertical-align: top; white-space: nowrap; }
th { font-weight: 600; }
.num { text-align: right; font-variant-numeric: tabular-nums; }
a { color: #1d4ed8; }
"""
