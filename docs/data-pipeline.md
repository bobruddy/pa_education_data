# Data pipeline (legacy notebooks)

> **Legacy.** New sources go through [`refined-pipeline.md`](refined-pipeline.md) (`sources/catalog.toml` + `python -m pa_edu.refine`). This page describes the 2021–era notebooks that write `data/pde.db`.

Both acquisition notebooks do the same job in the same shape: scrape a PDE index page for `.xlsx` links, cache the files under `data/raw/`, coerce each year onto one column set, melt to long form, pickle the frame, then write SQLite tables in `data/pde.db`.

SSL verification is turned off (`ssl._create_unverified_context`) because the PDE host was failing certificate checks when this was written.

`requests` is used for the download. `beautifulsoup4` parses the index page. `openpyxl` (via pandas) reads the workbooks. None of the notebooks pin versions.

## Enrollment

Notebook: `data_acquisition/acquire_basic_enrollment.ipynb`

Index page:

`https://www.education.pa.gov/DataAndReporting/Enrollment/Pages/PublicSchEnrReports.aspx`

Links kept are those matching `Enrollment Public Schools 20xx-xx.xlsx`. Files land in `data/raw/basic_enrollment/` with the URL-decoded filename lowercased and spaces turned into underscores. A file already on disk is not downloaded again.

Sheet name and header offset change by year:

| Start year | Sheet | Rows skipped |
| --- | --- | --- |
| 2011 and later | `LEA and School` | 4 |
| 2010 | `School` | 4 |
| 2009 | `School - Data File` | 4 |
| 2008 | `School - Datafile` | 4 |
| 2007 | `LEA - Data File` | 6 |
| 2004–2006 | commented out | — |

2004, 2005, and 2006 are skipped on purpose. The notebook's own todo says those years have quality problems, mostly `lea_type` and `aun`.

### Column cleanup

Expected string columns: `LEA Name`, `LEA Type`, `County`, `School Name`, `AUN`, `School Number`.

Expected count columns, later stored as the `grade` value:

- `PKA`, `PKP`, `PKF`, `K4A`, `K4P`, `K4F`, `K5A`, `K5P`, `K5F` — pre-K, kindergarten-for-4, kindergarten-for-5, split into AM (`A`), PM (`P`), and full day (`F`). Older files that only have `PreK` / `K4` / `K5` are renamed onto the AM column.
- `001` through `012` — grades 1–12. Bare names like `1` or integer `7` are zero-padded.

Other fixes applied before the frames are stacked:

- `County Name` is renamed to `County`.
- If `LEA Type` is missing, it is derived from the last token of `LEA Name` (`Avon Grove SD` becomes `SD`). See the bug note below.
- Rows whose `School Number` is not numeric are dropped.
- `County`, `LEA Name`, and `AUN` are forward-filled. Older sheets look like pivot reports: the name is on the first row of a group and blank underneath.
- Columns outside the expected set are dropped.
- Rows whose `LEA Name` ends in `Total` are dropped. Older years were shipping subtotal rows.
- Missing count columns are created as null. Counts are `UInt16`. Text columns are pandas strings.
- Blank `aun` values are filled from the first `aun` already seen for that `lea_name`. That path matters for 2006 and earlier, which are currently commented out.
- Headers are snake_cased, then the frame is melted.

Long-form grain: one row per `aun`, `school_number`, `school_year`, `grade`, with `enrollment`. `school_year` is the four-digit start year parsed from the filename (`2020` means 2020–21). Repeating text columns are stored as pandas categories.

### Outputs

- `data/basic_enrollment.pkl.bz2`
- SQLite tables `lea_info`, `school_info`, `basic_enrollment`, `lea_w_enrollment`, `school_w_enrollment` (see [database](database-and-lookups.md))

The download loop is capped at 120 files, which is larger than the number of yearly workbooks, so it is not an active limit.

### Enrollment bug

When `LEA Type` is missing, the notebook reads `df['LEA Name']` (the accumulator) instead of `df1['LEA Name']` (the year just loaded). On the first such year `df` is still empty, so that branch will fail or assign the wrong series. Years that already contain `LEA Type` skip this branch.

## Budget expenses

Notebook: `data_acquisition/acquire_budget_data.ipynb`

Index page:

`https://www.education.pa.gov/Teachers%20-%20Administrators/School%20Finances/Finances/GFBData/Pages/default.aspx`

Links kept match `20xx-xxGFBData.xlsx`. Cache directory is `data/raw/finance_expenses/`.

Only the first five matching links are processed (`count < 5`). The notebook prints each URL as it goes. The saved output from the last run shows 2021, 2020, 2019, 2018, and then a truncated 2017 line, so the cap is a debug limit, not a finished backfill. Years before 2011 are not handled: the sheet read is inside `if int(school_year) >= 2011`, and a miss leaves `df1` undefined.

For each file it reads sheet `ExpDetail` with no skipped rows, then melts so each account column becomes a row. Identifier columns kept through the melt: `InstCat`, `AUN`, `InstName`, `CountyName`. The melted name is `expense_category` (values like `1100-100`) and the amount is `expense_value`. `school_year` is parsed from the filename the same way as enrollment.

`lookup_data/expense_lookups.csv` is joined on `raw_category` = `expense_category`, which adds `expense_category_name_0`, `_1`, and `_2`. Then `instname`, `countyname`, and `instcat` are dropped. Institution name, county, and institution category are expected to come back later by joining `aun` to `lea_info` from the enrollment load. The notebook's own todo says a district-info dataset is still needed for `lea_type`; that table is the enrollment notebook's `lea_info`, not something this notebook builds.

Reference links recorded in the notebook:

- PDE Chart of Accounts PDF, used as the source of the function and object codes
- PDE glossary of child-accounting terms

### Outputs

- `data/budget_expense.pkl.bz2`
- SQLite table `finance_expense`, replaced on each run. Other tables in `pde.db` are left alone.

## Personnel

`python -m pa_edu.personnel` (also called from `python -m pa_edu.load`) downloads the individual professional-staff workbooks and writes `professional_assignment` and `professional_staff`. Header changes are explicit per year in `pa_edu/personnel_layouts.py`. A year whose headers do not match that layout stops the load. Column rules, the salary double-count warning, and the primary-assignment fallback are in [personnel](personnel.md).

## What "done" meant in 2022

Enrollment cleaning is the more finished of the two. It spans 2007 onward, with year-specific sheet names and a written reason for stopping at 2006. Budget loading works for recent General Fund Budget files but only keeps five of them, and it trusts that `ExpDetail` has a stable header from 2011 forward. The analysis notebook assumes both loads have been run and that 2020 exists in both.
