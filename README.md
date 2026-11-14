# PA education data

Public [Pennsylvania Department of Education](https://www.education.pa.gov/) files → citeable Parquet tables → a small LEA browser at [pdenumbers.org](https://pdenumbers.org/).

The active path is the **refined pipeline**: a checked-in catalog of source URLs, parsers that keep PDE’s published grain, offline checks that round-trip cells back to the workbooks, and a static site built from the Parquet. The repo does not ship the data.

Source: [github.com/bobruddy/pa_education_data](https://github.com/bobruddy/pa_education_data) · License: GPL-3.0

## What you get

| Piece | Role |
| --- | --- |
| `sources/catalog.toml` | Known documents (URL, parser, `stable` / `review`, school year) |
| `sources/checks.toml` | AUNs and cells that must match the cached workbook |
| `pa_edu/parse_*.py` | One parser family per source shape |
| `python -m pa_edu.refine` | Fetch missing raw files, parse `stable`, write Parquet (+ DuckDB views) |
| `python -m pa_edu.check` | Offline identity, grain, and cell checks |
| `python -m pa_edu.publish` | Build `pde_site/`. The education job runs this after refreshing `data/`, then ships the image. |
| `pa_edu/web/` | Source of truth for the LEA browser UI |

Refined coverage today includes EdNA LEAs, General Fund Budget expenditures, AFR actuals (LEA and school), public-school enrollment (with gender/race cuts), PSSA/Keystone district proficiency, Act 1 indexes, real-estate tax mills, charter ADM, home-education counts, and professional-staff salaries. Staff tables are written by `python -m pa_edu.personnel` and attached at publish time.

## Run locally

Python 3.11+ (this tree was brought back up on 3.14). Use the project venv; `pa.gov` needs the User-Agent in `pa_edu.common.HEADERS`.

```bash
python3.14 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

python -m pa_edu.refine    # first run needs the network; later runs use data/raw/
python -m pa_edu.check     # offline, against the local cache
pytest tests/
```

Raw bytes land under `data/raw/<source_id>/<sha256>/`. Refined tables under `data/refined/*.parquet`. DuckDB views from `sql/model.sql` live in `data/pde.duckdb`. All of `data/` is gitignored.

`school_year` is the **four-digit start year** (`2024` = 2024–25). It comes from the catalog entry, not from a workbook header string.

## Deploy

A push to `main` runs the job on the education build host. The job runs the tests, then `refine`, `personnel`, and `check` inside the data container on docker09, then `python -m pa_edu.publish` against that service. It pushes `192.168.150.59:443/pdenumbers:<git sha>` and the same image as `pdenumbers:latest`, then updates the site container on docker09. It does not copy files to elm and it does not change https://pdenumbers.org/.

`scripts/docker09.sh <sha>` pulls that image. It starts `pdenumbers` on port 8090 if the container is absent, and replaces it if it is already there. The site is http://192.168.10.116:8090/. The data service is a separate container, `scripts/docker09-data.sh`, on port 8091. It mounts `blackhole:/mnt/tank04/pde_data` at `/var/pde`.

https://pdenumbers.org/ is the elm container. Jenkins job `pdenumbers-install` is the button that moves it. Leave the parameter at `latest` to install the newest push, or paste a 40-character git sha to install that build. `scripts/elm.sh` does the same thing from a shell on education. The tag in use is `/data/pdenumbers/.env` (`PDENUMBERS_TAG`). The `latest` push in the Jenkinsfile takes effect on the next build after this file is on `main`.

`data/` is not in git. Workbooks, sheet extracts, and refined tables live on the NFS share. The education job does not keep them under `/home/jenkins/pde-data`, and they are not copied into the site image. Publish reads the refined tables from `http://192.168.10.116:8091/refined`.

## Site

Edit `pa_edu/web/`, not the generated `pde_site/` (gitignored). After JS/CSS changes, bump the `?v=` query on `pa_edu/web/index.html` so browsers pick up the new file.

The browser is county → LEA, with Overview, Financials, Staff, Enrollment, PSSA, and Keystone. The address bar holds the selection; Share copies that URL. Every figure cites the PDE workbook URL it came from.

## Design rules (short)

1. **Cite the source.** Every refined fact row has a `document_id` that resolves to the URL and retained bytes.
2. **Rebuild from the catalog.** Clone + `pip install -e .` + `python -m pa_edu.refine` rebuilds the Parquet.
3. **Keep raw bytes.** A later PDE edit does not erase what was already fetched.
4. **Stable only when the layout is known.** `review` is downloaded and left alone until a human confirms the layout.
5. **Show published grain.** Budget ≠ AFR. Parent accounts are not summed with their children. Empty is not zero.

Deep design: [`docs/refined-pipeline.md`](docs/refined-pipeline.md). Agent guidance: [`AGENTS.md`](AGENTS.md).

## Legacy path

The older SQLite loaders (`python -m pa_edu.load`), Dash app (`python -m pa_edu.app`), and notebooks under `data_acquisition/` still exist. Do not extend them for new sources. Historical notes for that stack live under [`docs/`](docs/) and are marked legacy.

```bash
python -m pa_edu.load       # rebuilds data/pde.db
python -m pa_edu.personnel  # professional-staff salaries into data/refined/
python -m pa_edu.app        # Dash chart at http://127.0.0.1:8050
```
