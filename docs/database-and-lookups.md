# Database and lookups (legacy SQLite)

> **Legacy.** The citeable tables are Parquet under `data/refined/` with DuckDB views from `sql/model.sql`. See [`refined-pipeline.md`](refined-pipeline.md). This page describes `data/pde.db` from the older loaders.

All tables live in `data/pde.db` (SQLite, gitignored). Pandas `to_sql` rebuilds each table from scratch. There are no migrations or foreign keys. The personnel load adds indexes on `(aun, school_year)` and, for assignments, `(public_id, school_year)`.

Run enrollment before budget. Budget does not create `lea_info` or `lea_w_enrollment`, and the chart needs both.

## Tables from the enrollment notebook

`lea_info` — one row per administrative unit number, taken from the newest `school_year` for that `aun`.

| Column | Notes |
| --- | --- |
| `aun` | Index. PDE Administrative Unit Number. Join key to finance. |
| `lea_name` | Local education agency name as of the newest year |
| `lea_type` | Suffix-style type from the source file (`SD` school district, `CS` charter school, and whatever else PDE used) |
| `county` | County name from that same newest row |

`school_info` — one row per `school_number`, newest year wins.

| Column | Notes |
| --- | --- |
| `school_number` | Index. Deduped on this column alone |
| `school_name` | |
| `aun` | Owning LEA |

School numbers in the PDE files are not obviously statewide unique. Deduping only on `school_number` can collapse two schools that share a number under different AUNs. Worth checking before trusting `school_info` or `school_w_enrollment`.

`basic_enrollment` — long-form counts.

| Column | Notes |
| --- | --- |
| `aun`, `school_number`, `school_year`, `grade` | Composite index |
| `enrollment` | Headcount for that grade code. Nullable where the source year had no column |

`grade` values are the original column codes: `pka`, `pkp`, `pkf`, `k4a`, `k4p`, `k4f`, `k5a`, `k5p`, `k5f`, `001`–`012`. AM/PM/full-day kindergarten splits are still separate rows. Nothing rolls them into a single grade.

`lea_w_enrollment` — `sum(enrollment)` by `aun`, `school_year`. This is the denominator in the chart (`expense_value / le.enrollment`). Because AM, PM, and full-day columns are all summed, a student is counted once per grade cell PDE published. That matches "total of the published cells," which may double-count if PDE also published a total column that was not fully dropped. Total rows (LEA name ending in `Total`) are removed. Total columns are removed only when they are outside the expected column list.

`school_w_enrollment` — same sum by `school_number`, `school_year`. Not used by the chart.

## Table from the budget notebook

`finance_expense` — one row per LEA, year, and account code. Index is `aun`, `school_year`, `expense_category`.

| Column | Notes |
| --- | --- |
| `aun` | Join to `lea_info.aun` |
| `school_year` | Four-digit start year, stored as text from the filename |
| `expense_category` | Raw code, e.g. `1100-100` |
| `expense_value` | Dollar amount from the `ExpDetail` sheet |
| `expense_category_name_0` | Top group: Instruction, Support Services, and so on |
| `expense_category_name_1` | Function: Regular Programs, Food Services, Debt Service, … |
| `expense_category_name_2` | Object: Salaries, Benefits, Supplies, … |

`instcat`, institution name, and county are dropped before the write. The chart recovers name, type, and county from `lea_info`. LEAs that appear in the finance file but not in enrollment will fall out of the inner join.

The notebook comment above this write still says "create lea_info table." The code writes `finance_expense` only.

## Tables from the personnel load

Written by `pa_edu.personnel`. Full rules are in [personnel](personnel.md).

`professional_assignment` — one row per person, LEA, year, and assignment. `annual_salary` repeats on every assignment for that person at that LEA. Summing it here double-counts.

`professional_staff` — one row per `public_id`, `aun`, and `school_year`, so salary can be summed. `row_rule` is `primary_assignment` or `highest_fte`. `assignment_count` is how many assignment rows were collapsed.

## Expense lookup

`lookup_data/expense_lookups.csv` — 176 rows, the only curated data in git.

| Column | Meaning |
| --- | --- |
| `raw_category` | `{function}-{object}`, matching melted `ExpDetail` headers |
| `expense_category_name_0` | Major class |
| `expense_category_name_1` | Function name |
| `expense_category_name_2` | Object name |

Function code is the PDE expenditure function. Object code is the PDE object. Codes present:

| Function | Name in the file | Object codes present |
| --- | --- | --- |
| 1100 | Regular Programs - Elementary / Secondary | 100–800 |
| 1200 | Special Programs - Elementary / Secondary | 100–800 |
| 1300 | Vocational Education | 100–800 |
| 1400 | Other Instructional Programs - Elementary / Secondary | 100–800 |
| 1500 | Nonpublic School Programs | 100–800 |
| 1600 | Adult Edecation Programs | 100–800 |
| 1700 | Higher Education Programs For Secondary Students | 500, 600 only |
| 1800 | Pre-Kindergarten | 100–800 |
| 2100 | Support Services - Students | 100–800 |
| 2200 | Support Services - Instructional Staff | 100–800 |
| 2300 | Support Services - Administration | 100–800 |
| 2400 | Support Services - Pupil Health | 100–800 |
| 2500 | Support Services - Business | 100–800 |
| 2600 | Operation and Maintenance of Plant Services | 100–800 |
| 2700 | Student Transportation Services | 100–800 |
| 2800 | Support Services - Central | 100–800 |
| 2900 | Other Support Services | 100–800 |
| 3100 | Food Services | 100–800 |
| 3200 | Student Activities | 100–800 |
| 3300 | Community Services | 100–800 |
| 3400 | Scholarships and Awards | 100–800 |
| 4000 | Facilities Acquisition, Construction, and Improvement Services | 100–700 (no 800) |
| 5100 | Debt Service / Other Expenditures and Financing Uses | 800, 900 |
| 5200 | Interfund Transfers - Ou | 900 |
| 5300 | Transrers Out To Component Units / Primary Governments | 900 |
| 5500 | Special And Extraordinary Items | 800, 900 |
| 5900 | Budgetary Reserve | 800 |

Object names used: 100 Salaries, 200 Employee Benefits, 300 Purchased Professional and Technical Services, 400 Purchased Property Services, 500 Other Purchased Services, 600 Supplies, 700 Property, 800 Other Objects, 900 Other Uses of Funds.

Five top groups (`expense_category_name_0`):

| Group | Rows |
| --- | --- |
| Support Services | 72 |
| Instruction | 58 |
| Operation of Non-Instructional Services | 32 |
| Facilities Acquisition, Construction, and Improvement Services | 7 |
| Other Expenditures and Financing Uses | 7 |

Names are stored with the typos already in the CSV: "Adult Edecation Programs", "Interfund Transfers - Ou", "Transrers Out To Component Units / Primary Governments". A code in a workbook that is not in this file still loads; the three name columns are null for that row, and the sunburst will not group it.

The scatter SQL in the analysis notebook drops object `500` for school districts (`expense_category like '%-500' and lea_type = 'SD'`). The comment next to it points at a double-count: purchased services between a district and a charter. The sunburst query does not apply that filter.
