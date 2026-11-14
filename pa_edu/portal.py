"""Download portal for the refined tables.

`python -m pa_edu.publish` writes this under `pde_site/download/` and deploys it
with the LEA browser. The DuckDB file's views read the Parquet URLs on
https://pdenumbers.org. Publish binds each view's columns from the local
Parquet, so a new table can be created before that URL is on the site.

`python -m pa_edu.portal` builds the same directory locally and points the
DuckDB file at the local Parquet copies.
"""

from __future__ import annotations

import html
import json
import re
import shutil
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

import duckdb

from pa_edu.common import DATA_DIR, ROOT

PUBLIC_SITE = "https://pdenumbers.org"
PUBLIC_TABLE_ROOT = f"{PUBLIC_SITE}/download/tables"
DUCKDB_NAME = "pdenumbers.duckdb"
ASSET_VERSION = "20261114a"
WEB_CSS = Path(__file__).resolve().parent / "web" / "download.css"
PORTAL_SQL = ROOT / "sql" / "portal.sql"
_NAME = re.compile(r"^[a-z][a-z0-9_]*$")

# Statewide dimensions copied whole into every county zip. Fact tables are
# limited to AUNs whose directory county is that county.
LOOKUP_TABLES = frozenset({
    "document",
    "grade",
    "account",
    "revenue_account",
    "chart_description",
    "act1_base",
})

# Insertion order is the order on the portal page.
TABLES: dict[str, str] = {
    "document": "One row per retained source file. Join on document_id for source_url.",
    "lea": "One row per AUN from the EdNA directory. County is the administrative office.",
    "lea_year": "Name and county printed on a finance file for that AUN and year.",
    "school": "AUN and school number, with the school name from the newest enrollment year.",
    "grade": "Grade code, label, and band.",
    "account": "Chart of accounts names for a function code and an object code.",
    "revenue_account": "Revenue account names and rollup codes.",
    "chart_description": "Chart-of-accounts heading (name) and the paragraph under it (description) for a function, object, or revenue code.",
    "gfb_expenditure": "General Fund Budget expenditure. One reported amount. This is the adopted budget, not an actual.",
    "gfb_revenue": "General Fund Budget revenue. One reported amount.",
    "afr_expenditure": "Annual Financial Report expenditure, all funds, at the published account grain.",
    "afr_expenditure_school": "School-level AFR expenditure for the years PDE published a building file.",
    "afr_revenue": "Annual Financial Report revenue. The amount columns are separate published fields.",
    "enrollment": "Public-school enrollment. One grade cell. Gender and race are other tables.",
    "enrollment_gender": "The same enrollment broken out by Female and Male.",
    "enrollment_race": "LEA enrollment by race and grade. This table has no school number.",
    "enrollment_low_income": "Low-income enrollment and the percentage PDE published.",
    "enrollment_iep": "IEP enrollment and the percentage PDE published.",
    "assessment_result": "PSSA and Keystone results. Each student group is its own row.",
    "cohort_graduation": "Cohort graduation counts and rate for an AUN, year, and span.",
    "cohort_graduation_group": "Cohort graduation rate by student group.",
    "act1_index": "Act 1 adjusted index for a school district and year.",
    "act1_base": "Statewide Act 1 base index for a year.",
    "real_estate_tax": "Real-estate millage by AUN, year, county, and locality.",
    "charter_adm": "Charter average daily membership PDE published for a district and year.",
    "home_education": "Home-education affidavit counts PDE published for a district and year.",
    "professional_assignment": "One assignment for a person at an LEA in a year. Annual salary is that person's total at the LEA and is repeated on every assignment.",
    "professional_staff": "One person at an LEA in a year, so salary can be summed. The row is the primary assignment, or the highest FTE when PDE did not mark one.",
}


@dataclass(frozen=True)
class PortalView:
    name: str
    needs: tuple[str, ...]
    about: str
    sql: str


@dataclass(frozen=True)
class TableFile:
    name: str
    about: str
    rows: int
    nbytes: int


@dataclass(frozen=True)
class CountyFile:
    name: str
    slug: str
    leas: int
    nbytes: int


def load_views(sql: str | None = None) -> list[PortalView]:
    text = PORTAL_SQL.read_text(encoding="utf-8") if sql is None else sql
    views: list[PortalView] = []
    name = ""
    needs: list[str] = []
    about = ""
    body: list[str] = []

    def finish() -> None:
        if not name:
            return
        statement = "\n".join(body).strip()
        if not statement:
            raise SystemExit(f"portal view {name} has no SQL")
        if not _NAME.fullmatch(name):
            raise SystemExit(f"portal view name {name!r} is not a plain identifier")
        views.append(PortalView(name, tuple(needs), about, statement))

    for line in text.splitlines():
        if line.startswith("-- view:"):
            finish()
            name = line.split(":", 1)[1].strip()
            needs = []
            about = ""
            body = []
        elif name and line.startswith("-- needs:"):
            needs = [part.strip() for part in line.split(":", 1)[1].split(",") if part.strip()]
        elif name and line.startswith("-- about:"):
            about = line.split(":", 1)[1].strip()
        elif name and not line.startswith("--"):
            body.append(line)
    finish()
    if not views:
        raise SystemExit(f"{PORTAL_SQL} has no views")
    return views


def views_for(tables: list[str], views: list[PortalView] | None = None) -> list[PortalView]:
    available = set(tables)
    chosen: list[PortalView] = []
    for view in views if views is not None else load_views():
        if all(need in available for need in view.needs):
            chosen.append(view)
            available.add(view.name)
    return chosen


def schema_sql(
    parquet_base: str,
    tables: list[str],
    views: list[PortalView] | None = None,
    schemas: dict[str, str] | None = None,
) -> str:
    """CREATE statements for base tables and the useful views.

    `parquet_base` is a URL or directory, with no trailing slash. An empty
    string means each view reads `name.parquet` from the working directory.
    `schemas` maps a table to a DuckDB `MAP { ... }` of column types. Publish
    passes that so DuckDB can create a public URL view before the file is online.
    """
    lines = [
        "-- Views over the refined Parquet tables.",
        "-- Join document on document_id for the workbook URL of a row.",
        "",
    ]
    if parquet_base.startswith("http"):
        lines.extend([
            "INSTALL httpfs;",
            "LOAD httpfs;",
            "",
        ])
    for name in tables:
        _require_name(name)
        clause = ""
        if schemas is not None:
            if name not in schemas:
                raise SystemExit(f"{name} has no column schema")
            clause = f", schema={schemas[name]}"
        lines.append(
            f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM read_parquet('{_parquet_ref(parquet_base, name)}'{clause});"
        )
    lines.append("")
    for view in views_for(tables, views):
        if view.about:
            lines.append(f"-- {view.about}")
        lines.append(view.sql if view.sql.endswith(";") else view.sql + ";")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_duckdb(
    database: Path,
    parquet_base: str,
    tables: list[str],
    *,
    search_path: Path | None = None,
    extension_directory: Path | None = None,
    schema_from: Path | None = None,
) -> None:
    """Create a DuckDB file whose views read `parquet_base`.

    Without `schema_from`, an HTTP base is retried. DuckDB reads each Parquet
    footer while it creates the view, so those URLs have to respond first.
    `schema_from` is a directory of local `<table>.parquet` files. Publish
    passes the tables it just wrote. The view still names the public URL, and
    the column types come from the local file, so a new table does not have to
    be on the site yet.
    """
    schemas = _column_schemas(schema_from, tables) if schema_from is not None else None
    attempts = 5 if parquet_base.startswith("http") and schemas is None else 1
    for attempt in range(attempts):
        try:
            _write_duckdb_once(
                database,
                parquet_base,
                tables,
                search_path=search_path,
                extension_directory=extension_directory,
                schemas=schemas,
            )
            return
        except duckdb.Error as error:
            message = str(error)
            retry = attempt + 1 < attempts and ("HTTP" in message or "404" in message)
            if not retry:
                raise
            time.sleep(2)


def build_portal(out: Path, refined: Path) -> None:
    """Write tables, county zips, schema.sql, and index.html. Not the public DuckDB file."""
    out = out.resolve()
    refined = refined.resolve()
    if out in {ROOT.resolve(), (ROOT / "pde_site").resolve()}:
        raise SystemExit("portal output must be the download directory, not the site root")
    lea_path = refined / "lea.parquet"
    if not lea_path.exists():
        raise SystemExit(f"{lea_path} is missing")
    present = _present(refined)
    _reject_unknown(refined)

    if out.exists():
        shutil.rmtree(out)
    table_dir = out / "tables"
    table_dir.mkdir(parents=True)
    connection = duckdb.connect()
    try:
        _reject_duplicate_auns(connection, lea_path)
        copied = [_copy_table(connection, refined / f"{name}.parquet", table_dir / f"{name}.parquet", name) for name in present]
        _validate(table_dir, present)
        counties = _county_packages(connection, out / "counties", refined, present)
        unassigned = _unassigned(connection, lea_path)
    finally:
        connection.close()

    chosen = views_for(present)
    (out / "schema.sql").write_text(schema_sql(PUBLIC_TABLE_ROOT, present, chosen), encoding="utf-8")
    shutil.copyfile(WEB_CSS, out / "download.css")
    page = render_html(copied, chosen, counties, unassigned)
    (out / "index.html").write_text(page, encoding="utf-8")
    manifest = {
        "tables": [
            {"name": item.name, "rows": item.rows, "bytes": item.nbytes, "file": f"tables/{item.name}.parquet"}
            for item in copied
        ],
        "views": [{"name": view.name, "about": view.about} for view in chosen],
        "counties": [
            {
                "name": item.name,
                "slug": item.slug,
                "leas": item.leas,
                "bytes": item.nbytes,
                "file": f"counties/{item.slug}.zip",
            }
            for item in counties
        ],
        "duckdb": DUCKDB_NAME,
        "unassigned": unassigned,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"portal: {len(copied)} tables, {len(counties)} counties -> {out}")


def render_html(
    tables: list[TableFile],
    views: list[PortalView],
    counties: list[CountyFile],
    unassigned: list[dict[str, str]],
) -> str:
    unassigned_note = ""
    if unassigned:
        names = ", ".join(
            f"{html.escape(row['lea_name'])} ({html.escape(row['aun'])})" for row in unassigned
        )
        unassigned_note = (
            f"<p class=\"note\">These directory rows have no county, so they stay in the full tables only: {names}.</p>"
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PDE data download</title>
<link rel="stylesheet" href="download.css?v={ASSET_VERSION}">
</head>
<body>
<a class="skip" href="#content">Skip to content</a>
<header class="top">
  <div class="top-row">
    <a class="brand" href="../">PDE data</a>
    <p class="brand-note">Download</p>
  </div>
</header>
<main id="content">
  <h1>Download the tables</h1>
  <p class="lede">Refined Pennsylvania Department of Education tables behind the LEA browser. One Parquet file per table, a zip for each county, and a DuckDB file of views that reads the Parquet on this site.</p>
  <p class="contents">
    <a href="#database">Database</a>
    <a href="#views">Views</a>
    <a href="#tables">Tables</a>
    <a href="#counties">Counties</a>
  </p>

  <h2 id="database">Database</h2>
  <p><a href="{DUCKDB_NAME}">{DUCKDB_NAME}</a> is the view definitions. The rows stay in the Parquet files. Querying it needs a network connection. <a href="schema.sql">schema.sql</a> is those same views.</p>
  <pre>INSTALL httpfs;
LOAD httpfs;

SELECT lea_name, county
FROM school_district
WHERE county = 'Fayette'
ORDER BY lea_name;</pre>
  <p class="note">Open the file with DuckDB 1.1 or newer (<code>duckdb {DUCKDB_NAME}</code>). The first query downloads the httpfs extension if it is not installed yet. Join <code>document</code> on <code>document_id</code> for the workbook URL of a row.</p>
  <pre>-- Albert Gallatin Area SD. Sum of school headcounts from grade cells.
SELECT school_year, sum(enrollment) AS enrollment
FROM enrollment_headcount
WHERE aun = '101260303'
GROUP BY school_year
ORDER BY school_year;

SELECT function_code, function_name, object_code, object_name, program_code, amount
FROM gfb_line
WHERE aun = '101260303' AND school_year = 2024
ORDER BY function_code, object_code, program_code;</pre>

  <h2 id="views">Views</h2>
  <p class="note">Names and counties on the labeled finance views come from the current directory, one row per AUN. The name PDE printed on that year's finance file is <code>lea_year</code>. Expenditure rows keep the published account grain, including a rollup code PDE printed beside the detail codes. Sum the detail codes, or sum a rollup column. <code>enrollment_headcount</code> adds grade cells within a school. Gender, race, and the county workbook are separate published counts.</p>
  {_view_table(views)}

  <h2 id="tables">Tables</h2>
  <p class="note">A reported zero is a row. A cell PDE did not publish is absent from the file.</p>
  {_table_table(tables)}

  <h2 id="counties">County packages</h2>
  <p class="note">Each zip is the tables above for LEAs whose directory county is that county, open and closed, every category. Millage rows stay with the LEA's directory county when PDE also names another county on the rate. Lookup tables are copied whole so joins still resolve: {html.escape(", ".join(item.name for item in tables if item.name in LOOKUP_TABLES))}.</p>
  <p class="note">Unzip a package and open it from that folder: <code>duckdb county.duckdb</code>. The views then read the Parquet files next to the database.</p>
  {_county_list(counties)}
  {unassigned_note}
</main>
<footer class="site-foot">
  <div class="site-foot-row">
    <div class="site-foot-notes">
      <p>Source code: <a href="https://github.com/bobruddy/pa_education_data">github.com/bobruddy/pa_education_data</a></p>
      <p><a href="../">LEA browser</a></p>
    </div>
    <p class="site-stamp" id="build-stamp" hidden>
      <span>Commit <a href="https://github.com/bobruddy/pa_education_data"></a></span>
      <span data-committed></span>
      <span data-built></span>
    </p>
  </div>
</footer>
<script type="module" src="../stamp.js?v={ASSET_VERSION}"></script>
</body>
</html>
"""


def main() -> None:
    out = ROOT / "pde_site" / "download"
    refined = DATA_DIR / "refined"
    build_portal(out, refined)
    present = _present(out / "tables")
    write_duckdb(out / DUCKDB_NAME, (out / "tables").resolve().as_posix(), present)
    print(f"local {DUCKDB_NAME} reads {(out / 'tables').resolve()}")
    print("python -m pa_edu.publish replaces it with views that read https://pdenumbers.org/download/tables/")


def _column_schemas(directory: Path, tables: list[str]) -> dict[str, str]:
    connection = duckdb.connect()
    try:
        schemas = {}
        for name in tables:
            _require_name(name)
            path = directory / f"{name}.parquet"
            if not path.exists():
                raise SystemExit(f"{path} is missing")
            schemas[name] = _schema_map(connection, path)
        return schemas
    finally:
        connection.close()


def _schema_map(connection: duckdb.DuckDBPyConnection, path: Path) -> str:
    rows = connection.execute(
        "DESCRIBE SELECT * FROM read_parquet(?)",
        [str(path)],
    ).fetchall()
    if not rows:
        raise SystemExit(f"{path.name} has no columns")
    entries = []
    for name, typ, *_rest in rows:
        _require_name(str(name))
        entries.append(
            "{key}: {{'name': {key}, 'type': {typ}, 'default_value': NULL}}".format(
                key=_sql_string(str(name)),
                typ=_sql_string(str(typ)),
            )
        )
    return "MAP {" + ", ".join(entries) + "}"


def _write_duckdb_once(
    database: Path,
    parquet_base: str,
    tables: list[str],
    *,
    search_path: Path | None,
    extension_directory: Path | None,
    schemas: dict[str, str] | None = None,
) -> None:
    database.parent.mkdir(parents=True, exist_ok=True)
    if database.exists():
        database.unlink()
    config: dict[str, str] = {}
    if extension_directory is not None:
        extension_directory.mkdir(parents=True, exist_ok=True)
        config["extension_directory"] = str(extension_directory)
        config["home_directory"] = str(extension_directory)
    connection = duckdb.connect(str(database), config=config)
    try:
        if parquet_base == "":
            if search_path is None:
                raise SystemExit("relative parquet views need search_path")
            connection.execute(f"SET file_search_path = {_sql_string(search_path.resolve().as_posix())}")
        elif parquet_base.startswith("http"):
            connection.execute("INSTALL httpfs")
            connection.execute("LOAD httpfs")
        connection.execute(schema_sql(parquet_base, tables, schemas=schemas))
    except Exception:
        connection.close()
        database.unlink(missing_ok=True)
        wal = Path(str(database) + ".wal")
        wal.unlink(missing_ok=True)
        raise
    else:
        connection.close()


def _validate(table_dir: Path, tables: list[str]) -> None:
    with tempfile.TemporaryDirectory(prefix="pde-portal-check-") as tmp:
        database = Path(tmp) / "check.duckdb"
        write_duckdb(database, table_dir.resolve().as_posix(), tables)
        connection = duckdb.connect(str(database), read_only=True)
        try:
            names = [row[0] for row in connection.execute(
                "SELECT view_name FROM duckdb_views() WHERE NOT internal"
            ).fetchall()]
            for name in names:
                _require_name(name)
                connection.execute(f"SELECT * FROM {name} LIMIT 1").fetchall()
        finally:
            connection.close()


def _present(directory: Path) -> list[str]:
    found = {path.stem for path in directory.glob("*.parquet")}
    return [name for name in TABLES if name in found]


def _reject_unknown(refined: Path) -> None:
    extra = sorted(path.name for path in refined.glob("*.parquet") if path.stem not in TABLES)
    if extra:
        raise SystemExit("refined parquet has no portal entry: " + ", ".join(extra))


def _reject_duplicate_auns(connection: duckdb.DuckDBPyConnection, lea_path: Path) -> None:
    duplicates = connection.execute(
        f"""
        SELECT aun
        FROM read_parquet({_sql_string(lea_path.as_posix())})
        GROUP BY aun
        HAVING count(*) > 1
        LIMIT 5
        """
    ).fetchall()
    if duplicates:
        listed = ", ".join(str(row[0]) for row in duplicates)
        raise SystemExit(f"lea.aun is not unique: {listed}")


def _copy_table(connection: duckdb.DuckDBPyConnection, source: Path, dest: Path, name: str) -> TableFile:
    shutil.copyfile(source, dest)
    rows = connection.execute(
        f"SELECT count(*) FROM read_parquet({_sql_string(dest.as_posix())})"
    ).fetchone()
    return TableFile(name, TABLES[name], int(rows[0]), dest.stat().st_size)


def _county_packages(
    connection: duckdb.DuckDBPyConnection,
    out: Path,
    refined: Path,
    present: list[str],
) -> list[CountyFile]:
    lea_path = refined / "lea.parquet"
    counted = connection.execute(
        f"""
        SELECT county, count(*)
        FROM read_parquet({_sql_string(lea_path.as_posix())})
        WHERE county IS NOT NULL AND county <> ''
        GROUP BY county
        ORDER BY county
        """
    ).fetchall()
    counties = [(str(name), int(count)) for name, count in counted]
    for name, _count in counties:
        if not re.fullmatch(r"[A-Za-z][A-Za-z .'-]*", name):
            raise SystemExit(f"county {name!r} cannot be a package file name")
    slugs: dict[str, str] = {}
    for name, _count in counties:
        slug = county_slug(name)
        if slug in slugs:
            raise SystemExit(f"counties {slugs[slug]!r} and {name!r} share the slug {slug}")
        slugs[slug] = name
    connection.execute(
        f"""
        CREATE TEMP TABLE _portal_lea AS
        SELECT aun, county
        FROM read_parquet({_sql_string(lea_path.as_posix())})
        WHERE county IS NOT NULL AND county <> ''
        """
    )
    aun_tables = [name for name in present if name not in LOOKUP_TABLES and name != "lea"]
    for name in aun_tables:
        columns = _columns(connection, refined / f"{name}.parquet")
        if "aun" not in columns:
            raise SystemExit(f"{name} has no aun and is not a county lookup table")

    out.mkdir(parents=True)
    packages: list[CountyFile] = []
    with tempfile.TemporaryDirectory(prefix="pde-portal-counties-") as tmp_name:
        tmp = Path(tmp_name)
        partitions = {
            name: _partition_facts(connection, refined / f"{name}.parquet", tmp / name)
            for name in aun_tables
        }
        empties = {
            name: _empty_like(connection, refined / f"{name}.parquet", tmp / f"{name}.empty.parquet")
            for name in aun_tables
        }
        for name, leas in counties:
            print(f"portal: {county_slug(name)}.zip", flush=True)
            packages.append(_write_county_zip(
                connection,
                out / f"{county_slug(name)}.zip",
                tmp / "staging",
                refined,
                present,
                aun_tables,
                partitions,
                empties,
                name,
                leas,
            ))
    return packages


def _partition_facts(connection: duckdb.DuckDBPyConnection, source: Path, dest: Path) -> Path:
    connection.execute(
        f"""
        COPY (
            SELECT t.*, l.county AS _portal_county
            FROM read_parquet({_sql_string(source.as_posix())}) t
            JOIN _portal_lea l ON t.aun = l.aun
        ) TO {_sql_string(dest.as_posix())} (
            FORMAT PARQUET,
            PARTITION_BY (_portal_county),
            OVERWRITE_OR_IGNORE,
            WRITE_PARTITION_COLUMNS false
        )
        """
    )
    return dest


def _write_county_zip(
    connection: duckdb.DuckDBPyConnection,
    dest: Path,
    staging: Path,
    refined: Path,
    present: list[str],
    aun_tables: list[str],
    partitions: dict[str, Path],
    empties: dict[str, Path],
    county: str,
    leas: int,
) -> CountyFile:
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    _copy_lea(connection, refined / "lea.parquet", staging / "lea.parquet", county)
    for name in aun_tables:
        folder = partitions[name] / f"_portal_county={county}"
        target = staging / f"{name}.parquet"
        if folder.exists():
            _consolidate(connection, folder, target)
        else:
            shutil.copyfile(empties[name], target)
    lookups = [name for name in present if name in LOOKUP_TABLES]
    for name in lookups:
        shutil.copyfile(refined / f"{name}.parquet", staging / f"{name}.parquet")
    (staging / "README.txt").write_text(_readme(county, lookups), encoding="utf-8")
    write_duckdb(staging / "county.duckdb", "", present, search_path=staging)
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in present:
            archive.write(staging / f"{name}.parquet", f"{name}.parquet")
        archive.write(staging / "README.txt", "README.txt")
        archive.write(staging / "county.duckdb", "county.duckdb")
    return CountyFile(county, county_slug(county), leas, dest.stat().st_size)


def _copy_lea(connection: duckdb.DuckDBPyConnection, source: Path, dest: Path, county: str) -> None:
    connection.execute("CREATE OR REPLACE TEMP TABLE _county_name (county VARCHAR)")
    connection.execute("INSERT INTO _county_name VALUES (?)", [county])
    connection.execute(
        f"""
        COPY (
            SELECT t.*
            FROM read_parquet({_sql_string(source.as_posix())}) t
            SEMI JOIN _county_name c ON t.county = c.county
            ORDER BY ALL
        ) TO {_sql_string(dest.as_posix())} (FORMAT PARQUET)
        """
    )


def _consolidate(connection: duckdb.DuckDBPyConnection, folder: Path, dest: Path) -> None:
    sample = next(folder.glob("*.parquet"))
    columns = _columns(connection, sample)
    select = "* EXCLUDE (_portal_county)" if "_portal_county" in columns else "*"
    connection.execute(
        f"""
        COPY (
            SELECT {select}
            FROM read_parquet({_sql_string((folder / '*.parquet').as_posix())})
            ORDER BY ALL
        ) TO {_sql_string(dest.as_posix())} (FORMAT PARQUET)
        """
    )


def _empty_like(connection: duckdb.DuckDBPyConnection, source: Path, dest: Path) -> Path:
    connection.execute(
        f"""
        COPY (
            SELECT * FROM read_parquet({_sql_string(source.as_posix())}) WHERE false
        ) TO {_sql_string(dest.as_posix())} (FORMAT PARQUET)
        """
    )
    return dest


def _unassigned(connection: duckdb.DuckDBPyConnection, lea_path: Path) -> list[dict[str, str]]:
    rows = connection.execute(
        f"""
        SELECT aun, lea_name
        FROM read_parquet({_sql_string(lea_path.as_posix())})
        WHERE county IS NULL OR county = ''
        ORDER BY aun
        """
    ).fetchall()
    return [{"aun": str(aun), "lea_name": str(name)} for aun, name in rows]


def _readme(county: str, lookups: list[str]) -> str:
    lookup_line = ", ".join(lookups) if lookups else "none"
    return (
        f"{county} County\n\n"
        "Parquet extract from https://pdenumbers.org/download/\n"
        f"LEAs whose directory county is {county}. Open and closed entities of every category are included.\n"
        f"Lookup tables copied whole: {lookup_line}.\n\n"
        "Open the views from this folder:\n\n"
        "    duckdb county.duckdb\n\n"
        "    SELECT * FROM school_district ORDER BY lea_name;\n\n"
        "General Fund Budget rows and Annual Financial Report rows are separate tables.\n"
        "A missing row was not published.\n"
    )


def _columns(connection: duckdb.DuckDBPyConnection, path: Path) -> list[str]:
    rows = connection.execute(
        f"DESCRIBE SELECT * FROM read_parquet({_sql_string(path.as_posix())})"
    ).fetchall()
    return [str(row[0]) for row in rows]


def county_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
    if not slug:
        raise SystemExit(f"county {name!r} has an empty file name")
    return slug


def _view_table(views: list[PortalView]) -> str:
    rows = []
    for view in views:
        rows.append(
            "<tr>"
            f"<td><div class=\"name\"><code>{html.escape(view.name)}</code></div>"
            f"<p class=\"about\">{html.escape(view.about)}</p></td>"
            "</tr>"
        )
    body = "\n".join(rows)
    return (
        "<div class=\"wrap\"><table>"
        "<thead><tr><th>View</th></tr></thead>"
        f"<tbody>{body}</tbody></table></div>"
    )


def _table_table(tables: list[TableFile]) -> str:
    rows = []
    for item in tables:
        rows.append(
            "<tr>"
            f"<td><div class=\"name\"><code>{html.escape(item.name)}</code></div>"
            f"<p class=\"about\">{html.escape(item.about)}</p></td>"
            f"<td class=\"num\">{item.rows:,}</td>"
            f"<td class=\"num\">{format_bytes(item.nbytes)}</td>"
            f"<td><a href=\"tables/{html.escape(item.name)}.parquet\">Download</a></td>"
            "</tr>"
        )
    body = "\n".join(rows)
    return (
        "<div class=\"wrap\"><table>"
        "<thead><tr><th>Table</th><th class=\"num\">Rows</th><th class=\"num\">Size</th><th></th></tr></thead>"
        f"<tbody>{body}</tbody></table></div>"
    )


def _county_list(counties: list[CountyFile]) -> str:
    items = []
    for item in counties:
        noun = "LEA" if item.leas == 1 else "LEAs"
        items.append(
            "<li>"
            f"<a href=\"counties/{html.escape(item.slug)}.zip\">{html.escape(item.name)}</a> "
            f"<span>{item.leas:,} {noun} · {format_bytes(item.nbytes)}</span>"
            "</li>"
        )
    return "<ul class=\"counties\">" + "\n".join(items) + "</ul>"


def format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024 / 1024:.1f} MB"


def _parquet_ref(base: str, name: str) -> str:
    _require_name(name)
    if base == "":
        ref = f"{name}.parquet"
    else:
        ref = f"{base.rstrip('/')}/{name}.parquet"
    return ref.replace("'", "''")


def _sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _require_name(name: str) -> None:
    if not _NAME.fullmatch(name):
        raise SystemExit(f"table name {name!r} is not a plain identifier")


if __name__ == "__main__":
    main()
