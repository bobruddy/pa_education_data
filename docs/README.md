# Documentation

This tree documents how PDE public files become the citeable dataset behind [pdenumbers.org](https://pdenumbers.org/).

## Current (refined pipeline)

| Doc | Role |
| --- | --- |
| [Refined pipeline](refined-pipeline.md) | Catalog, raw cache, parsers, Parquet tables, DuckDB views, checks, and what is in / out of scope |
| [`AGENTS.md`](../AGENTS.md) | Short working agreement for people and agents touching the repo |
| [`.cursor/rules/`](../.cursor/rules/) | Enforceable Cursor rules (pipeline, site publish, tests) |

Commands that matter day to day:

```bash
python -m pa_edu.refine
python -m pa_edu.check
python -m pa_edu.discover
python -m pa_edu.publish
pytest tests/
```

Remote: [github.com/bobruddy/pa_education_data](https://github.com/bobruddy/pa_education_data). Live site: https://pdenumbers.org/.

## Legacy (SQLite / Dash / notebooks)

These pages describe the 2021–2022 notebook loaders and the Dash sunburst that predate the refined path. They are kept so the old flow is still readable; new work does not extend them.

| Doc | Role |
| --- | --- |
| [Data pipeline](data-pipeline.md) | Notebook download / melt / SQLite write for enrollment and GFB |
| [Database and lookups](database-and-lookups.md) | `data/pde.db` tables and the hand-built account-code map |
| [Analysis app](analysis.md) | Dash expense-per-enrollment chart |
| [Personnel salaries](personnel.md) | Professional-staff salary files (still used at publish for the Staff tab) |
| [Runtime and gaps](runtime-and-gaps.md) | Docker, Jenkins, and historical breakage notes |

Scratch notebooks and JSON under [`analysis/`](../analysis/) are local explorations, not the published site.
