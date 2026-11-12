# Analysis app (legacy Dash)

> **Legacy.** The published product is the static LEA browser at https://pdenumbers.org/ (`pa_edu/web/` + `python -m pa_edu.publish`). `python -m pa_edu.app` is the older Dash chart on `data/pde.db`.

The running app is `python -m pa_edu.app`. It has two views of the same General Fund Budget:

- **All expenses** includes charter tuition. That money is part of what the district spends.
- **Per pupil** removes brick-and-mortar and cyber charter tuition, regular and special education, because those students are in the charter's enrollment. Tuition for approved private schools and PRRIs stays in the numerator. Those amounts come from the AFR tuition schedule (`tuition_paid`), which is the split the budget's object-500 lines do not publish.

The rest of this page describes the 2022 notebook the app replaced.

# Original analysis notebook

Notebook: `analysis/chart_expense_per_enrollment.ipynb`

This is a JupyterDash app on top of `data/pde.db`. It was the last thing committed (13 Sep 2022). The saved outputs show it was executed locally with Python 3.10, outside the Alpine image, and that run did not finish cleanly.

## What it shows

A sunburst of **expense per enrolled student** for a chosen county and one or more LEAs.

- Default county is `Chester`.
- The LEA dropdown is multi-select. Changing the county reloads LEA names and selects all of them.
- The sunburst path is `lea_name` → `expense_category_name_0` → `expense_category_name_1` → `expense_category_name_2`.
- Slice size is `expense_value / enrollment`.
- Color is the top expense group.
- Hover includes the raw dollars, the account code, and the per-student figure.
- Only `lea_type` of `SD` or `CS` is included.
- School year is hardcoded to `2020` in the join (`2020 = e.school_year`), on both the sunburst and the scatter.

Enrollment in the denominator is `lea_w_enrollment.enrollment` for that AUN and year: the sum of every grade cell, including the AM/PM/full-day splits.

A second, non-app cell set draws a Plotly scatter for Chester County only: x is `expense_value`, y is `enrollment`, color is per-student expense. That query also drops object-code `500` rows for school districts. The sunburst does not. See [lookups](database-and-lookups.md).

## Queries

Counties:

```sql
select county from lea_info group by county order by county
```

LEAs for the dropdown (parameterized on county):

```sql
select lea_name from lea_info
where county = ?
group by lea_name
order by lea_name
```

Sunburst, abbreviated. `lea_name` is expanded to one `?` per selected LEA:

```sql
SELECT l.lea_name, l.lea_type, l.county,
       e.expense_category, e.school_year, e.expense_value,
       le.enrollment,
       e.expense_value / le.enrollment as expense_value_per_enrollment,
       e.expense_category_name_0, e.expense_category_name_1,
       e.expense_category_name_2
FROM lea_info l
INNER JOIN finance_expense e
    ON l.aun = e.aun AND 2020 = e.school_year
INNER JOIN lea_w_enrollment le
    ON e.aun = le.aun AND e.school_year = le.school_year
WHERE county = ?
  AND l.lea_name IN ( ... )
  AND (lea_type = 'CS' OR lea_type = 'SD')
```

`school_year` is compared as the number `2020`. The acquisition notebooks write it from a regex capture, so SQLite will coerce a numeric-looking text value. A format change in that column breaks the join silently (inner join, zero rows).

## Layout and callbacks

`app.layout` is a title ("JupyterDash Demo"), a county `dcc.Dropdown`, an LEA `dcc.Dropdown`, and `dcc.Graph` id `sun-graph`. Bootstrap is loaded via `dash_bootstrap_components.themes.BOOTSTRAP` but no Bootstrap layout components are used.

- `update_lea_dropdown` — county in, LEA options and value out.
- `update_sun_graph` — LEA value in, county as `State`, figure out. The figure is built by `build_sunburst`.

`app.run_server(mode='inline')` is the cell that would render it inside the notebook.

## Why the saved run failed

Two problems are visible in the notebook as it sits:

1. **Definition order.** `build_sunburst` is in a cell *after* `app.run_server`. The callback closes over that name. The stored traceback is `NoLayoutException` from Flask while serving the inline app. Moving the function above the layout, or re-running the function cell before `run_server`, is required.

2. **Dependencies are not in the image.** The notebook imports `dash`, `dash_bootstrap_components`, and `jupyter_dash`. None of those are in `docker_files/development/requirements.txt` or the production requirements. `plotly` is. An output on the layout cell also says `dash_bootstrap_components` has no attribute `Dropdown`. The current source uses `dcc.Dropdown`, so that message is leftover from an earlier version of the cell (`dbc.Dropdown`).

The scatter cells call `pd.read_sql(sql, cnx)`, and this notebook never opens `cnx`. That only works if a previous notebook left `cnx` in the same kernel.

## What the chart cannot do yet

- No year picker. 2020 is fixed in two SQL strings.
- No grade filter. The denominator is all grades summed.
- No toggle for the object-500 school-district exclusion. It exists only on the scatter.
- Title is still "JupyterDash Demo".
- `plotly.io` is imported and unused. `State` is imported and used.
