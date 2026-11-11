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
pa_edu/parse_*.py        one parser family per source shape
pa_edu/refine.py         download → parse stable → write parquet (+ duckdb views)
pa_edu/check.py          offline identity, grain, and cell checks against the cache
sql/model.sql            DuckDB views over parquet
pa_edu/publish.py        parquet → pde_site/ JSON + static files → rsync to elm
pa_edu/web/              source of truth for the LEA browser UI
```

`school_year` is the **four-digit start year** (`2024` = 2024–25). Take it from the catalog entry, not from a workbook header string.

Commands (always use `.venv/bin/python`):

| Command | Role |
| --- | --- |
| `python -m pa_edu.refine` | Fetch missing raw files, parse `stable`, write parquet / duckdb |
| `python -m pa_edu.check` | Offline checks against `data/raw` + parquet |
| `python -m pa_edu.discover` | Print uncataloged links on watched PDE pages |
| `python -m pa_edu.publish` | Build `pde_site/` and rsync to `elm:/data/pdenumbers/htdocs/` |
| `pytest tests/` | Tiny fixture workbooks for parsers and publish helpers |

`pa.gov` returns 403 without the project User-Agent in `pa_edu.common.HEADERS`.

## Legacy vs refined

- **Refined path** (`refine` / `check` / `publish` / `pa_edu/web`) is the active product.
- **Legacy path** (`pa_edu.load`, `budget.py`, Dash `pa_edu.app`, notebooks under `data_acquisition/`) still exists. Do not extend it for new sources unless asked. New finance / tax / index data goes through the catalog and a `parse_*.py`.

## Site

- Edit `pa_edu/web/`, not the generated `pde_site/` (gitignored).
- Live URL: https://pdenumbers.org/
- After JS/CSS changes, bump the `?v=` query on `pa_edu/web/index.html` so browsers pick up the new file (nginx sends no Cache-Control).
- Sidecar series (Act 1, millage) attach only onto years that already exist from enrollment / budget / actuals. Do not invent years that only have the sidecar.

## Agent working agreements

- Do not commit or push unless Robert asks.
- Do not edit `docs/` unless he asks (this `AGENTS.md` and `.cursor/rules/` are the standing exception for agent guidance).
- Do not kill an interactive `duckdb` session locking `data/pde.duckdb`. Parquet can still be written; `check` and `publish` read parquet.
- Prefer proving numbers from the workbook or live JSON over asserting the UI “should” show them.
- When a feature must be visible on elm, rebuild locally, deploy (publish or rsync of `pde_site/`), and verify the public URL.
