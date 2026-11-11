# Tools for analyzing PA Department of Education (PDE) public data

Notebooks and a small Python package download PDE spreadsheets, line them up across years, and chart General Fund Budget spending per enrolled student. The repo does not ship the data. Loaders write it under `data/`, which is gitignored.

## Run locally

Python 3.14 is what this was brought back up on. The system `python3` may be newer than the wheels for pandas.

```bash
python3.14 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m pa_edu.load
python -m pa_edu.personnel
python -m pa_edu.app
```

`python -m pa_edu.refine` rebuilds the Parquet tables and `data/pde.duckdb` from the catalog in `sources/catalog.toml`. `python -m pa_edu.check` compares that rebuild to the cached workbooks. The first refine needs the network. A later refine uses `data/raw/`.

`python -m pa_edu.publish` writes the LEA browser to `pde_site/` from those Parquet tables and rsyncs it to `/data/pdenumbers/htdocs/` on elm. nginx serves it at https://pdenumbers.org. The address bar holds the county, LEA, the Financials year, budget drill, and filters, and Share copies that URL. Other LEA tabs use the latest published year for each series.

The load step caches workbooks under `data/raw/` and rebuilds `data/pde.db`. `python -m pa_edu.personnel` loads only the professional-staff salary files. The app listens on http://127.0.0.1:8050.

Enrollment currently covers school years 2007–08 through whatever the public-school enrollment page publishes. Budget covers the General Fund Budget files on the current GFB data page (2017–18 onward as of 2026). The chart offers years that exist in both. See `docs/` for the table layout and the account-code map. 
