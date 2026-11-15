# Agent instructions

This repo turns Pennsylvania Department of Education (PDE) public files into a citeable, rebuildable dataset and a small LEA browser. Prefer the **refined pipeline** over the older SQLite loaders.

Deep design lives in [`docs/refined-pipeline.md`](docs/refined-pipeline.md). Cursor rules under [`.cursor/rules/`](.cursor/rules/) are the short, enforceable version.

## Goals

1. **Cite the source.** Every refined fact row has a `document_id` that resolves to the URL (and retained bytes) it came from.
2. **Rebuild from the catalog.** `sources/catalog.toml` + `pip install -e .` + `python -m pa_edu.refine` rebuilds `data/refined/*.parquet`. The repo does not ship data.
3. **Keep raw bytes.** Downloads land under `data/raw/<source_id>/<sha256>/`. A later PDE edit does not erase what we already fetched.
4. **Stable only when the layout is known.** Catalog status `stable` is parsed unattended. `review` is downloaded and left alone until a human confirms the layout.
5. **Show published grain, not invented rollups.** Budget and AFR are different files. Do not add them. Do not melt parent and child accounts into the same sum.

## Architecture

```text
sources/catalog.toml     known documents (URL, parser, stable|review, school_year)
sources/checks.toml      AUNs / cells that must round-trip from workbook → parquet
pa_edu/extract.py        workbook bytes → one table per sheet, beside data/raw
pa_edu/parse_*.py        one parser family per source shape
pa_edu/refine.py         download → extract stable workbooks → refined parquet
pa_edu/check.py          offline identity, grain, and cell checks against the workbooks
pa_edu/serve.py          refined Parquet over HTTP, and /status for the data service
sql/model.sql            DuckDB views over local parquet
sql/portal.sql           convenience views (school district, fund 10, labeled lines)
pa_edu/portal.py         download page: Parquet, county zips, remote DuckDB
pa_edu/publish.py        parquet → pde_site/ JSON + download portal
pa_edu/web/              LEA browser UI; download.css is the portal stylesheet
```

`school_year` is the **four-digit start year** (`2024` = 2024–25). Take it from the catalog entry, not from a workbook header string.

`check`, `refine`, and `personnel` write a run record under `data/status/runs.json` (on the data host, `/var/pde/status/runs.json`). The data service reads it at `/` and `/status.json`. That page does not serve workbooks or the data directory path.

Commands (always use `.venv/bin/python`):

| Command | Role |
| --- | --- |
| `python -m pa_edu.refine` | Fetch missing raw files, extract sheets, build parquet / duckdb from the extracts |
| `python -m pa_edu.check` | Offline checks; cell round-trip still opens the workbook |
| `python -m pa_edu.discover` | Print uncataloged links on watched PDE pages |
| `python -m pa_edu.publish` | Build `pde_site/` from local parquet, or from `PDE_REFINED_URL` on the education job |
| `pytest tests/` | Tiny fixture workbooks for parsers and publish helpers |

`pa.gov` returns 403 without the project User-Agent in `pa_edu.common.HEADERS`.

## Legacy vs refined

- **Refined path** (`refine` / `check` / `publish` / `pa_edu/web`) is the active product.
- **Legacy path** (`pa_edu.load`, `budget.py`, Dash `pa_edu.app`, notebooks under `data_acquisition/`) still exists. Do not extend it for new sources unless asked. New finance / tax / index data goes through the catalog and a `parse_*.py`.

## Site

- Edit `pa_edu/web/`, not the generated `pde_site/` (gitignored).
- Live URL: https://pdenumbers.org/
- After JS/CSS changes, bump the `?v=` query on `pa_edu/web/index.html` so browsers pick up the new file (nginx sends no Cache-Control).
- Keep the source-code footnote in `index.html` (`site-foot`) so every view links to https://github.com/bobruddy/pa_education_data.
- Sidecar series (Act 1, millage) attach only onto years that already exist from enrollment / budget / actuals. Do not invent years that only have the sidecar.

## Download portal

`/download/` is a separate page from the LEA browser. `publish` writes it. A change that adds or reshapes a refined table updates the portal in the same commit.

- Add a one-line description to `TABLES` in `pa_edu/portal.py`. `TABLES` must match `refine.COLUMNS`. A parquet file with no entry fails the build.
- A table with `aun` is packed into the LEA's directory county. A table with no `aun` is a lookup copied whole into every county zip: add it to `LOOKUP_TABLES`. Anything else fails the build.
- Convenience views live in `sql/portal.sql` (`-- view:`, `-- needs:`, `-- about:`). `refine` applies that file after `sql/model.sql`. Keep published grain. Budget and actuals stay apart. A view does not add a parent account to its children.
- Links from the LEA browser to `download/` use class `site-link`, or `app.js` will swallow them. Portal CSS is `pa_edu/web/download.css`. Bump `ASSET_VERSION` in `portal.py` when that file changes.
- `python -m pa_edu.portal` writes a local preview whose DuckDB reads local files. The database `publish` writes reads `https://pdenumbers.org/download/tables/`. Do not copy that preview database into the image.

## Agent working agreements

- Do not commit or push unless Robert asks.
- Do not edit `docs/` unless he asks (this `AGENTS.md` and `.cursor/rules/` are the standing exception for agent guidance).
- Do not kill an interactive `duckdb` session locking `data/pde.duckdb`. Parquet can still be written; `check` and `publish` read parquet.
- Prefer proving numbers from the workbook or live JSON over asserting the UI “should” show them.
- A push to `main` runs the education job: `pytest`, then a data image whose container on docker09 mounts `blackhole:/mnt/tank04/pde_data` at `/var/pde`. That container is the only writer. The job runs `refine`, `personnel`, and `check` inside it, then `python -m pa_edu.publish` with `PDE_REFINED_URL=http://192.168.10.116:8091/refined`. Publish does not read `/home/jenkins/pde-data`. It writes `pde_site/` and does not copy it to elm. The job then pushes `192.168.150.59:443/pdenumbers:<git sha>` and `pdenumbers:latest`, and `scripts/docker09.sh` starts `pdenumbers` on port 8090 if it is absent, or replaces that container if it is already running. The data service stays on port 8091. UAT is http://192.168.10.116:8090/. Do not run publish from an agent session, do not rsync to elm, and do not copy `data/` from the laptop. A push does not change https://pdenumbers.org/. That container moves only from Jenkins job `pdenumbers-install` (parameter `tag`, default `latest`, or a 40-character git sha) or `scripts/elm.sh`.
- Workbooks, raw extracts, and refined tables stay on the NFS share mounted only into the data container. Replacing the education workspace does not delete them. `refine` downloads a catalog file the container does not already have, writes the sheet extract, and rebuilds the refined tables from that extract. `personnel` does the same for staff workbooks. A raw file already on disk is not fetched again, and a warm run does not open Excel. `check` still opens the workbook. The site image is the nginx site: LEA JSON, county packages, and view definitions. It does not contain the workbooks, the extracts, or the refined tables.
- When a change must be checked on UAT, push to `main`, wait for the education job, and verify http://192.168.10.116:8090/. Bump `index.html`’s `?v=` before that push when JS or CSS changed. https://pdenumbers.org/ stays on the installed tag until Robert runs `pdenumbers-install`. Do not run that job unless he asks.
