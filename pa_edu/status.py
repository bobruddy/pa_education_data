"""Status page for the data service.

``check``, ``refine``, and ``personnel`` write a run record under
``<data>/status/runs.json``. That directory is on the data volume, so the
record survives a container replace. The page reports those runs, the catalog,
and refined Parquet inventory. It does not include the data directory path
or any workbook bytes.
"""

from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq

from pa_edu.catalog import load_catalog
from pa_edu.common import DATA_DIR, ROOT

RUNS_FILE = "runs.json"
KINDS = ("check", "refine", "personnel")
MAX_ERRORS = 40
MAX_ERROR_CHARS = 500
TABLE_NAME = re.compile(r"[A-Za-z0-9_]+\.parquet")
SHA = re.compile(r"[0-9a-fA-F]{7,40}")
DOCUMENT_COLUMNS = ["catalog_id", "source_id", "retrieved_at", "school_year"]


def record_run(
    kind: str,
    *,
    ok: bool,
    data_dir: Path | None = None,
    errors: list[str] | None = None,
    error: str | None = None,
    documents: int | None = None,
    years: int | None = None,
) -> None:
    """Merge one run into the status record. Other runs stay put."""
    if kind not in KINDS:
        raise ValueError(kind)
    data_dir = data_dir or DATA_DIR
    entry: dict = {"finished_at": _now(), "ok": bool(ok)}
    if errors is not None:
        cleaned = [_clip(redact(item, data_dir)) for item in errors]
        entry["error_count"] = len(cleaned)
        entry["errors"] = cleaned[:MAX_ERRORS]
        omitted = len(cleaned) - len(entry["errors"])
        if omitted:
            entry["errors_omitted"] = omitted
    if error is not None:
        entry["error"] = _clip(redact(error, data_dir))
    if documents is not None:
        entry["documents"] = documents
    if years is not None:
        entry["years"] = years
    path = _runs_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    current = _read_runs(path)
    current.pop("_unreadable", None)
    current[kind] = entry
    temporary = path.parent / f".{RUNS_FILE}.{os.getpid()}.tmp"
    temporary.write_text(json.dumps(current, indent=2) + "\n")
    os.replace(temporary, path)


def public_error(exc: BaseException, data_dir: Path | None = None) -> str:
    data_dir = data_dir or DATA_DIR
    return redact(f"{type(exc).__name__}: {exc}", data_dir)


def redact(text: str, data_dir: Path) -> str:
    """Drop the data-directory path from a message that will be shown."""
    updated = text
    for raw in {str(data_dir), str(data_dir.resolve())}:
        if raw and raw in updated:
            updated = updated.replace(raw, "<data>")
    return updated


def status_report(data_dir: Path, catalog_path: Path | None = None) -> dict:
    loaded = _read_runs(_runs_path(data_dir))
    unreadable = bool(loaded.pop("_unreadable", False))
    report = {
        "generated_at": _now(),
        "git_sha": git_sha(),
        "runs_readable": not unreadable,
        "check": _run(loaded.get("check")),
        "refine": _run(loaded.get("refine")),
        "personnel": _run(loaded.get("personnel")),
        "catalog": catalog_posture(catalog_path),
        "refined": refined_inventory(data_dir / "refined"),
    }
    report["ok"] = _outcome(report)[0]
    return {"ok": report.pop("ok"), **report}


def git_sha() -> str | None:
    value = os.environ.get("PDE_GIT_SHA", "").strip()
    if SHA.fullmatch(value):
        return value.lower()
    return None


def catalog_posture(catalog_path: Path | None = None) -> dict:
    path = catalog_path or (ROOT / "sources" / "catalog.toml")
    entries = load_catalog(path)
    counts: dict[str, dict[str, int | str]] = {}
    for entry in entries:
        row = counts.setdefault(entry.source_id, {"source_id": entry.source_id, "stable": 0, "review": 0})
        row[entry.status] = int(row[entry.status]) + 1
    sources = [counts[key] for key in sorted(counts)]
    return {
        "stable": sum(int(row["stable"]) for row in sources),
        "review": sum(int(row["review"]) for row in sources),
        "sources": sources,
    }


def refined_inventory(refined: Path) -> dict:
    tables = []
    if refined.is_dir():
        for path in sorted(refined.glob("*.parquet")):
            if not TABLE_NAME.fullmatch(path.name):
                continue
            tables.append({
                "file": path.name,
                "rows": _row_count(path),
                "bytes": path.stat().st_size,
            })
    facts = _document_facts(refined / "document.parquet")
    return {"tables": tables, **facts}


def render_status(report: dict) -> str:
    _ok, tone, banner = _outcome(report)
    sha = report.get("git_sha")
    if sha:
        commit = (
            f'<a href="https://github.com/bobruddy/pa_education_data/commit/{html.escape(sha)}">'
            f"<code>{html.escape(sha)}</code></a>"
        )
    else:
        commit = "unavailable"
    parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="robots" content="noindex">',
        "<title>PDE data status</title>",
        f"<style>{_CSS}</style>",
        "</head>",
        "<body>",
        "<h1>PDE data</h1>",
        (
            f'<p class="meta">Generated {_text(report.get("generated_at"))}'
            f" · build {commit}"
            ' · <a href="/status.json">JSON</a>'
            ' · <a href="/refined/">refined tables</a></p>'
        ),
        f'<p class="banner {tone}">{html.escape(banner)}</p>',
        "<h2>Check</h2>",
        _check_section(report),
        "<h2>Runs</h2>",
        _runs_table(report),
        "<h2>Catalog</h2>",
        _catalog_section(report.get("catalog") or {}),
        "<h2>Refined tables</h2>",
        _refined_section(report.get("refined") or {}),
        '<p class="meta">Workbooks and raw extracts are not served here.</p>',
        "</body>",
        "</html>",
        "",
    ]
    return "\n".join(parts)


def _check_section(report: dict) -> str:
    if not report.get("runs_readable", True):
        return "<p>The run record could not be read.</p>"
    check = report.get("check")
    if not check:
        return "<p>No check has been recorded.</p>"
    errors = check.get("errors") or []
    crash = check.get("error")
    if not errors and not crash:
        return "<p>No errors recorded.</p>"
    items = "".join(f"<li>{_text(item)}</li>" for item in errors)
    if crash and crash not in errors:
        items = f"<li>{_text(crash)}</li>" + items
    omitted = int(check.get("errors_omitted") or 0)
    more = f"<p>{omitted} more not stored.</p>" if omitted else ""
    return f"<ul class=\"errors\">{items}</ul>{more}"


def _runs_table(report: dict) -> str:
    rows = []
    for kind, label in (("check", "check"), ("refine", "refine"), ("personnel", "personnel")):
        run = report.get(kind)
        if not run:
            rows.append(f"<tr><td>{label}</td><td>not recorded</td><td></td><td></td></tr>")
            continue
        state = "passed" if run.get("ok") else "failed"
        detail = _run_detail(run)
        rows.append(
            "<tr>"
            f"<td>{label}</td>"
            f"<td>{state}</td>"
            f"<td class=\"when\">{_text(run.get('finished_at'))}</td>"
            f"<td>{_text(detail)}</td>"
            "</tr>"
        )
    body = "".join(rows)
    return (
        '<div class="wrap"><table><thead><tr><th>Run</th><th>Result</th><th>Finished</th>'
        f"<th>Detail</th></tr></thead><tbody>{body}</tbody></table></div>"
    )


def _run_detail(run: dict) -> str:
    if "documents" in run:
        return f"{run['documents']} documents"
    if "years" in run:
        return f"{run['years']} years"
    if run.get("error_count"):
        return f"{run['error_count']} errors"
    if run.get("error"):
        return str(run["error"])
    return ""


def _catalog_section(catalog: dict) -> str:
    stable = catalog.get("stable", 0)
    review = catalog.get("review", 0)
    rows = []
    for source in catalog.get("sources") or []:
        rows.append(
            "<tr>"
            f"<td>{_text(source.get('source_id'))}</td>"
            f"<td class=\"num\">{_text(source.get('stable'))}</td>"
            f"<td class=\"num\">{_text(source.get('review'))}</td>"
            "</tr>"
        )
    body = "".join(rows)
    return (
        f"<p>{stable} stable, {review} review.</p>"
        '<div class="wrap"><table><thead><tr><th>Source</th><th class="num">Stable</th>'
        f'<th class="num">Review</th></tr></thead><tbody>{body}</tbody></table></div>'
    )


def _refined_section(refined: dict) -> str:
    years = refined.get("school_years") or []
    year_text = ", ".join(str(year) for year in years) if years else "none"
    newest = refined.get("newest_document")
    if newest:
        bits = [
            newest.get("catalog_id"),
            newest.get("source_id"),
            newest.get("school_year"),
            newest.get("retrieved_at"),
        ]
        newest_text = " · ".join(str(bit) for bit in bits if bit is not None and bit != "") or "none"
    else:
        newest_text = "none"
    rows = []
    for table in refined.get("tables") or []:
        name = str(table.get("file") or "")
        link = html.escape(name)
        rows.append(
            "<tr>"
            f'<td><a href="/browse/{link}">{link}</a></td>'
            f"<td class=\"num\">{_rows(table.get('rows'))}</td>"
            f"<td class=\"num\">{html.escape(_bytes(table.get('bytes')))}</td>"
            f'<td><a href="/refined/{link}">parquet</a></td>'
            "</tr>"
        )
    body = "".join(rows) or "<tr><td colspan=\"4\">No refined tables.</td></tr>"
    return (
        f"<p>School years (start year): {_text(year_text)}</p>"
        f"<p>Newest document: {_text(newest_text)}</p>"
        '<div class="wrap"><table><thead><tr><th>Table</th><th class="num">Rows</th>'
        f'<th class="num">Size</th><th>Download</th></tr></thead><tbody>{body}</tbody></table></div>'
    )


def _outcome(report: dict) -> tuple[bool, str, str]:
    """Whether the data side is current, a banner tone, and the banner text.

    A missing refine or personnel run does not fail the page. A recorded
    failure does, including when an older check still says it passed.
    """
    if not report.get("runs_readable", True):
        return False, "bad", "The run record could not be read"
    failures = []
    check = report.get("check")
    if check and not check.get("ok"):
        count = check.get("error_count")
        if not isinstance(count, int):
            count = 1 if check.get("error") else 0
        noun = "error" if count == 1 else "errors"
        failures.append(_with_when(f"Checks failed · {count} {noun}", check))
    for kind in ("refine", "personnel"):
        run = report.get(kind)
        if run and not run.get("ok"):
            failures.append(_with_when(f"{kind} failed", run))
    if failures:
        return False, "bad", "; ".join(failures)
    if not check:
        return False, "unknown", "No check has been recorded"
    return True, "ok", _with_when("Checks passed", check)


def _with_when(text: str, run: dict) -> str:
    when = str(run.get("finished_at") or "")
    if when:
        return f"{text} · {when}"
    return text


def _runs_path(data_dir: Path) -> Path:
    return data_dir / "status" / RUNS_FILE


def _read_runs(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {"_unreadable": True}
    if not isinstance(loaded, dict):
        return {"_unreadable": True}
    return loaded


def _run(value: object) -> dict | None:
    if not isinstance(value, dict) or not isinstance(value.get("ok"), bool):
        return None
    kept: dict = {"ok": value["ok"]}
    for key in ("finished_at", "error", "documents", "years"):
        if key in value and value[key] is not None:
            kept[key] = value[key]
    if isinstance(value.get("error_count"), int) and not isinstance(value.get("error_count"), bool):
        kept["error_count"] = value["error_count"]
    if isinstance(value.get("errors_omitted"), int) and not isinstance(value.get("errors_omitted"), bool):
        kept["errors_omitted"] = value["errors_omitted"]
    if isinstance(value.get("errors"), list):
        kept["errors"] = [str(item) for item in value["errors"] if item is not None]
    return kept


def _row_count(path: Path) -> int | None:
    try:
        return pq.read_metadata(path).num_rows
    except Exception:
        return None


def _document_facts(path: Path) -> dict:
    empty = {"school_years": [], "newest_document": None}
    if not path.is_file():
        return empty
    try:
        rows = pq.read_table(path, columns=DOCUMENT_COLUMNS).to_pylist()
    except Exception:
        return empty
    years = sorted({year for row in rows if (year := _year(row.get("school_year"))) is not None})
    newest = None
    best = ""
    for row in rows:
        stamp = _iso(row.get("retrieved_at")) or ""
        if newest is not None and stamp < best:
            continue
        best = stamp
        newest = {
            "catalog_id": _plain(row.get("catalog_id")),
            "source_id": _plain(row.get("source_id")),
            "retrieved_at": stamp or None,
            "school_year": _year(row.get("school_year")),
        }
    return {"school_years": years, "newest_document": newest}


def _year(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float) and value != value:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _plain(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _iso(value: object) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat(timespec="seconds")
        except TypeError:
            return value.isoformat()
    text = str(value).strip()
    return text or None


def _clip(text: str) -> str:
    if len(text) <= MAX_ERROR_CHARS:
        return text
    return text[: MAX_ERROR_CHARS - 1] + "…"


def _text(value: object) -> str:
    if value is None:
        return ""
    return html.escape(str(value))


def _rows(value: object) -> str:
    if isinstance(value, int):
        return f"{value:,}"
    return "—"


def _bytes(value: object) -> str:
    if not isinstance(value, int) or value < 0:
        return "—"
    size = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{value} B"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


_CSS = """
body { font: 15px/1.45 system-ui, sans-serif; margin: 2rem auto; max-width: 52rem;
       color: #1c1917; background: #fafaf9; padding: 0 1rem; }
h1 { font-size: 1.4rem; margin-bottom: 0.2rem; }
h2 { font-size: 1.05rem; margin: 1.4rem 0 0.4rem; }
.meta { color: #57534e; }
.banner { padding: 0.6rem 0.8rem; border-radius: 6px; }
.ok { background: #ecfdf3; color: #14532d; }
.bad { background: #fef2f2; color: #7f1d1d; }
.unknown { background: #f5f5f4; color: #44403c; }
table { border-collapse: collapse; width: 100%; margin: 0.4rem 0 0.2rem; }
.wrap { overflow-x: auto; }
th, td { text-align: left; padding: 0.28rem 0.5rem; border-bottom: 1px solid #e7e5e4;
         vertical-align: top; }
th { font-weight: 600; }
.num { text-align: right; font-variant-numeric: tabular-nums; }
.when { white-space: nowrap; }
code { font-size: 0.92em; }
a { color: #1d4ed8; }
ul.errors { padding-left: 1.2rem; }
"""
