# Refined pipeline

This is the active path. Catalog → raw cache → parsers → Parquet → DuckDB views → static LEA browser. The older SQLite loaders and Dash app remain in the tree for personnel and historical notebooks; new finance, enrollment, assessment, and tax sources go through this pipeline.

The refined dataset is a set of Parquet tables under `data/refined/`. DuckDB sits on top of those files. The raw PDE workbooks stay on disk, and every refined row points at the URL of the workbook it came from. `python -m pa_edu.publish` turns those tables into `pde_site/` for https://pdenumbers.org/.

## Goals

- A query can cite the original document. Each refined row carries a `document_id`, and that document row stores the URL the file was downloaded from.
- A clone of this repo, plus `pip install -e .` and one command, rebuilds the refined tables. The repo does not ship the data.
- The relationships live in this document and in checked-in SQL that builds the DuckDB views.
- A new PDE publication can need a human to confirm the layout. Publications we have already parsed rebuild with no one watching.
- Raw files are kept. A later PDE edit does not throw away the bytes we already downloaded.
- `school_year` is the four-digit start year. `2024` means 2024–25.

## Layout

```text
sources/catalog.toml          checked in. One entry per known document.
data/raw/<source_id>/<sha256>/  gitignored. Exact bytes we downloaded.
data/refined/*.parquet        gitignored. Rebuilt from raw + catalog.
data/pde.duckdb               gitignored. Views over the Parquet.
sql/model.sql                 checked in. The view definitions.
```

`python -m pa_edu.refine` reads the catalog, downloads any file whose bytes are not already under `data/raw/`, parses the entries marked stable, and writes the Parquet and the DuckDB file. A second run with the cache filled does not need the network.

## Sources

`document` is the citation record.

| Column | Meaning |
| --- | --- |
| `document_id` | Stable id, referenced by every refined row from that file |
| `source_id` | Family, such as `gfb`, `afr`, `edna`, or `enrollment` |
| `source_url` | URL of the workbook or extract itself |
| `page_url` | PDE page that linked it, when there is one |
| `sha256` | Hash of the bytes |
| `retrieved_at` | When this copy was downloaded |
| `school_year` | Start year, when the file is a single year |
| `parser` | Name of the parser that is allowed to read it |

The same URL can produce more than one `document_id` if PDE replaces the file and the hash changes. Both copies stay under `data/raw/`. The catalog points the current rebuild at the newest hash. An older analysis still resolves its `document_id` to the URL and the retained file.

The catalog is the list of documents the rebuild will fetch. Each entry has the URL, the parser, and a status of `stable` or `review`. `refine` downloads and parses `stable` entries only. A companion check reads the live PDE index pages and prints URLs that are not in the catalog. It does not parse them and it does not delete cached files.

A new school year joins the rebuild when someone adds its URL. If the headers match a parser that is already `stable`, that is the whole change. If the headers moved, the entry stays at `review` until the parser has a rule for that file. After that, the year is part of the unattended backfill.

PDE’s index pages list about ten years and say older AFR files are on an FTP site they do not link. Older years are catalog entries with the last URL we know. When that URL dies, the cached file still rebuilds. The live index is how we notice a new file, not how we find history.

## LEAs

The first refined table is the LEA list. Enrollment is not the source of it. The enrollment load’s `lea_info` is “the newest enrollment row for this AUN,” which misses intermediate units, career and technical centers, and jointures, and it renames an LEA whenever the newest file does.

The directory is EdNA’s Educational Entities and Administrators extract, open and closed:

[https://www.edna.pa.gov/Screens/Extracts/wfExtractEntitiesAdmin.aspx](https://www.edna.pa.gov/Screens/Extracts/wfExtractEntitiesAdmin.aspx)

That page is an ASP.NET form, so the catalog records the page URL and the saved extract. Once the download request is known, later refreshes are automatic. A form change is a `review` item: save the new extract, point the catalog at it, and keep the previous extract on disk.

Rows kept from EdNA are the public entities that file financial reports:

| EdNA category | `lea.category` |
| --- | --- |
| School District | `school_district` |
| Charter School | `charter_school` |
| Intermediate Unit | `intermediate_unit` |
| Career and Technical Center | `career_and_technical_center` |
| Special program jointure / joint operating committee | `jointure` |
| State Juvenile Correctional Inst | `state_juvenile_correctional` |

`aun` is the nine-digit Administrative Unit Number, stored as text. It is the primary key. Intermediate unit AUNs end in `000000`.

`lea` holds identity that comes from the directory.

| Column | Meaning |
| --- | --- |
| `aun` | Primary key |
| `lea_name` | Official name on the directory extract |
| `category` | One of the values above |
| `status` | `open`, `closed`, or `unknown` |
| `county` | County of the administrative office |
| `iu_aun` | Intermediate unit this LEA sits in, when EdNA gives one |
| `in_directory` | False when the AUN was seen in a finance or enrollment file and not in EdNA |
| `document_id` | The EdNA extract |

Finance and enrollment files also carry a name, a county, and an LEA type for the year they were published. Those stay on the fact rows, so a rename in 2019 does not overwrite the 2017 name, and a file that says `Cyber CS` does not overwrite the EdNA category. An AUN that appears in a General Fund Budget, an AFR, or an enrollment file and not in EdNA stays in `lea`, with `in_directory` false and the name taken from the latest of those files. Its spending and its headcount then join.

The 2024–25 General Fund Budget `Exp` sheet is the check on coverage. It has 791 reporting entities:

| `InstCat` | Count | What the names are |
| --- | --- | --- |
| `01` | 500 | School districts |
| `02` | 29 | Intermediate units |
| `03` | 74 | Career and technical centers |
| `04` | 179 | Charter schools |
| `06` | 9 | Jointures and joint operating committees |

After the LEA table is built, every one of those AUNs should hit `lea`. That match is the gate before any fact table is trusted.

The [data.pa.gov public schools file](https://data.pa.gov/api/views/knsp-q7fv/rows.csv?accessType=DOWNLOAD) is a building list (AUN plus school number). It is a later school table, not the LEA list.

## Budget and actuals

“Budget” and “the finest published amounts” are different files. Both are kept. They are not added together.

General Fund Budget files are the adopted budget, filed before the school year. The current page lists 2017–18 through 2026–27, one workbook a year, posted around the end of August:

[https://www.pa.gov/agencies/education/programs-and-services/schools/grants-and-funding/school-finances/financial-data/general-fund-budget-gfb-data](https://www.pa.gov/agencies/education/programs-and-services/schools/grants-and-funding/school-finances/financial-data/general-fund-budget-gfb-data)

Example file: [2024–25 GFB](https://www.pa.gov/content/dam/copapwp-pagov/en/education/documents/schools/grants-and-funding/school-finances/finances/gfbdata/2024-25gfbdata.xlsx).

The finest budget grain in that workbook:

| Who | Sheet | Grain |
| --- | --- | --- |
| Districts, charters, CTCs, jointures | `Exp` (older files in this window still use `ExpDetail`) | AUN × function × major object. Columns look like `1100-100`. Function is the four-digit function (`1100`), not the subfunction (`1110`). Object is the major object (`100`), not the detail object (`120` or `562`). |
| Intermediate units | `IUExp_Prog` | Same pair plus a program code. Columns look like `1100-100-10`. About 2,100 amount columns on the 2024–25 file. |

There is no school-level budget in this file, and no detail-object budget. `1100-500` is all “other purchased services,” which mixes charter tuition with other tuition and purchased services. The tuition schedule already loaded by `pa_edu.tuition` is the published split of that rollup; it stays a separate table.

Annual Financial Report files are actuals, after the year. The yearly workbook on the summary-level page is the full reported AFR. The 2024–25 file is the snapshot as of 16 Apr 2026:

[https://www.pa.gov/content/dam/copapwp-pagov/en/education/documents/schools/grants-and-funding/school-finances/summary-of-afr-data/afr-data-summary-level/afr%202024-2025.xlsx](https://www.pa.gov/content/dam/copapwp-pagov/en/education/documents/schools/grants-and-funding/school-finances/summary-of-afr-data/afr-data-summary-level/afr%202024-2025.xlsx)

Page: [AFR data, summary-level](https://www.pa.gov/agencies/education/programs-and-services/schools/grants-and-funding/school-finances/financial-data/summary-of-annual-financial-report-data/afr-data-summary-level).

The `EXP` sheet is the finest account grain PDE publishes for every reporting LEA. The 2024–25 sheet has 246,032 rows, long already, for institution categories `01`, `02`, `03`, and `04`. Category `06` jointures are on the GFB and are absent from this `EXP` sheet.

| Column | Meaning |
| --- | --- |
| `FundCode` | `10` is the general fund. Other funds are on the same sheet (`23`, `26`, `39`, and others). They stay on the row. |
| `AccountCode` | Function actually reported. Often a subfunction (`1110`). Some functions are reported at four digits (`1300`, `3200`) because that is the leaf. |
| `Rollup1AccountCode`, `Rollup2AccountCode`, `Rollup3AccountCode` | Ancestors of that function (`1000`, `1100`). Attributes of the row. |
| `ObjectCode` | Detail object, three digits (`120`). Every 2024–25 row has one. |
| `Rollup1ObjectCode`, `Rollup2ObjectCode` | Major object (`100`) and the level between, when PDE filled them. |
| `ProgramCode` | Set on IU rows. Empty for most district rows. |
| `ElementaryAmount`, `SecondaryAmount`, `FederalAmount`, `TotalAmount` | Elementary is K–6 and not federally funded. Secondary is 7–12 and not federally funded. Federal is the federally funded part. On functions that collect all three, PDE fills the total from them. On others (social work is the published example) only the total and the federal piece are collected, and the federal piece already sits inside the total. Analysis uses `TotalAmount`. |

`SLFS_EXP_1` and `SLFS_EXP_2` are the same columns plus `SchoolName` and `BranchNumber` (a school number, or `LEAW` for LEA-wide). The 2024–25 file splits them only because of the spreadsheet row limit: about 1.03 million rows on the first sheet and 0.11 million on the second. Building-level reporting starts with the 2024–25 AFR. Those rows are the same dollars as `EXP`, broken out by building. They get their own table so a query has to opt in to the building grain. A repeated building-and-account row is summed. `LEAW` is the unallocated remainder: when the named buildings already equal the `EXP` amount, the `LEAW` rows on that line are dropped. Two 2024–25 lines still do not add back to `EXP` (Pittsburgh SD 2519-890 and Northern York County SD 2260-350). `check` allows those two and fails on any other gap.

Account titles come from the chart of accounts, joined on function and object, not from a hand-maintained rename of `1100-100`:

[Chart of Accounts 2024–25 (PDF)](https://www.pa.gov/content/dam/copapwp-pagov/en/education/documents/schools/grants-and-funding/school-finances/comptrollers-office/chart%20of%20accounts%202024-2025.pdf)

The wide files on the [AFR detailed](https://www.pa.gov/agencies/education/programs-and-services/schools/grants-and-funding/school-finances/financial-data/summary-of-annual-financial-report-data/afr-data-detailed) page are rollups of `EXP`. They are useful later as a check that our sums match PDE’s published totals. They are not the fact table.

- Expenditure Detail is one column per function and subfunction, including both a parent (`1100`) and its children (`1110`). Summing the sheet double-counts. The 2024–25 sheet also has thousands of empty trailing columns.
- Object-Level Expenditures is one column per major object for the whole LEA. Objects `220` and `230` are components of object `200` on that sheet.

`JEXP_NS` and `JEXP_SP` are wide, selected-account schedules (nonspecial and special) used around tuition rates. They are not the full ledger.

## Assessment (PSSA and Keystone)

District proficiency for the Pennsylvania System of School Assessment (grades 3–8) and Keystone Exams (grade 11) comes from the Assessment Reporting page:

[https://www.pa.gov/agencies/education/data-and-reporting/assessment-reporting](https://www.pa.gov/agencies/education/data-and-reporting/assessment-reporting)

Each spring assessment year is one district workbook. Catalog `school_year` is the start year of that school year: the spring 2025 PSSA file is `pssa-district-2024` with `school_year = 2024`. There is no 2019–20 / spring 2020 file (COVID). School-level workbooks are not in the refined tables yet.

`assessment_result` grain is AUN × school year × assessment (`pssa` or `keystone`) × subject × grade × student group. Subjects are normalized (`ela`, `math`, `algebra_i`, `biology`, `literature`). Grades are `003`–`008`, `011`, or `total`. Percents for groups smaller than 11 students are suppressed in the source and stored as null. `pct_proficient_and_above` is the main achievement measure; the four level percents are kept beside it.

## Enrollment

Public-school enrollment is an October 1 headcount from PIMS, for students enrolled and attending. The 2024–25 workbook says the as-of date is October 1, 2024, and that the reporters are school districts, area vocational-technical schools, charter schools, intermediate units, and state-operated educational facilities. The page is:

[https://www.pa.gov/agencies/education/data-and-reporting/enrollment](https://www.pa.gov/agencies/education/data-and-reporting/enrollment)

The fact comes from the yearly public-school workbook, one file per school year. 2025–26 is [enrollment public schools 2025-2026.xlsx](https://www.pa.gov/content/dam/copapwp-pagov/en/education/documents/data-and-reporting/enrollment/public-school/enrollment%20public%20schools%202025-2026.xlsx). 2007–08 through 2010–11 are `.xls` and use “school” singular in the filename. `school_year` comes from the catalog entry.

The headcount sheet is the school-by-grade sheet.

| Years | Sheet | Header rows skipped |
| --- | --- | --- |
| 2011–12 onward | `LEA and School` | 4 |
| 2010–11 | `School` | 4 |
| 2009–10 | `School - Data File` | 4 |
| 2008–09 | `School - Datafile` | 4 |
| 2007–08 | `LEA - Data File` | 6 |

2004–05, 2005–06, and 2006–07 are on the same page and are downloaded. They stay at `review`. The 2006–07 sheet is `School Enrollments`, with no AUN and no school number: county and LEA name are filled down a group, schools sit on the following rows, and a row whose LEA name ends in `Total` repeats the schools above it. Grades are `PreK`, `K4`, `K5`, and `1` through `12`, plus ungraded. A refined row from those years keeps a null `aun` until someone writes a rule. The load does not copy an AUN from a later year by matching the LEA name.

The consolidated workbook (2016–17 through 2025–26) and the 2007–2012 rollup are the same yearly numbers again. They are retained and not parsed into `enrollment`.

On the 2024–25 `LEA and School` sheet the grain is one row per AUN and school number, with a column per grade and a `Total` column. Summing the grade columns equals `Total` on all 3,416 rows in 2024–25, so those columns partition the students. `Total` is the check, not a grade. A few earlier rows publish a `Total` that is one or more students above the grade columns on both the school sheet and the LEA sheet; the grade columns still agree across those two sheets, and that is the check that has to pass. On the race sheet a cell of `*` is suppressed, and a trailing `^` is a count rounded to a multiple of 5. Neither is an exact enrollment, so neither is stored. `check` does not require a grade to match the headcount when any race cell in it is `*` or `^`. An all-zero duplicate of a race row is dropped. A reported zero stays a row. A grade column that a year does not publish produces no row. 2007–08 also publishes `EUG` and `SUG` (elementary and secondary ungraded). Those are grades in the years that have them. The current SQLite load drops them.

Grade codes:

| Code | Who is counted |
| --- | --- |
| `prek`, `k4`, `k5` | The single column in years that do not split the session |
| `pka`, `pkp`, `pkf` | Pre-kindergarten, half-day morning, half-day afternoon, full day |
| `k4a`, `k4p`, `k4f` | First year of a two-year kindergarten, same session split |
| `k5a`, `k5p`, `k5f` | Traditional kindergarten, or the second year of a two-year program, same session split |
| `001`–`012` | Grades 1–12 |
| `eug`, `sug` | Ungraded elementary and secondary, in the years that publish them |

A file that already has `PKA` / `PKP` / `PKF` keeps the three codes. A file that only has `PreK`, `K4`, and `K5` stores `prek`, `k4`, and `k5` with an empty session. The load does not pick AM or full day for them.

`enrollment` is one grade cell: `aun`, `school_number`, `school_year`, `grade_code`, `enrollment`, plus the name, `lea_type`, county, and school name printed on that row, and `document_id`. `school_number` is text. The key is AUN plus school number. In 2024–25 the value `9999` is used by 459 LEAs and `0` is used by 27 intermediate units, so a school number is not a statewide id. The current SQLite `school_info` dedupe on `school_number` alone is not repeated.

`9999` is part of the headcount. Those 459 rows hold 14,037 students in 2024–25, the school name is the LEA name, and they sit alongside real buildings. School number `0` is the intermediate unit’s own row. Both stay. Dropping either undercounts the LEA. Summing every school row on the 2024–25 file equals the `LEA` sheet for all 781 AUNs. The `LEA` sheet is that check, not a second fact.

The same workbook carries two finer cuts of the same students. They get their own tables and share the workbook’s `document_id`.

| Sheet | Table | Grain |
| --- | --- | --- |
| `LEA, School and Gender` | `enrollment_gender` | AUN × school × `Female` or `Male` × grade |
| `LEA and Race` | `enrollment_race` | AUN × race × grade. No school. |

In 2024–25, female plus male equals the school grade cell, for every school. Race is checked against the `LEA` sheet, not against a single school. County, statewide, and Penn Data sheets are a different count: the workbook says county and statewide totals are unique students, they add full-time students educated outside the resident district, and they leave out intermediate-unit and CTC part-day enrollment. LEA and school rows will not sum to those sheets. Part-day intermediate-unit and CTC students can also be counted in a district, so summing every LEA’s headcount is not the statewide unique count.

`school` is one row per AUN and school number, with the school name from the newest enrollment year. The name for a given year stays on `enrollment`.

LEA types printed on the 2024–25 file are `SD`, `CS`, `Cyber CS`, `IU`, `OCCCTC`, `COMCTC`, and `SJCI`. 2007–08 also has `SPJ` and `STATE`, and a stray contact-info row whose type is a URL. Rows with no numeric AUN are dropped. The published type stays on the enrollment row.

Private and nonpublic enrollment, English-learner counts, low-income percentages, projections, and home-education counts are other files on the same page. They are not this table.

## Tables and how they join

```text
document 1───* lea
document 1───* lea_year
document 1───* gfb_expenditure
document 1───* afr_expenditure
document 1───* afr_expenditure_school
document 1───* enrollment
document 1───* enrollment_gender
document 1───* enrollment_race

lea 1───* lea_year
lea 1───* gfb_expenditure
lea 1───* afr_expenditure
lea 1───* afr_expenditure_school
lea 1───* school
lea 1───* enrollment
lea 1───* enrollment_gender
lea 1───* enrollment_race

school 1───* enrollment
school 1───* enrollment_gender
grade 1───* enrollment
grade 1───* enrollment_gender
grade 1───* enrollment_race

account *───* gfb_expenditure          function_code + object_code
account *───* afr_expenditure          function_code + object_code
account *───* afr_expenditure_school
```

`lea_year` is the name and county PDE printed on a finance file for that AUN and year: `aun`, `school_year`, `lea_name`, `county`, `inst_cat`, `document_id`.

`gfb_expenditure` is one reported budget amount.

| Column | Meaning |
| --- | --- |
| `aun`, `school_year` | Who and which budget |
| `function_code` | `1100` |
| `object_code` | Major object, `100` through `900` |
| `program_code` | Empty except on `IUExp_Prog` |
| `amount` | Dollars. A reported zero stays zero. An account that was not a column that year has no row. |
| `fund_code` | Always `10`. The GFB is the general fund. |
| `document_id` | The workbook |

`afr_expenditure` is one `EXP` row: `aun`, `school_year`, `fund_code`, `function_code`, `object_code`, `program_code`, the rollup codes, `elementary_amount`, `secondary_amount`, `federal_amount`, `total_amount`, `document_id`.

`afr_expenditure_school` is the stacked `SLFS_EXP_*` sheets: the same amount columns plus `school_number` (`BranchNumber`, with `LEAW` left as text).

`account` is the chart-of-accounts dimension: `function_code`, `object_code`, `function_name`, `object_name`, `major_function`, `major_object`. A code that shows up in a workbook and not in the chart still loads; the name columns are null.

`grade` is the enrollment dimension: `grade_code`, `label`, `band` (`prek`, `k4`, `k5`, `grade`, `ungraded`), and `session` (`am`, `pm`, `full`, or empty).

`school` is `aun`, `school_number`, and `school_name` from the newest year that published that pair. `enrollment.school_name` is the name on that year’s row. `enrollment_gender` repeats the school grain with `gender`. `enrollment_race` has `race` and no school number. A 2004–2006 row with no AUN has a null `aun` and does not join to `lea` until a rule gives it one.

DuckDB views in `sql/model.sql` expose these tables and one convenience view, `afr_general_fund`, which is `afr_expenditure` filtered to `fund_code = '10'`. Joining `document` on `document_id` is how a result lists `source_url`.

Sums that match PDE’s own totals:

- AFR: sum `total_amount`. Group by `function_code` or by a rollup column, not by both.
- AFR objects: sum `object_code`, or sum a rollup object column, not both.
- GFB: sum `amount` at `function_code` × `object_code`. Compare to AFR general fund only after AFR detail objects are rolled to the major object and AFR subfunctions are rolled to the four-digit function.
- School-level AFR is a breakdown of `afr_expenditure` for the years that have it. Queries read one table or the other.
- Enrollment headcount is the sum of `enrollment` across `grade_code` for an AUN, school, and year. That sum is the published grade columns, and it matches `Total` except where both the school sheet and the LEA sheet share the same gap. Gender is a breakdown of the same cell. Race is a breakdown of the LEA for grades PDE did not suppress. None of those three are added together. The county and statewide sheets are not the headcount.

## Status and remaining work

Built and shipping:

1. Catalog format, raw cache keyed by hash, and the `document` table.
2. EdNA extract into `lea`, reconciled against the GFB reporting entities.
3. GFB `Exp` / `ExpDetail` and `IUExp_Prog` into `gfb_expenditure`.
4. AFR `EXP` into `afr_expenditure`, plus school-level `SLFS_EXP_*` into `afr_expenditure_school` where those sheets exist.
5. Public-school enrollment into `enrollment`, with gender and race cuts. 2007–08 onward is stable year by year as each sheet rule passes `check`; 2004–05 through 2006–07 stay at `review`.
6. District PSSA and Keystone into `assessment_result`.
7. Act 1 indexes, real-estate tax mills, charter ADM, and home-education counts as sidecar / supporting tables.
8. Static LEA browser via `publish` (`pa_edu/web/` → `pde_site/` → elm).

Still on the older path or not yet cataloged:

- Professional-staff salaries (`pa_edu.personnel`) load into SQLite and are attached at publish for the Staff tab; they are not yet a refined Parquet family.
- AFR `REV` (revenue) is the same shape of work as `EXP` and can follow without a new layout; it is not in the refined tables yet.
- School-level assessment workbooks are not in the refined tables yet.
- Private / nonpublic enrollment, English-learner counts, low-income percentages, and projections on the enrollment page are other files, not this enrollment table.

## Testing

The refined path has two test layers. Both run offline. Neither downloads PDE, and neither checks in a real workbook. Parser and publish helpers live under `tests/` (`test_refine.py`, `test_publish.py`). The Jenkins test stage is still a stub and does not run `check`.

**Parser tests** live next to the code and run under `pytest` on every change. Each parser is fed a tiny workbook built in the test, with a couple of LEAs and a couple of accounts. The cases worth pinning:

- AUN stays a nine-digit string. `101260303.0` from Excel does not become `1012603030` or `1.01260303e8`.
- `school_year` is the start year taken from the catalog entry, not from a header cell that says `2024-2025`.
- A GFB zero stays a row. An account column that is absent that year produces no row.
- `1100-100` and `1100-100-10` split into function, object, and program. A header that is not an account code is rejected rather than melted into the fact table.
- Empty trailing columns, as on the 2024–25 Expenditure Detail sheet, are ignored.
- `SLFS_EXP_1` and `SLFS_EXP_2` stack. `LEAW` stays text. A repeated building and account is summed, and `LEAW` is dropped when the named buildings already equal `EXP`.
- An AFR row keeps `fund_code`, the reported `function_code`, and the detail `object_code`. Rollup columns stay attributes of that row.
- An enrollment `Total` column is not melted. A row whose LEA name ends in `Total` is dropped. `EUG` and `SUG` are kept when the sheet has them. School number `9999` and `0` are kept. The school key is AUN plus school number. Gender and race land in their own tables.
- Every fact row’s `document_id` resolves to the fixture’s `source_url`.
- A catalog entry marked `review` is downloaded and left unparsed. A second hash for a URL already on disk adds a document and leaves the old bytes in place.

`sql/model.sql` is applied to those fixture tables in DuckDB. The test checks that `afr_general_fund` is fund `10` only, and that a fact row joins to `lea` and to `document`.

**Rebuild checks** are `python -m pa_edu.check`, run by a person after `refine` against the local raw cache. CI does not run them, because they need the real files. A year does not move from `review` to `stable` until they pass for that file. The checks are:

| Check | Pass means |
| --- | --- |
| LEA coverage | All 791 AUNs on the 2024–25 GFB `Exp` sheet are in `lea`. |
| Fact identity | Every `aun` on a fact row is in `lea`. Every `document_id` has a `source_url`. |
| Grain | No duplicate key. GFB key is AUN, year, function, object, program. AFR key adds fund. School AFR adds school number. Enrollment key is AUN, school number, year, grade. Gender adds gender. Race is AUN, year, race, grade. |
| Cell round-trip | For a fixed handful of AUNs and account codes, `gfb_expenditure.amount` equals the source cell, and `afr_expenditure.total_amount` equals the source `EXP` row. For a fixed handful of schools, each grade cell equals `enrollment`. |
| Published totals | For those same AUNs, general-fund `total_amount` rolled to a leaf function matches that column on Expenditure Detail, and detail objects rolled to a major object match Object-Level Expenditures. Parent columns on Expenditure Detail (`1100` beside `1110`) are not part of the sum. Objects `220` and `230` on the object file are not added on top of object `200`. |
| School rollup | Where `SLFS` exists, building rows for one AUN, fund, function, and object sum to that `EXP` row. |
| Enrollment totals | Grade rows for a school sum to the grade columns, and those columns agree with the `LEA` sheet. `Total` may differ only when the school sheet and the LEA sheet share the same gap. Female plus male equals the school cell. Race sums to the LEA for grades with no `*` or `^` cell. Every enrollment AUN is in `lea`. |
| Repeatable | A second `refine` on an unchanged cache writes the same row counts and the same document hashes. |

The cell round-trip is the citation test: the number in an analysis is the number in the workbook at `document.source_url`. The published-total check is what stops a parser from summing a rollup into the leaves. Both use a small checked-in list of AUNs and codes, not a snapshot of the full table.
